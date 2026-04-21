"""customer profile_change (append-only) + merge audit

Revision ID: 0012_customer_audit_merge
Revises: 0011_customers
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0012_customer_audit_merge"
down_revision: str | None = "0011_customers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RLS_TABLES = [
    ("cust", "profile_change"),
    ("cust", "merge"),
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
    op.create_table(
        "profile_change",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "customer_id",
            UUID(as_uuid=True),
            sa.ForeignKey("cust.customer.id"),
            nullable=False,
        ),
        sa.Column("actor_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("change_kind", sa.String(16), nullable=False),
        sa.CheckConstraint(
            "change_kind IN ('update','merge','deactivate','reactivate','anonymize')",
            name="ck_profile_change_kind",
        ),
        schema="cust",
    )
    op.create_index(
        "ix_profile_change_customer_time",
        "profile_change",
        ["tenant_id", "customer_id", "occurred_at"],
        schema="cust",
    )
    # Append-only enforcement
    op.execute(
        """
        CREATE OR REPLACE FUNCTION cust.profile_change_deny_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'cust.profile_change is append-only (op=%)', TG_OP;
        END
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER profile_change_no_update BEFORE UPDATE OR DELETE ON cust.profile_change
        FOR EACH ROW EXECUTE FUNCTION cust.profile_change_deny_mutation();
        """
    )

    op.create_table(
        "merge",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("survivor_id", UUID(as_uuid=True), sa.ForeignKey("cust.customer.id"), nullable=False),
        sa.Column("merged_away_id", UUID(as_uuid=True), sa.ForeignKey("cust.customer.id"), nullable=False),
        sa.Column("performed_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.CheckConstraint("survivor_id <> merged_away_id", name="ck_merge_distinct"),
        sa.UniqueConstraint("tenant_id", "merged_away_id", name="uq_merge_tenant_merged_away"),
        schema="cust",
    )

    for s, t in RLS_TABLES:
        _enable_rls(s, t)


def downgrade() -> None:
    for s, t in reversed(RLS_TABLES):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{s}"."{t}"')
    op.drop_table("merge", schema="cust")
    op.execute("DROP TRIGGER IF EXISTS profile_change_no_update ON cust.profile_change")
    op.execute("DROP FUNCTION IF EXISTS cust.profile_change_deny_mutation()")
    op.drop_table("profile_change", schema="cust")
