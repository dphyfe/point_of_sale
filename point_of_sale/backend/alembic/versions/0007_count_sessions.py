"""count sessions

Revision ID: 0007_count_sessions
Revises: 0006_returns_and_rmas
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0007_count_sessions"
down_revision: str | None = "0006_returns_and_rmas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RLS_TABLES = [
    ("cnt", "count_session"),
    ("cnt", "count_session_snapshot"),
    ("cnt", "count_assignment"),
    ("cnt", "count_entry"),
]


def _enable_rls(s: str, t: str) -> None:
    op.execute(f'ALTER TABLE "{s}"."{t}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{s}"."{t}" FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY tenant_isolation ON "{s}"."{t}" USING (tenant_id = app_current_tenant()) WITH CHECK (tenant_id = app_current_tenant())')


def upgrade() -> None:
    op.create_table(
        "count_session",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("site_id", UUID(as_uuid=True), sa.ForeignKey("inv.site.id"), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("hide_system_qty", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("scope_kind", sa.String(16), nullable=False, server_default="full"),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("state IN ('open','submitted','approved','closed')", name="ck_count_state"),
        schema="cnt",
    )
    op.create_table(
        "count_session_snapshot",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("cnt.count_session.id"), nullable=False),
        sa.Column("sku_id", UUID(as_uuid=True), sa.ForeignKey("inv.sku.id"), nullable=False),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("inv.location.id"), nullable=False),
        sa.Column("on_hand_at_open", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.UniqueConstraint("session_id", "sku_id", "location_id", name="uq_snapshot_per_pair"),
        schema="cnt",
    )
    op.create_table(
        "count_assignment",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("cnt.count_session.id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("inv.location.id"), nullable=False),
        schema="cnt",
    )
    op.create_table(
        "count_entry",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("cnt.count_session.id"), nullable=False),
        sa.Column("sku_id", UUID(as_uuid=True), sa.ForeignKey("inv.sku.id"), nullable=False),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("inv.location.id"), nullable=False),
        sa.Column("counted_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("counter_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("serial_value", sa.String(64)),
        sa.Column("counted_at", sa.DateTime(timezone=True), nullable=False),
        schema="cnt",
    )
    for s, t in RLS_TABLES:
        _enable_rls(s, t)


def downgrade() -> None:
    for s, t in reversed(RLS_TABLES):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{s}"."{t}"')
        op.drop_table(t, schema=s)
