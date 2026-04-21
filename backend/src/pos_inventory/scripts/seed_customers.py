"""Idempotent additive seed for customer-view dev/staging data (US3).

Mirrors `seed_dev.py` patterns: refuses to run unless `POS_INVENTORY_AUTH_BYPASS`
or `POS_INVENTORY_ALLOW_SEED` is set. Inserts are keyed by
`(tenant_id, client_request_id)` so re-runs are safe.

Usage:

    POS_INVENTORY_AUTH_BYPASS=true python -m pos_inventory.scripts.seed_customers \\
        --customer-count 50000

    # additive top-up (does not delete):
    POS_INVENTORY_AUTH_BYPASS=true python -m pos_inventory.scripts.seed_customers \\
        --customer-add 1000 --with-consent-defaults
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.config import get_settings
from pos_inventory.core.db import session_factory

DEFAULT_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


@dataclass
class Counters:
    customers_created: int = 0
    customers_skipped: int = 0
    consent_states_inserted: int = 0
    return_links_set: int = 0
    new_ids: list[UUID] = field(default_factory=list)


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
    sess.execute(
        text("SELECT set_config('app.current_tenant', :tid, false)"),
        {"tid": str(tenant_id)},
    )


def _current_count(sess: Session, tenant_id: UUID) -> int:
    return int(
        sess.execute(
            text("SELECT count(*) FROM cust.customer WHERE tenant_id = :tid"),
            {"tid": str(tenant_id)},
        ).scalar_one()
    )


def _seed_customers(
    sess: Session, tenant_id: UUID, n_to_create: int, rng: random.Random, counters: Counters
) -> None:
    from faker import Faker

    faker = Faker()
    Faker.seed(rng.randint(0, 2**31 - 1))
    now = datetime.now(timezone.utc)

    for _ in range(n_to_create):
        cid = uuid4()
        crid = uuid4()  # idempotency key per insert
        contact_type = "individual" if rng.random() > 0.05 else "company"
        first = faker.first_name() if contact_type == "individual" else None
        last = faker.last_name() if contact_type == "individual" else None
        company = faker.company() if contact_type == "company" else None
        email = faker.unique.email()
        phone = faker.unique.msisdn()
        res = sess.execute(
            text(
                """
                INSERT INTO cust.customer
                    (id, tenant_id, client_request_id, contact_type, first_name, last_name,
                     company_name, email, primary_phone, preferred_channel, tags,
                     state, version, created_at, updated_at)
                VALUES
                    (:id, :tid, :crid, :ct, :fn, :ln, :co, :em, :ph, 'email', '{}'::text[],
                     'active', 1, :ts, :ts)
                ON CONFLICT (tenant_id, client_request_id) DO NOTHING
                RETURNING id
                """
            ),
            {
                "id": str(cid),
                "tid": str(tenant_id),
                "crid": str(crid),
                "ct": contact_type,
                "fn": first,
                "ln": last,
                "co": company,
                "em": email,
                "ph": phone,
                "ts": now,
            },
        ).first()
        if res is None:
            counters.customers_skipped += 1
            continue
        counters.customers_created += 1
        counters.new_ids.append(cid)


def _seed_consent_defaults(sess: Session, tenant_id: UUID, ids: list[UUID], counters: Counters) -> None:
    if not ids:
        return
    now = datetime.now(timezone.utc)
    for cid in ids:
        for channel in ("email", "sms"):
            for purpose, default in (("transactional", "opted_in"), ("marketing", "unset")):
                sess.execute(
                    text(
                        """
                        INSERT INTO consent.state
                            (tenant_id, customer_id, channel, purpose, state, effective_at, source)
                        VALUES (:tid, :cid, :ch, :pu, :st, :ts, 'pos')
                        ON CONFLICT (tenant_id, customer_id, channel, purpose) DO NOTHING
                        """
                    ),
                    {
                        "tid": str(tenant_id),
                        "cid": str(cid),
                        "ch": channel,
                        "pu": purpose,
                        "st": default,
                        "ts": now,
                    },
                )
                counters.consent_states_inserted += 1


def _link_random_returns(
    sess: Session, tenant_id: UUID, ids: list[UUID], rng: random.Random, counters: Counters
) -> None:
    """Best-effort: attach a random subset of newly-created customers to existing
    `ret.customer_return` rows that don't yet have a customer_id, so transaction
    history has data to display."""
    if not ids:
        return
    free_returns = sess.execute(
        text(
            """
            SELECT id FROM ret.customer_return
             WHERE tenant_id = :tid AND customer_id IS NULL
             LIMIT 200
            """
        ),
        {"tid": str(tenant_id)},
    ).all()
    for (rid,) in free_returns:
        cid = rng.choice(ids)
        sess.execute(
            text(
                "UPDATE ret.customer_return SET customer_id=:cid WHERE id=:rid AND tenant_id=:tid"
            ),
            {"cid": str(cid), "rid": str(rid), "tid": str(tenant_id)},
        )
        counters.return_links_set += 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Idempotent customer seed for dev/staging.")
    parser.add_argument("--tenant-id", default=str(DEFAULT_TENANT_ID))
    parser.add_argument(
        "--customer-count",
        type=int,
        default=None,
        help="Target total customers for tenant; only top-up is created.",
    )
    parser.add_argument(
        "--customer-add",
        type=int,
        default=None,
        help="Number of customers to additionally create (regardless of current count).",
    )
    parser.add_argument("--with-consent-defaults", action="store_true")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()

    if not args.confirm:
        sys.stderr.write("Pass --confirm to proceed.\n")
        sys.exit(2)
    _check_safety_gate()

    tenant_id = UUID(args.tenant_id)
    rng = random.Random(args.seed if args.seed is not None else 42)

    sf = session_factory()
    counters = Counters()
    with sf() as sess:
        _set_tenant(sess, tenant_id)
        existing = _current_count(sess, tenant_id)
        n_to_create = 0
        if args.customer_count is not None:
            n_to_create = max(0, args.customer_count - existing)
        if args.customer_add is not None:
            n_to_create += max(0, args.customer_add)
        _seed_customers(sess, tenant_id, n_to_create, rng, counters)
        if args.with_consent_defaults:
            _seed_consent_defaults(sess, tenant_id, counters.new_ids, counters)
        _link_random_returns(sess, tenant_id, counters.new_ids, rng, counters)
        sess.commit()

    print(
        f"customers_created={counters.customers_created} "
        f"customers_skipped={counters.customers_skipped} "
        f"consent_states={counters.consent_states_inserted} "
        f"return_links={counters.return_links_set}"
    )


if __name__ == "__main__":
    main()
