"""Idempotent dev/staging seed for inventory data.

Usage (local):

    POS_INVENTORY_AUTH_BYPASS=true \
        python -m pos_inventory.scripts.seed_dev --confirm

Usage (cloud one-off task / k8s Job):

    POS_INVENTORY_DB_DSN=postgresql+psycopg://... \
    POS_INVENTORY_ALLOW_SEED=true \
        python -m pos_inventory.scripts.seed_dev --confirm \
            --tenant-id 00000000-0000-0000-0000-000000000001 \
            --sku-count 500

Re-running is safe: every insert is keyed on a natural unique key (sku_code,
location code, lot_code, serial_value) and uses ON CONFLICT DO NOTHING. Stock
is only posted to the ledger for SKUs created on this run, so balances do not
double-count when re-seeding.

Safety: refuses to run unless `POS_INVENTORY_AUTH_BYPASS=true` (dev) or
`POS_INVENTORY_ALLOW_SEED=true` (explicit opt-in for non-dev environments).
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.config import get_settings
from pos_inventory.core.db import session_factory
from pos_inventory.domain.inventory.ledger import post_movement


DEFAULT_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
DEFAULT_USER_ID = UUID("00000000-0000-0000-0000-000000000002")

SITE_CODE = "STORE-01"
SITE_NAME = "Store 01"

LOCATIONS = [
    ("BACKROOM", "Backroom", "physical"),
    ("FRONT", "Sales Floor", "physical"),
    ("IN-TRANSIT", "In Transit", "virtual_in_transit"),
]

DEPARTMENTS = [
    "Electronics",
    "Apparel",
    "Grocery",
    "Home",
    "Toys",
    "Tools",
    "Health",
    "Beauty",
]

# Tracking-type mix: 85% non-serialized, 10% serialized, 5% lot-tracked.
TRACKING_WEIGHTS = [
    ("non_serialized", 85),
    ("serialized", 10),
    ("lot_tracked", 5),
]


@dataclass
class Counters:
    sites_created: int = 0
    locations_created: int = 0
    skus_created: int = 0
    skus_skipped: int = 0
    serials_created: int = 0
    lots_created: int = 0
    ledger_rows: int = 0
    new_sku_ids: list[tuple[UUID, str]] = field(default_factory=list)
    # (sku_id, tracking)


def _check_safety_gate() -> None:
    settings = get_settings()
    allow = os.environ.get("POS_INVENTORY_ALLOW_SEED", "").lower() in {"1", "true", "yes"}
    if not (settings.auth_bypass or allow):
        sys.stderr.write(
            "Refusing to seed: set POS_INVENTORY_AUTH_BYPASS=true (dev) or "
            "POS_INVENTORY_ALLOW_SEED=true to opt in explicitly.\n"
        )
        sys.exit(2)


def _set_tenant(sess: Session, tenant_id: UUID) -> None:
    """Set the per-session GUC so RLS policies allow inserts."""
    sess.execute(
        text("SELECT set_config('app.current_tenant', :tid, false)"),
        {"tid": str(tenant_id)},
    )


def _seed_site_and_locations(
    sess: Session, tenant_id: UUID, counters: Counters
) -> tuple[UUID, dict[str, UUID]]:
    site_id = uuid4()
    res = sess.execute(
        text(
            """
            INSERT INTO inv.site (id, tenant_id, code, name)
            VALUES (:id, :tid, :code, :name)
            ON CONFLICT (tenant_id, code) DO NOTHING
            RETURNING id
            """
        ),
        {"id": str(site_id), "tid": str(tenant_id), "code": SITE_CODE, "name": SITE_NAME},
    ).first()
    if res is None:
        site_id = sess.execute(
            text("SELECT id FROM inv.site WHERE tenant_id = :tid AND code = :code"),
            {"tid": str(tenant_id), "code": SITE_CODE},
        ).scalar_one()
    else:
        counters.sites_created += 1

    locations: dict[str, UUID] = {}
    for code, name, kind in LOCATIONS:
        loc_id = uuid4()
        res = sess.execute(
            text(
                """
                INSERT INTO inv.location (id, tenant_id, site_id, code, name, kind)
                VALUES (:id, :tid, :sid, :code, :name, :kind)
                ON CONFLICT (tenant_id, code) DO NOTHING
                RETURNING id
                """
            ),
            {
                "id": str(loc_id),
                "tid": str(tenant_id),
                "sid": str(site_id),
                "code": code,
                "name": name,
                "kind": kind,
            },
        ).first()
        if res is None:
            loc_id = sess.execute(
                text(
                    "SELECT id FROM inv.location WHERE tenant_id = :tid AND code = :code"
                ),
                {"tid": str(tenant_id), "code": code},
            ).scalar_one()
        else:
            counters.locations_created += 1
        locations[code] = loc_id
    return site_id, locations


def _pick_tracking(rng: random.Random) -> str:
    return rng.choices(
        [t for t, _ in TRACKING_WEIGHTS],
        weights=[w for _, w in TRACKING_WEIGHTS],
        k=1,
    )[0]


def _seed_skus(
    sess: Session,
    tenant_id: UUID,
    sku_count: int,
    rng: random.Random,
    counters: Counters,
) -> None:
    # Lazy import: faker is a dev dependency, not required at runtime.
    from faker import Faker

    faker = Faker()
    Faker.seed(rng.randint(0, 2**31 - 1))

    # Constrain brands to ~20 unique values for realism.
    brand_pool = sorted({faker.unique.company() for _ in range(20)})
    faker.unique.clear()

    for i in range(sku_count):
        tracking = _pick_tracking(rng)
        department = rng.choice(DEPARTMENTS)
        brand = rng.choice(brand_pool)
        # 12-digit numeric UPC
        upc = "".join(rng.choices("0123456789", k=12))
        price = Decimal(f"{rng.uniform(1.99, 999.99):.2f}")
        sku_code = f"SKU-{i + 1:05d}"
        name = f"{brand} {department} {faker.word().capitalize()}"
        sku_id = uuid4()
        res = sess.execute(
            text(
                """
                INSERT INTO inv.sku
                    (id, tenant_id, sku_code, name, tracking,
                     upc, department, brand, price, created_at)
                VALUES
                    (:id, :tid, :code, :name, :tracking,
                     :upc, :dept, :brand, :price, now())
                ON CONFLICT (tenant_id, sku_code) DO NOTHING
                RETURNING id
                """
            ),
            {
                "id": str(sku_id),
                "tid": str(tenant_id),
                "code": sku_code,
                "name": name,
                "tracking": tracking,
                "upc": upc,
                "dept": department,
                "brand": brand,
                "price": price,
            },
        ).first()
        if res is None:
            counters.skus_skipped += 1
            continue
        counters.skus_created += 1
        counters.new_sku_ids.append((sku_id, tracking))


def _stock_skus(
    sess: Session,
    tenant_id: UUID,
    locations: dict[str, UUID],
    rng: random.Random,
    counters: Counters,
) -> None:
    backroom = locations["BACKROOM"]
    actor = DEFAULT_USER_ID
    now = datetime.now(timezone.utc)

    for sku_id, tracking in counters.new_sku_ids:
        unit_cost = Decimal(f"{rng.uniform(0.55, 250.00):.4f}")
        if tracking == "non_serialized":
            qty = Decimal(rng.randint(5, 200))
            post_movement(
                sess,
                tenant_id=tenant_id,
                sku_id=sku_id,
                location_id=backroom,
                qty_delta=qty,
                source_kind="po_receipt",
                source_doc_id=uuid4(),
                unit_cost=unit_cost,
                actor_user_id=actor,
                occurred_at=now,
            )
            counters.ledger_rows += 1
        elif tracking == "serialized":
            count = rng.randint(1, 8)
            for _ in range(count):
                serial_value = f"SN-{uuid4().hex[:16].upper()}"
                serial_id = uuid4()
                sess.execute(
                    text(
                        """
                        INSERT INTO inv.serial
                            (id, tenant_id, sku_id, serial_value, state, unit_cost)
                        VALUES (:id, :tid, :sid, :sv, 'received', 0)
                        ON CONFLICT (tenant_id, serial_value) DO NOTHING
                        """
                    ),
                    {
                        "id": str(serial_id),
                        "tid": str(tenant_id),
                        "sid": str(sku_id),
                        "sv": serial_value,
                    },
                )
                post_movement(
                    sess,
                    tenant_id=tenant_id,
                    sku_id=sku_id,
                    location_id=backroom,
                    qty_delta=Decimal("1"),
                    source_kind="po_receipt",
                    source_doc_id=uuid4(),
                    serial_id=serial_id,
                    unit_cost=unit_cost,
                    actor_user_id=actor,
                    occurred_at=now,
                    serial_state_after="sellable",
                )
                counters.serials_created += 1
                counters.ledger_rows += 1
        else:  # lot_tracked
            lots_n = rng.randint(1, 2)
            for j in range(lots_n):
                lot_code = f"LOT-{uuid4().hex[:10].upper()}"
                lot_id = uuid4()
                sess.execute(
                    text(
                        """
                        INSERT INTO inv.lot (id, tenant_id, sku_id, lot_code, created_at)
                        VALUES (:id, :tid, :sid, :code, now())
                        ON CONFLICT (tenant_id, sku_id, lot_code) DO NOTHING
                        """
                    ),
                    {
                        "id": str(lot_id),
                        "tid": str(tenant_id),
                        "sid": str(sku_id),
                        "code": lot_code,
                    },
                )
                qty = Decimal(rng.randint(10, 100))
                post_movement(
                    sess,
                    tenant_id=tenant_id,
                    sku_id=sku_id,
                    location_id=backroom,
                    qty_delta=qty,
                    source_kind="po_receipt",
                    source_doc_id=uuid4(),
                    lot_id=lot_id,
                    unit_cost=unit_cost,
                    actor_user_id=actor,
                    occurred_at=now,
                )
                counters.lots_created += 1
                counters.ledger_rows += 1


def _reset_tenant(sess: Session, tenant_id: UUID) -> None:
    """Delete only this tenant's seeded inventory data. Use with --reset."""
    tid = {"tid": str(tenant_id)}
    # Order matters: child tables first.
    for stmt in [
        "DELETE FROM inv.ledger WHERE tenant_id = :tid",
        "DELETE FROM inv.cost_layer WHERE tenant_id = :tid",
        "DELETE FROM inv.balance WHERE tenant_id = :tid",
        "DELETE FROM inv.serial WHERE tenant_id = :tid",
        "DELETE FROM inv.lot WHERE tenant_id = :tid",
        "DELETE FROM inv.sku WHERE tenant_id = :tid",
        "DELETE FROM inv.location WHERE tenant_id = :tid",
        "DELETE FROM inv.site WHERE tenant_id = :tid",
    ]:
        sess.execute(text(stmt), tid)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed dev inventory data.")
    parser.add_argument(
        "--tenant-id",
        type=UUID,
        default=DEFAULT_TENANT_ID,
        help="Target tenant UUID (default: dev tenant).",
    )
    parser.add_argument("--sku-count", type=int, default=500, help="Number of SKUs to create.")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for reproducibility.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete this tenant's existing inventory rows first.",
    )
    parser.add_argument("--confirm", action="store_true", help="Required: confirm intent to write.")
    args = parser.parse_args(argv)

    if not args.confirm:
        sys.stderr.write("Refusing to run without --confirm\n")
        return 2

    _check_safety_gate()
    rng = random.Random(args.seed)
    counters = Counters()

    SessionLocal = session_factory()
    sess = SessionLocal()
    try:
        _set_tenant(sess, args.tenant_id)
        if args.reset:
            _reset_tenant(sess, args.tenant_id)
        _seed_site_and_locations(sess, args.tenant_id, counters)
        _seed_skus(sess, args.tenant_id, args.sku_count, rng, counters)
        _stock_skus(sess, args.tenant_id, _refetch_locations(sess, args.tenant_id), rng, counters)
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()

    print(
        "Seed complete:"
        f" sites={counters.sites_created},"
        f" locations={counters.locations_created},"
        f" skus_created={counters.skus_created},"
        f" skus_skipped={counters.skus_skipped},"
        f" serials={counters.serials_created},"
        f" lots={counters.lots_created},"
        f" ledger_rows={counters.ledger_rows}"
    )
    return 0


def _refetch_locations(sess: Session, tenant_id: UUID) -> dict[str, UUID]:
    rows = sess.execute(
        text("SELECT code, id FROM inv.location WHERE tenant_id = :tid"),
        {"tid": str(tenant_id)},
    ).all()
    return {code: lid for code, lid in rows}


if __name__ == "__main__":
    raise SystemExit(main())
