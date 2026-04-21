"""sku merchandising fields: upc, department, brand, price

Revision ID: 0010_sku_merchandising_fields
Revises: 0009_config
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_sku_merchandising_fields"
down_revision: str | None = "0009_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sku", sa.Column("upc", sa.String(32), nullable=True), schema="inv")
    op.add_column("sku", sa.Column("department", sa.String(64), nullable=True), schema="inv")
    op.add_column("sku", sa.Column("brand", sa.String(128), nullable=True), schema="inv")
    op.add_column("sku", sa.Column("price", sa.Numeric(12, 2), nullable=True), schema="inv")
    # Partial unique index: enforce UPC uniqueness per tenant when present,
    # but allow many rows with NULL upc.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_sku_tenant_upc
            ON inv.sku (tenant_id, upc)
            WHERE upc IS NOT NULL
        """
    )
    op.create_index("ix_sku_tenant_department", "sku", ["tenant_id", "department"], schema="inv")
    op.create_index("ix_sku_tenant_brand", "sku", ["tenant_id", "brand"], schema="inv")


def downgrade() -> None:
    op.drop_index("ix_sku_tenant_brand", table_name="sku", schema="inv")
    op.drop_index("ix_sku_tenant_department", table_name="sku", schema="inv")
    op.execute("DROP INDEX IF EXISTS inv.uq_sku_tenant_upc")
    op.drop_column("sku", "price", schema="inv")
    op.drop_column("sku", "brand", schema="inv")
    op.drop_column("sku", "department", schema="inv")
    op.drop_column("sku", "upc", schema="inv")
