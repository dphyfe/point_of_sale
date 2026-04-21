from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from pos_inventory.persistence.base import Base


class VendorRmaLine(Base):
    __tablename__ = "vendor_rma_line"
    __table_args__ = {"schema": "rma"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    rma_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rma.vendor_rma.id"), nullable=False)
    sku_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("inv.sku.id"), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    serial_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
