"""link customer_id (nullable) to existing transaction tables

Revision ID: 0015_link_customer_to_sales
Revises: 0014_messaging
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0015_link_customer_to_sales"
down_revision: str | None = "0014_messaging"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Tables that always exist in this codebase
KNOWN = [
    ("ret", "customer_return", "occurred_at"),
]
# Tables that may not yet exist (added by future features)
OPTIONAL = [
    ("ret", "exchange", "occurred_at"),
    ("sales", "sale_transaction", "occurred_at"),
    ("svc", "service_order", "occurred_at"),
]


def _add_optional(s: str, t: str, occurred_col: str) -> None:
    # idempotent / table-presence guarded
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = '{s}' AND table_name = '{t}'
            ) THEN
                EXECUTE 'ALTER TABLE "{s}"."{t}" ADD COLUMN IF NOT EXISTS customer_id uuid NULL';
                EXECUTE 'ALTER TABLE "{s}"."{t}"
                          ADD CONSTRAINT fk_{t}_customer_id_customer
                          FOREIGN KEY (customer_id) REFERENCES cust.customer(id)';
                EXECUTE 'CREATE INDEX IF NOT EXISTS ix_{t}_customer_time
                          ON "{s}"."{t}" (tenant_id, customer_id, {occurred_col} DESC)';
            END IF;
        END
        $$;
        """
    )


def _drop_optional(s: str, t: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = '{s}' AND table_name = '{t}'
            ) THEN
                EXECUTE 'DROP INDEX IF EXISTS "{s}".ix_{t}_customer_time';
                EXECUTE 'ALTER TABLE "{s}"."{t}" DROP CONSTRAINT IF EXISTS fk_{t}_customer_id_customer';
                EXECUTE 'ALTER TABLE "{s}"."{t}" DROP COLUMN IF EXISTS customer_id';
            END IF;
        END
        $$;
        """
    )


def upgrade() -> None:
    for s, t, occurred in KNOWN:
        op.add_column(t, sa.Column("customer_id", UUID(as_uuid=True), nullable=True), schema=s)
        op.create_foreign_key(
            f"fk_{t}_customer_id_customer",
            t,
            "customer",
            ["customer_id"],
            ["id"],
            source_schema=s,
            referent_schema="cust",
        )
        op.create_index(
            f"ix_{t}_customer_time",
            t,
            ["tenant_id", "customer_id", occurred],
            schema=s,
        )

    for s, t, occurred in OPTIONAL:
        _add_optional(s, t, occurred)


def downgrade() -> None:
    for s, t, _ in OPTIONAL:
        _drop_optional(s, t)

    for s, t, _ in KNOWN:
        op.drop_index(f"ix_{t}_customer_time", table_name=t, schema=s)
        op.drop_constraint(f"fk_{t}_customer_id_customer", t, schema=s, type_="foreignkey")
        op.drop_column(t, "customer_id", schema=s)
