"""locations and skus + RLS

Revision ID: 0002_locations_and_skus
Revises: 0001_init_schemas
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0002_locations_and_skus"
down_revision: str | None = "0001_init_schemas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RLS_TABLES = [
    ("inv", "site"),
    ("inv", "location"),
    ("inv", "sku"),
    ("po", "vendor"),
]


def _enable_rls(schema: str, table: str) -> None:
    op.execute(f'ALTER TABLE "{schema}"."{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{schema}"."{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON "{schema}"."{table}"
            USING (tenant_id = app_current_tenant())
            WITH CHECK (tenant_id = app_current_tenant());
        """
    )


def upgrade() -> None:
    op.create_table(
        "site",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "code", name="uq_site_tenant_code"),
        schema="inv",
    )
    op.create_index("ix_site_tenant", "site", ["tenant_id"], schema="inv")

    op.create_table(
        "location",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", UUID(as_uuid=True), sa.ForeignKey("inv.site.id"), nullable=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False, server_default="physical"),
        sa.Column("restrict_to_home_location", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "code", name="uq_location_tenant_code"),
        sa.CheckConstraint("kind IN ('physical','virtual_in_transit')", name="ck_location_kind"),
        schema="inv",
    )
    op.create_index("ix_location_tenant", "location", ["tenant_id"], schema="inv")

    op.create_table(
        "sku",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("sku_code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("tracking", sa.String(32), nullable=False, server_default="non_serialized"),
        sa.Column("over_receive_tolerance_pct", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "sku_code", name="uq_sku_tenant_code"),
        sa.CheckConstraint("tracking IN ('non_serialized','serialized','lot_tracked')", name="ck_sku_tracking"),
        schema="inv",
    )
    op.create_index("ix_sku_tenant", "sku", ["tenant_id"], schema="inv")

    op.create_table(
        "vendor",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "code", name="uq_vendor_tenant_code"),
        schema="po",
    )
    op.create_index("ix_vendor_tenant", "vendor", ["tenant_id"], schema="po")

    for s, t in RLS_TABLES:
        _enable_rls(s, t)


def downgrade() -> None:
    for s, t in reversed(RLS_TABLES):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{s}"."{t}"')
    op.drop_table("vendor", schema="po")
    op.drop_table("sku", schema="inv")
    op.drop_table("location", schema="inv")
    op.drop_table("site", schema="inv")
