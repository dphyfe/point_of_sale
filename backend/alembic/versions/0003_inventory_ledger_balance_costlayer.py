"""inventory ledger, balance, cost layer, serial, lot, adjustment

Revision ID: 0003_inventory_ledger
Revises: 0002_locations_and_skus
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0003_inventory_ledger"
down_revision: str | None = "0002_locations_and_skus"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RLS_TABLES = [
    ("inv", "serial"),
    ("inv", "lot"),
    ("inv", "balance"),
    ("inv", "ledger"),
    ("inv", "cost_layer"),
    ("inv", "adjustment"),
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
        "serial",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("sku_id", UUID(as_uuid=True), sa.ForeignKey("inv.sku.id"), nullable=False),
        sa.Column("serial_value", sa.String(255), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="received"),
        sa.Column("current_location_id", UUID(as_uuid=True), sa.ForeignKey("inv.location.id"), nullable=True),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "serial_value", name="uq_serial_tenant_value"),
        sa.CheckConstraint(
            "state IN ('received','sellable','reserved','sold','returned','rma_pending','rma_closed','scrapped','in_transit')",
            name="ck_serial_state",
        ),
        schema="inv",
    )
    op.create_index("ix_serial_tenant", "serial", ["tenant_id"], schema="inv")

    op.create_table(
        "lot",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("sku_id", UUID(as_uuid=True), sa.ForeignKey("inv.sku.id"), nullable=False),
        sa.Column("lot_code", sa.String(64), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "sku_id", "lot_code", name="uq_lot_tenant_sku_code"),
        schema="inv",
    )

    op.create_table(
        "balance",
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("sku_id", UUID(as_uuid=True), sa.ForeignKey("inv.sku.id"), nullable=False),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("inv.location.id"), nullable=False),
        sa.Column("on_hand", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("reserved", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column(
            "available",
            sa.Numeric(18, 3),
            sa.Computed("on_hand - reserved", persisted=True),
        ),
        sa.PrimaryKeyConstraint("tenant_id", "sku_id", "location_id", name="pk_balance"),
        schema="inv",
    )

    op.create_table(
        "ledger",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("sku_id", UUID(as_uuid=True), sa.ForeignKey("inv.sku.id"), nullable=False),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("inv.location.id"), nullable=False),
        sa.Column("qty_delta", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("source_doc_id", UUID(as_uuid=True), nullable=False),
        sa.Column("serial_id", UUID(as_uuid=True), sa.ForeignKey("inv.serial.id"), nullable=True),
        sa.Column("lot_id", UUID(as_uuid=True), sa.ForeignKey("inv.lot.id"), nullable=True),
        sa.Column("client_intake_id", UUID(as_uuid=True), nullable=True),
        sa.Column("actor_user_id", UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "source_kind IN ('po_receipt','sale','return','rma_ship','transfer_ship','transfer_receive','count_adjustment','scrap')",
            name="ck_ledger_source_kind",
        ),
        schema="inv",
    )
    op.create_index("ix_ledger_sku_loc_time", "ledger", ["tenant_id", "sku_id", "location_id", "occurred_at"], schema="inv")
    op.create_index(
        "uq_ledger_client_intake",
        "ledger",
        ["tenant_id", "client_intake_id"],
        unique=True,
        schema="inv",
        postgresql_where=sa.text("client_intake_id IS NOT NULL"),
    )

    # Append-only: deny update/delete via trigger
    op.execute(
        """
        CREATE OR REPLACE FUNCTION inv.ledger_deny_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'inv.ledger is append-only (op=%)', TG_OP;
        END
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER ledger_no_update BEFORE UPDATE OR DELETE ON inv.ledger
        FOR EACH ROW EXECUTE FUNCTION inv.ledger_deny_mutation();
        """
    )

    op.create_table(
        "cost_layer",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("sku_id", UUID(as_uuid=True), sa.ForeignKey("inv.sku.id"), nullable=False),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("inv.location.id"), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("qty_remaining", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False),
        schema="inv",
    )
    op.create_index(
        "ix_cost_layer_fifo",
        "cost_layer",
        ["tenant_id", "sku_id", "location_id", "received_at"],
        schema="inv",
    )

    op.create_table(
        "adjustment",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("sku_id", UUID(as_uuid=True), sa.ForeignKey("inv.sku.id"), nullable=False),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("inv.location.id"), nullable=False),
        sa.Column("qty_delta", sa.Numeric(18, 3), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("count_session_id", UUID(as_uuid=True), nullable=True),
        sa.Column("counter_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="inv",
    )

    for s, t in RLS_TABLES:
        _enable_rls(s, t)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS ledger_no_update ON inv.ledger")
    op.execute("DROP FUNCTION IF EXISTS inv.ledger_deny_mutation()")
    for s, t in reversed(RLS_TABLES):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{s}"."{t}"')
    op.drop_table("adjustment", schema="inv")
    op.drop_table("cost_layer", schema="inv")
    op.drop_table("ledger", schema="inv")
    op.drop_table("balance", schema="inv")
    op.drop_table("lot", schema="inv")
    op.drop_table("serial", schema="inv")
