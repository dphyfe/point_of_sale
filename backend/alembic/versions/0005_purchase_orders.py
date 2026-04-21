"""purchase orders + receipts

Revision ID: 0005_purchase_orders
Revises: 0004_audit_outbox
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0005_purchase_orders"
down_revision: str | None = "0004_audit_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RLS_TABLES = [
    ("po", "purchase_order"),
    ("po", "purchase_order_line"),
    ("po", "receipt"),
    ("po", "receipt_line"),
    ("po", "receipt_serial"),
]


def _enable_rls(schema: str, table: str) -> None:
    op.execute(f'ALTER TABLE "{schema}"."{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{schema}"."{table}" FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY tenant_isolation ON "{schema}"."{table}" USING (tenant_id = app_current_tenant()) WITH CHECK (tenant_id = app_current_tenant())')


def upgrade() -> None:
    op.create_table(
        "purchase_order",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", UUID(as_uuid=True), sa.ForeignKey("po.vendor.id"), nullable=False),
        sa.Column("po_number", sa.String(64), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("expected_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "po_number", name="uq_po_tenant_number"),
        sa.CheckConstraint(
            "state IN ('draft','submitted','approved','sent','receiving','closed','cancelled')",
            name="ck_po_state",
        ),
        schema="po",
    )
    op.create_table(
        "purchase_order_line",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("po_id", UUID(as_uuid=True), sa.ForeignKey("po.purchase_order.id"), nullable=False),
        sa.Column("sku_id", UUID(as_uuid=True), sa.ForeignKey("inv.sku.id"), nullable=False),
        sa.Column("ordered_qty", sa.Numeric(18, 3), nullable=False),
        sa.Column("received_qty", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("backordered_qty", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False),
        schema="po",
    )
    op.create_index("ix_po_line_po", "purchase_order_line", ["tenant_id", "po_id"], schema="po")

    op.create_table(
        "receipt",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("po_id", UUID(as_uuid=True), sa.ForeignKey("po.purchase_order.id"), nullable=False),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("inv.location.id"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("received_by", UUID(as_uuid=True), nullable=False),
        schema="po",
    )

    op.create_table(
        "receipt_line",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("receipt_id", UUID(as_uuid=True), sa.ForeignKey("po.receipt.id"), nullable=False),
        sa.Column("po_line_id", UUID(as_uuid=True), sa.ForeignKey("po.purchase_order_line.id"), nullable=False),
        sa.Column("received_qty", sa.Numeric(18, 3), nullable=False),
        sa.Column("overage_qty", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("lot_code", sa.String(64), nullable=True),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False),
        schema="po",
    )

    op.create_table(
        "receipt_serial",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("receipt_line_id", UUID(as_uuid=True), sa.ForeignKey("po.receipt_line.id"), nullable=False),
        sa.Column("serial_value", sa.String(255), nullable=False),
        schema="po",
    )

    for s, t in RLS_TABLES:
        _enable_rls(s, t)


def downgrade() -> None:
    for s, t in reversed(RLS_TABLES):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{s}"."{t}"')
    op.drop_table("receipt_serial", schema="po")
    op.drop_table("receipt_line", schema="po")
    op.drop_table("receipt", schema="po")
    op.drop_table("purchase_order_line", schema="po")
    op.drop_table("purchase_order", schema="po")
