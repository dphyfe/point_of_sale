from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import Computed, ForeignKey, Numeric, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from pos_inventory.persistence.base import Base


class Balance(Base):
    __tablename__ = "balance"
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "sku_id", "location_id", name="pk_balance"),
        {"schema": "inv"},
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sku_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("inv.sku.id"), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("inv.location.id"), nullable=False)
    on_hand: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0"))
    reserved: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0"))
    available: Mapped[Decimal] = mapped_column(Numeric(18, 3), Computed("on_hand - reserved", persisted=True))
