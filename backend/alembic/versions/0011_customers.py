"""customers + addresses + cust schema + RLS

Revision ID: 0011_customers
Revises: 0010_sku_merchandising_fields
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0011_customers"
down_revision: str | None = "0010_sku_merchandising_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RLS_TABLES = [
    ("cust", "customer"),
    ("cust", "customer_address"),
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
    op.execute('CREATE SCHEMA IF NOT EXISTS "cust"')

    op.create_table(
        "customer",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("client_request_id", UUID(as_uuid=True), nullable=True),
        sa.Column("external_loyalty_id", sa.Text(), nullable=True),
        sa.Column("external_crm_id", sa.Text(), nullable=True),
        sa.Column("contact_type", sa.String(16), nullable=False, server_default="individual"),
        sa.Column("first_name", sa.Text(), nullable=True),
        sa.Column("last_name", sa.Text(), nullable=True),
        sa.Column("company_name", sa.Text(), nullable=True),
        sa.Column("primary_phone", sa.Text(), nullable=True),
        sa.Column("secondary_phone", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("preferred_channel", sa.String(16), nullable=False, server_default="email"),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("tags", sa.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("tax_id", sa.Text(), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("state", sa.String(16), nullable=False, server_default="active"),
        sa.Column("merged_into", UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_by_user_id", UUID(as_uuid=True), nullable=True),
        # derived
        sa.Column("phone_normalized", sa.Text(), nullable=True),
        sa.Column("email_normalized", sa.Text(), nullable=True),
        sa.Column("display_name_lower", sa.Text(), nullable=True),
        sa.Column("search_vector", sa.dialects.postgresql.TSVECTOR(), nullable=True),
        sa.ForeignKeyConstraint(["merged_into"], ["cust.customer.id"], name="fk_customer_merged_into_customer"),
        sa.CheckConstraint("contact_type IN ('individual','company')", name="ck_customer_contact_type"),
        sa.CheckConstraint("preferred_channel IN ('email','sms','none')", name="ck_customer_preferred_channel"),
        sa.CheckConstraint("state IN ('active','inactive','merged','anonymized')", name="ck_customer_state"),
        sa.CheckConstraint(
            "(contact_type='individual' AND (first_name IS NOT NULL OR last_name IS NOT NULL))"
            " OR (contact_type='company' AND company_name IS NOT NULL)",
            name="ck_customer_minimal_name",
        ),
        sa.CheckConstraint(
            "primary_phone IS NOT NULL OR email IS NOT NULL",
            name="ck_customer_at_least_one_contact",
        ),
        sa.CheckConstraint(
            "(state <> 'merged') OR (merged_into IS NOT NULL)",
            name="ck_customer_merged_has_target",
        ),
        schema="cust",
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_customer_tenant_client_request_id
            ON cust.customer (tenant_id, client_request_id)
            WHERE client_request_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_customer_tenant_email_lower
            ON cust.customer (tenant_id, lower(email))
            WHERE email IS NOT NULL
        """
    )
    op.create_index("ix_customer_tenant_state", "customer", ["tenant_id", "state"], schema="cust")
    op.create_index("ix_customer_tenant_phone_norm", "customer", ["tenant_id", "phone_normalized"], schema="cust")
    op.create_index("ix_customer_tenant_email_norm", "customer", ["tenant_id", "email_normalized"], schema="cust")
    op.execute(
        """
        CREATE INDEX ix_customer_tenant_loyalty_lower
            ON cust.customer (tenant_id, lower(external_loyalty_id))
        """
    )
    op.execute(
        """
        CREATE INDEX ix_customer_search_vector
            ON cust.customer USING GIN (search_vector)
        """
    )

    # Trigger: maintain phone_normalized / email_normalized / display_name_lower / search_vector.
    # NOTE: phone normalization here is a digits-only fallback. Application code computes
    # E.164 form via the `phonenumbers` library and writes it into primary_phone-derived
    # caches when present; the trigger ensures a deterministic floor.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION cust.customer_normalize() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            NEW.email_normalized := CASE WHEN NEW.email IS NULL THEN NULL ELSE lower(btrim(NEW.email)) END;
            NEW.phone_normalized := CASE WHEN NEW.primary_phone IS NULL THEN NULL
                                         ELSE regexp_replace(NEW.primary_phone, '\\D', '', 'g') END;
            NEW.display_name_lower := lower(btrim(coalesce(
                nullif(btrim(coalesce(NEW.first_name,'') || ' ' || coalesce(NEW.last_name,'')), ''),
                NEW.company_name,
                ''
            )));
            NEW.search_vector :=
                  setweight(to_tsvector('simple', coalesce(NEW.display_name_lower, '')), 'A')
                || setweight(to_tsvector('simple', coalesce(NEW.email_normalized, '')), 'B')
                || setweight(to_tsvector('simple', coalesce(NEW.phone_normalized, '')), 'B')
                || setweight(to_tsvector('simple', coalesce(NEW.external_loyalty_id, '')), 'C')
                || setweight(to_tsvector('simple', coalesce(NEW.external_crm_id, '')), 'C');
            NEW.updated_at := now();
            RETURN NEW;
        END
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER customer_normalize_biud
            BEFORE INSERT OR UPDATE ON cust.customer
            FOR EACH ROW EXECUTE FUNCTION cust.customer_normalize();
        """
    )

    op.create_table(
        "customer_address",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "customer_id",
            UUID(as_uuid=True),
            sa.ForeignKey("cust.customer.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("is_default_for_kind", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("line1", sa.Text(), nullable=False),
        sa.Column("line2", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("postal_code", sa.Text(), nullable=True),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("kind IN ('billing','shipping','service')", name="ck_customer_address_kind"),
        schema="cust",
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_customer_address_default_per_kind
            ON cust.customer_address (tenant_id, customer_id, kind)
            WHERE is_default_for_kind
        """
    )
    op.create_index(
        "ix_customer_address_customer",
        "customer_address",
        ["tenant_id", "customer_id"],
        schema="cust",
    )

    for s, t in RLS_TABLES:
        _enable_rls(s, t)


def downgrade() -> None:
    for s, t in reversed(RLS_TABLES):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{s}"."{t}"')
    op.drop_table("customer_address", schema="cust")
    op.execute("DROP TRIGGER IF EXISTS customer_normalize_biud ON cust.customer")
    op.execute("DROP FUNCTION IF EXISTS cust.customer_normalize()")
    op.drop_table("customer", schema="cust")
    op.execute('DROP SCHEMA IF EXISTS "cust" CASCADE')
