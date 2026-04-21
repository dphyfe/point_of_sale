"""msg schema: template + message + status events + outbox

Revision ID: 0014_messaging
Revises: 0013_consent
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0014_messaging"
down_revision: str | None = "0013_consent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RLS_TABLES = [
    ("msg", "template"),
    ("msg", "message"),
    ("msg", "message_status_event"),
    ("msg", "outbox"),
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
    op.execute('CREATE SCHEMA IF NOT EXISTS "msg"')

    op.create_table(
        "template",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("channel", sa.String(8), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("subject_template", sa.Text(), nullable=True),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "code", name="uq_template_tenant_code"),
        sa.CheckConstraint("channel IN ('email','sms')", name="ck_template_channel"),
        sa.CheckConstraint("purpose IN ('transactional','marketing')", name="ck_template_purpose"),
        sa.CheckConstraint(
            "(channel='email' AND subject_template IS NOT NULL) OR channel='sms'",
            name="ck_template_email_subject_required",
        ),
        schema="msg",
    )

    op.create_table(
        "message",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("client_request_id", UUID(as_uuid=True), nullable=True),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("cust.customer.id"), nullable=False),
        sa.Column("template_id", UUID(as_uuid=True), sa.ForeignKey("msg.template.id"), nullable=True),
        sa.Column("channel", sa.String(8), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("to_address", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("related_transaction_id", UUID(as_uuid=True), nullable=True),
        sa.Column("related_transaction_kind", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("provider_message_id", sa.Text(), nullable=True),
        sa.Column("sent_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("channel IN ('email','sms')", name="ck_message_channel"),
        sa.CheckConstraint("purpose IN ('transactional','marketing')", name="ck_message_purpose"),
        sa.CheckConstraint(
            "status IN ('queued','sent','delivered','bounced','failed','retrying')",
            name="ck_message_status",
        ),
        sa.CheckConstraint(
            "(channel='email' AND subject IS NOT NULL) OR channel='sms'",
            name="ck_message_email_subject_required",
        ),
        schema="msg",
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_message_tenant_client_request_id
            ON msg.message (tenant_id, client_request_id)
            WHERE client_request_id IS NOT NULL
        """
    )
    op.create_index(
        "ix_message_customer_time",
        "message",
        ["tenant_id", "customer_id", "created_at"],
        schema="msg",
    )
    op.create_index("ix_message_status", "message", ["tenant_id", "status"], schema="msg")

    op.create_table(
        "message_status_event",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", UUID(as_uuid=True), sa.ForeignKey("msg.message.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("provider_event_id", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued','sent','delivered','bounced','failed','retrying')",
            name="ck_message_status_event_status",
        ),
        schema="msg",
    )
    op.create_index(
        "ix_message_status_event_message",
        "message_status_event",
        ["tenant_id", "message_id", "occurred_at"],
        schema="msg",
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION msg.message_status_event_deny_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'msg.message_status_event is append-only (op=%)', TG_OP;
        END
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER message_status_event_no_update
            BEFORE UPDATE OR DELETE ON msg.message_status_event
            FOR EACH ROW EXECUTE FUNCTION msg.message_status_event_deny_mutation();
        """
    )

    op.create_table(
        "outbox",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("event_kind", sa.String(64), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "event_kind IN ('customer_message.send','customer_message.retry')",
            name="ck_msg_outbox_event_kind",
        ),
        schema="msg",
    )
    op.create_index(
        "ix_msg_outbox_pending",
        "outbox",
        ["tenant_id", "created_at"],
        schema="msg",
        postgresql_where=sa.text("dispatched_at IS NULL"),
    )

    for s, t in RLS_TABLES:
        _enable_rls(s, t)


def downgrade() -> None:
    for s, t in reversed(RLS_TABLES):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{s}"."{t}"')
    op.drop_table("outbox", schema="msg")
    op.execute("DROP TRIGGER IF EXISTS message_status_event_no_update ON msg.message_status_event")
    op.execute("DROP FUNCTION IF EXISTS msg.message_status_event_deny_mutation()")
    op.drop_table("message_status_event", schema="msg")
    op.drop_table("message", schema="msg")
    op.drop_table("template", schema="msg")
    op.execute('DROP SCHEMA IF EXISTS "msg" CASCADE')
