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
from datetime import datetime, timedelta, timezone
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

# PO lifecycle distribution. Transition timestamps are filled in to match
# the chosen terminal state so the data looks realistic.
PO_STATE_WEIGHTS = [
    ("draft", 25),
    ("submitted", 10),
    ("approved", 15),
    ("sent", 20),
    ("receiving", 10),
    ("closed", 15),
    ("cancelled", 5),
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
    vendors_created: int = 0
    pos_created: int = 0
    po_lines_created: int = 0
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
    # The inv.ledger table has an append-only trigger; bypass it for this
    # reset transaction. Requires the connecting role to have permission to
    # set session_replication_role (true for the dev `postgres` superuser).
    sess.execute(text("SET LOCAL session_replication_role = 'replica'"))
    # Order matters: child tables first.
    for stmt in [
        "DELETE FROM po.receipt_serial WHERE tenant_id = :tid",
        "DELETE FROM po.receipt_line WHERE tenant_id = :tid",
        "DELETE FROM po.receipt WHERE tenant_id = :tid",
        "DELETE FROM po.purchase_order_line WHERE tenant_id = :tid",
        "DELETE FROM po.purchase_order WHERE tenant_id = :tid",
        "DELETE FROM po.vendor WHERE tenant_id = :tid",
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
    parser.add_argument(
        "--vendor-count", type=int, default=25, help="Number of vendors to create."
    )
    parser.add_argument(
        "--po-count",
        type=int,
        default=2000,
        help="Target total number of purchase orders (idempotent; tops up to this count).",
    )
    parser.add_argument(
        "--po-add",
        type=int,
        default=0,
        help="Add this many additional purchase orders on top of whatever exists. Overrides --po-count when > 0.",
    )
    parser.add_argument(
        "--po-max-lines",
        type=int,
        default=12,
        help="Maximum number of lines per generated purchase order.",
    )
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
        _seed_vendors(sess, args.tenant_id, args.vendor_count, rng, counters)
        _seed_purchase_orders(
            sess,
            tenant_id=args.tenant_id,
            po_count=args.po_count,
            po_add=args.po_add,
            max_lines=args.po_max_lines,
            rng=rng,
            counters=counters,
        )
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
        f" ledger_rows={counters.ledger_rows},"
        f" vendors={counters.vendors_created},"
        f" purchase_orders={counters.pos_created},"
        f" po_lines={counters.po_lines_created}"
    )
    return 0


def _refetch_locations(sess: Session, tenant_id: UUID) -> dict[str, UUID]:
    rows = sess.execute(
        text("SELECT code, id FROM inv.location WHERE tenant_id = :tid"),
        {"tid": str(tenant_id)},
    ).all()
    return {code: lid for code, lid in rows}


def _seed_vendors(
    sess: Session,
    tenant_id: UUID,
    vendor_count: int,
    rng: random.Random,
    counters: Counters,
) -> None:
    if vendor_count <= 0:
        return
    from faker import Faker

    faker = Faker()
    Faker.seed(rng.randint(0, 2**31 - 1))

    rows = []
    seen_names: set[str] = set()
    for i in range(vendor_count):
        name = faker.company()
        for _ in range(20):
            if name not in seen_names:
                break
            name = faker.company()
        seen_names.add(name)
        rows.append(
            {
                "id": str(uuid4()),
                "tid": str(tenant_id),
                "code": f"VEND-{i + 1:04d}",
                "name": name,
            }
        )

    result = sess.execute(
        text(
            """
            INSERT INTO po.vendor (id, tenant_id, code, name)
            VALUES (:id, :tid, :code, :name)
            ON CONFLICT (tenant_id, code) DO NOTHING
            """
        ),
        rows,
    )
    counters.vendors_created += max(result.rowcount or 0, 0)


def _seed_purchase_orders(
    sess: Session,
    *,
    tenant_id: UUID,
    po_count: int,
    po_add: int = 0,
    max_lines: int,
    rng: random.Random,
    counters: Counters,
) -> None:
    if po_count <= 0 and po_add <= 0:
        return

    vendor_ids: list[UUID] = [
        row[0]
        for row in sess.execute(
            text("SELECT id FROM po.vendor WHERE tenant_id = :tid"),
            {"tid": str(tenant_id)},
        ).all()
    ]
    sku_ids: list[UUID] = [
        row[0]
        for row in sess.execute(
            text("SELECT id FROM inv.sku WHERE tenant_id = :tid"),
            {"tid": str(tenant_id)},
        ).all()
    ]
    if not vendor_ids or not sku_ids:
        return

    # `--po-count` is the desired *total* (idempotent top-up). `--po-add`,
    # when > 0, instead means "create N additional POs on top of whatever
    # already exists". Skip already-used po_numbers either way.
    existing_numbers: set[str] = {
        row[0]
        for row in sess.execute(
            text("SELECT po_number FROM po.purchase_order WHERE tenant_id = :tid"),
            {"tid": str(tenant_id)},
        ).all()
    }
    if po_add > 0:
        remaining = po_add
    else:
        remaining = po_count - len(existing_numbers)
    if remaining <= 0:
        return

    states = [s for s, _ in PO_STATE_WEIGHTS]
    weights = [w for _, w in PO_STATE_WEIGHTS]
    actor = DEFAULT_USER_ID
    now = datetime.now(timezone.utc)
    max_lines = max(1, max_lines)

    po_rows: list[dict] = []
    line_rows: list[dict] = []

    next_seq = 1
    while len(po_rows) < remaining:
        po_number = f"PO-{next_seq:06d}"
        next_seq += 1
        if po_number in existing_numbers:
            continue

        pid = uuid4()
        vendor_id = rng.choice(vendor_ids)
        created_at = now - timedelta(
            days=rng.randint(0, 180),
            hours=rng.randint(0, 23),
            minutes=rng.randint(0, 59),
        )
        state = rng.choices(states, weights=weights, k=1)[0]
        ts = _po_timestamps(state, created_at, rng)

        line_count = rng.randint(1, max_lines)
        chosen_skus = rng.sample(sku_ids, k=min(line_count, len(sku_ids)))
        expected_total = Decimal("0")
        for sku_id in chosen_skus:
            ordered_qty = Decimal(rng.randint(1, 50))
            unit_cost = Decimal(f"{rng.uniform(0.50, 250.00):.4f}")
            expected_total += ordered_qty * unit_cost
            received_qty = Decimal("0")
            if state == "closed":
                received_qty = ordered_qty
            elif state == "receiving":
                received_qty = Decimal(rng.randint(0, int(ordered_qty)))
            backordered_qty = ordered_qty - received_qty
            line_rows.append(
                {
                    "id": str(uuid4()),
                    "tid": str(tenant_id),
                    "pid": str(pid),
                    "sid": str(sku_id),
                    "oq": ordered_qty,
                    "rq": received_qty,
                    "bq": backordered_qty,
                    "uc": unit_cost,
                }
            )

        po_rows.append(
            {
                "id": str(pid),
                "tid": str(tenant_id),
                "vid": str(vendor_id),
                "pn": po_number,
                "state": state,
                "etot": expected_total.quantize(Decimal("0.01")),
                "uid": str(actor),
                "created_at": created_at,
                "submitted_at": ts["submitted_at"],
                "approved_at": ts["approved_at"],
                "sent_at": ts["sent_at"],
                "closed_at": ts["closed_at"],
                "cancelled_at": ts["cancelled_at"],
            }
        )

    _bulk_insert(
        sess,
        """
        INSERT INTO po.purchase_order
            (id, tenant_id, vendor_id, po_number, state, expected_total,
             created_by, created_at, submitted_at, approved_at, sent_at,
             closed_at, cancelled_at)
        VALUES
            (:id, :tid, :vid, :pn, :state, :etot,
             :uid, :created_at, :submitted_at, :approved_at, :sent_at,
             :closed_at, :cancelled_at)
        ON CONFLICT (tenant_id, po_number) DO NOTHING
        """,
        po_rows,
        chunk_size=500,
    )
    _bulk_insert(
        sess,
        """
        INSERT INTO po.purchase_order_line
            (id, tenant_id, po_id, sku_id, ordered_qty, received_qty,
             backordered_qty, unit_cost)
        VALUES (:id, :tid, :pid, :sid, :oq, :rq, :bq, :uc)
        """,
        line_rows,
        chunk_size=1000,
    )
    counters.pos_created += len(po_rows)
    counters.po_lines_created += len(line_rows)


def _po_timestamps(
    state: str, created_at: datetime, rng: random.Random
) -> dict[str, datetime | None]:
    """Fill lifecycle timestamps consistent with the terminal state."""
    ts: dict[str, datetime | None] = {
        "submitted_at": None,
        "approved_at": None,
        "sent_at": None,
        "closed_at": None,
        "cancelled_at": None,
    }
    if state == "draft":
        return ts
    if state == "cancelled":
        ts["cancelled_at"] = created_at + timedelta(hours=rng.randint(1, 48))
        return ts
    cursor = created_at + timedelta(hours=rng.randint(1, 12))
    ts["submitted_at"] = cursor
    if state == "submitted":
        return ts
    cursor += timedelta(hours=rng.randint(1, 24))
    ts["approved_at"] = cursor
    if state == "approved":
        return ts
    cursor += timedelta(hours=rng.randint(1, 24))
    ts["sent_at"] = cursor
    if state in ("sent", "receiving"):
        return ts
    # closed
    cursor += timedelta(days=rng.randint(1, 14))
    ts["closed_at"] = cursor
    return ts


def _bulk_insert(
    sess: Session, sql: str, rows: list[dict], *, chunk_size: int
) -> None:
    if not rows:
        return
    stmt = text(sql)
    for start in range(0, len(rows), chunk_size):
        sess.execute(stmt, rows[start : start + chunk_size])


if __name__ == "__main__":
    raise SystemExit(main())
