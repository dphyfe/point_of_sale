"""consent schema: event ledger + state projection

Revision ID: 0013_consent
Revises: 0012_customer_audit_merge
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0013_consent"
down_revision: str | None = "0012_customer_audit_merge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RLS_TABLES = [
    ("consent", "event"),
    ("consent", "state"),
]


def _enable_rls(s: str, t: str) -> None:
    op.execute(f'ALTER TABLE "{s}"."{t}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{s}"."{t}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON "{s}"."{t}"
            USING (tenant_id = app_current_tenant())
            WITH CHECK (tenant_id = app_current_tenant());
        """
    )


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS "consent"')

    op.create_table(
        "event",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("cust.customer.id"), nullable=False),
        sa.Column("channel", sa.String(8), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("event_kind", sa.String(16), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("actor_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint("channel IN ('email','sms')", name="ck_consent_event_channel"),
        sa.CheckConstraint("purpose IN ('transactional','marketing')", name="ck_consent_event_purpose"),
        sa.CheckConstraint("event_kind IN ('opted_in','opted_out')", name="ck_consent_event_kind"),
        sa.CheckConstraint(
            "source IN ('pos','online_portal','support','provider_unsubscribe','import')",
            name="ck_consent_event_source",
        ),
        schema="consent",
    )
    op.create_index(
        "ix_consent_event_lookup",
        "event",
        ["tenant_id", "customer_id", "channel", "purpose", "occurred_at"],
        schema="consent",
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION consent.event_deny_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'consent.event is append-only (op=%)', TG_OP;
        END
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER consent_event_no_update BEFORE UPDATE OR DELETE ON consent.event
        FOR EACH ROW EXECUTE FUNCTION consent.event_deny_mutation();
        """
    )

    op.create_table(
        "state",
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("cust.customer.id"), nullable=False),
        sa.Column("channel", sa.String(8), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="unset"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_event_id", UUID(as_uuid=True), sa.ForeignKey("consent.event.id"), nullable=True),
        sa.PrimaryKeyConstraint(
            "tenant_id", "customer_id", "channel", "purpose", name="pk_consent_state"
        ),
        sa.CheckConstraint("channel IN ('email','sms')", name="ck_consent_state_channel"),
        sa.CheckConstraint("purpose IN ('transactional','marketing')", name="ck_consent_state_purpose"),
        sa.CheckConstraint(
            "state IN ('opted_in','opted_out','unset')", name="ck_consent_state_state"
        ),
        schema="consent",
    )

    for s, t in RLS_TABLES:
        _enable_rls(s, t)


def downgrade() -> None:
    for s, t in reversed(RLS_TABLES):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{s}"."{t}"')
    op.drop_table("state", schema="consent")
    op.execute("DROP TRIGGER IF EXISTS consent_event_no_update ON consent.event")
    op.execute("DROP FUNCTION IF EXISTS consent.event_deny_mutation()")
    op.drop_table("event", schema="consent")
    op.execute('DROP SCHEMA IF EXISTS "consent" CASCADE')
