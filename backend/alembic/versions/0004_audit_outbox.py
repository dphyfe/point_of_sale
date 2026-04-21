"""audit + outbox

Revision ID: 0004_audit_outbox
Revises: 0003_inventory_ledger
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0004_audit_outbox"
down_revision: str | None = "0003_inventory_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_entry",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("target_kind", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("before_state", JSONB, nullable=True),
        sa.Column("after_state", JSONB, nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="audit",
    )
    op.create_index("ix_audit_tenant_target", "audit_entry", ["tenant_id", "target_kind", "target_id"], schema="audit")

    # Append-only
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit.audit_deny_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit.audit_entry is append-only (op=%)', TG_OP;
        END
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_no_update BEFORE UPDATE OR DELETE ON audit.audit_entry
        FOR EACH ROW EXECUTE FUNCTION audit.audit_deny_mutation();
        """
    )

    op.create_table(
        "event",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        schema="outbox",
    )
    op.create_index("ix_outbox_status", "event", ["status", "occurred_at"], schema="outbox")


def downgrade() -> None:
    op.drop_table("event", schema="outbox")
    op.execute("DROP TRIGGER IF EXISTS audit_no_update ON audit.audit_entry")
    op.execute("DROP FUNCTION IF EXISTS audit.audit_deny_mutation()")
    op.drop_table("audit_entry", schema="audit")
