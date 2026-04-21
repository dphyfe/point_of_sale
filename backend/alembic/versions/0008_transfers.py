"""transfers

Revision ID: 0008_transfers
Revises: 0007_count_sessions
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0008_transfers"
down_revision: str | None = "0007_count_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RLS_TABLES = [("xfr", "transfer"), ("xfr", "transfer_line"), ("xfr", "transfer_serial")]


def _enable_rls(s: str, t: str) -> None:
    op.execute(f'ALTER TABLE "{s}"."{t}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{s}"."{t}" FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY tenant_isolation ON "{s}"."{t}" USING (tenant_id = app_current_tenant()) WITH CHECK (tenant_id = app_current_tenant())')


def upgrade() -> None:
    op.create_table(
        "transfer",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("source_location_id", UUID(as_uuid=True), sa.ForeignKey("inv.location.id"), nullable=False),
        sa.Column("destination_location_id", UUID(as_uuid=True), sa.ForeignKey("inv.location.id"), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shipped_at", sa.DateTime(timezone=True)),
        sa.Column("received_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("state IN ('draft','shipped','received','cancelled')", name="ck_transfer_state"),
        schema="xfr",
    )
    op.create_table(
        "transfer_line",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("transfer_id", UUID(as_uuid=True), sa.ForeignKey("xfr.transfer.id"), nullable=False),
        sa.Column("sku_id", UUID(as_uuid=True), sa.ForeignKey("inv.sku.id"), nullable=False),
        sa.Column("qty", sa.Numeric(18, 4), nullable=False),
        sa.CheckConstraint("qty > 0", name="ck_transfer_line_qty_pos"),
        schema="xfr",
    )
    op.create_table(
        "transfer_serial",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("transfer_line_id", UUID(as_uuid=True), sa.ForeignKey("xfr.transfer_line.id"), nullable=False),
        sa.Column("serial_id", UUID(as_uuid=True), sa.ForeignKey("inv.serial.id"), nullable=False),
        sa.UniqueConstraint("transfer_line_id", "serial_id", name="uq_transfer_serial"),
        schema="xfr",
    )
    for s, t in RLS_TABLES:
        _enable_rls(s, t)


def downgrade() -> None:
    for s, t in reversed(RLS_TABLES):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{s}"."{t}"')
        op.drop_table(t, schema=s)
