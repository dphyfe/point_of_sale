"""Inventory sale guard (non-serialized): per-location stock check (FR-030)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.errors import BusinessRuleConflict


def assert_can_sell(
    sess: Session,
    *,
    tenant_id: UUID,
    sku_id: UUID,
    location_id: UUID,
    qty: Decimal,
) -> None:
    row = sess.execute(
        text(
            """
            SELECT b.available, l.restrict_to_home_location
              FROM inv.balance b
              JOIN inv.location l ON l.id = b.location_id
             WHERE b.tenant_id = :tid AND b.sku_id = :sid AND b.location_id = :lid
            """
        ),
        {"tid": str(tenant_id), "sid": str(sku_id), "lid": str(location_id)},
    ).one_or_none()
    if row is None or Decimal(row[0]) < qty:
        if row and row[1]:
            raise BusinessRuleConflict("SKU not stocked at register's home location")
        raise BusinessRuleConflict("insufficient available stock at location")
