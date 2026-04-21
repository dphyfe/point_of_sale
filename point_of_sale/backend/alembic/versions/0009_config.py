"""tenant config

Revision ID: 0009_config
Revises: 0008_transfers
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0009_config"
down_revision: str | None = "0008_transfers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_config",
        sa.Column("tenant_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("over_receive_tolerance_pct", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("no_receipt_returns_enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("extras", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_by", UUID(as_uuid=True)),
        schema="inv",
    )
    op.execute('ALTER TABLE "inv"."tenant_config" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "inv"."tenant_config" FORCE ROW LEVEL SECURITY')
    op.execute('CREATE POLICY tenant_isolation ON "inv"."tenant_config" USING (tenant_id = app_current_tenant()) WITH CHECK (tenant_id = app_current_tenant())')


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "inv"."tenant_config"')
    op.drop_table("tenant_config", schema="inv")
