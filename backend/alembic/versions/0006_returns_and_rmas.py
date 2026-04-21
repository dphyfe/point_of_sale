"""returns and vendor rmas

Revision ID: 0006_returns_and_rmas
Revises: 0005_purchase_orders
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0006_returns_and_rmas"
down_revision: str | None = "0005_purchase_orders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RLS_TABLES = [
    ("ret", "customer_return"),
    ("ret", "customer_return_line"),
    ("rma", "vendor_rma"),
    ("rma", "vendor_rma_line"),
]


def _enable_rls(s: str, t: str) -> None:
    op.execute(f'ALTER TABLE "{s}"."{t}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{s}"."{t}" FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY tenant_isolation ON "{s}"."{t}" USING (tenant_id = app_current_tenant()) WITH CHECK (tenant_id = app_current_tenant())')


def upgrade() -> None:
    op.create_table(
        "customer_return",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("original_sale_id", UUID(as_uuid=True), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("cashier_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("no_receipt", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("manager_approval_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("refund_method", sa.String(32), nullable=False, server_default="original"),
        sa.Column("refund_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "refund_method IN ('original','store_credit','cash')",
            name="ck_return_refund_method",
        ),
        schema="ret",
    )
    op.create_table(
        "customer_return_line",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("return_id", UUID(as_uuid=True), sa.ForeignKey("ret.customer_return.id"), nullable=False),
        sa.Column("sku_id", UUID(as_uuid=True), sa.ForeignKey("inv.sku.id"), nullable=False),
        sa.Column("qty", sa.Numeric(18, 3), nullable=False),
        sa.Column("serial_id", UUID(as_uuid=True), nullable=True),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("disposition", sa.String(32), nullable=False),
        sa.Column("target_location_id", UUID(as_uuid=True), sa.ForeignKey("inv.location.id"), nullable=False),
        sa.Column("refund_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "disposition IN ('sellable','hold','scrap','vendor_rma')",
            name="ck_return_disposition",
        ),
        schema="ret",
    )

    op.create_table(
        "vendor_rma",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", UUID(as_uuid=True), sa.ForeignKey("po.vendor.id"), nullable=False),
        sa.Column("originating_po_id", UUID(as_uuid=True), nullable=True),
        sa.Column("state", sa.String(32), nullable=False, server_default="open"),
        sa.Column("holding_location_id", UUID(as_uuid=True), sa.ForeignKey("inv.location.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("credit_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.CheckConstraint("state IN ('open','shipped','closed')", name="ck_rma_state"),
        schema="rma",
    )
    op.create_table(
        "vendor_rma_line",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("rma_id", UUID(as_uuid=True), sa.ForeignKey("rma.vendor_rma.id"), nullable=False),
        sa.Column("sku_id", UUID(as_uuid=True), sa.ForeignKey("inv.sku.id"), nullable=False),
        sa.Column("qty", sa.Numeric(18, 3), nullable=False),
        sa.Column("serial_id", UUID(as_uuid=True), nullable=True),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        schema="rma",
    )

    for s, t in RLS_TABLES:
        _enable_rls(s, t)


def downgrade() -> None:
    for s, t in reversed(RLS_TABLES):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{s}"."{t}"')
    op.drop_table("vendor_rma_line", schema="rma")
    op.drop_table("vendor_rma", schema="rma")
    op.drop_table("customer_return_line", schema="ret")
    op.drop_table("customer_return", schema="ret")
