from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from pos_inventory.persistence.base import Base


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_line"
    __table_args__ = {"schema": "po"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    po_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("po.purchase_order.id"), nullable=False)
    sku_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("inv.sku.id"), nullable=False)
    ordered_qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    received_qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0"))
    backordered_qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0"))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
