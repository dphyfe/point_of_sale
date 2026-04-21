from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pos_inventory.persistence.base import Base


class CountEntry(Base):
    __tablename__ = "count_entry"
    __table_args__ = {"schema": "cnt"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    session_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("cnt.count_session.id"), nullable=False)
    sku_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("inv.sku.id"), nullable=False)
    location_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("inv.location.id"), nullable=False)
    counted_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    counter_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    serial_value: Mapped[str | None] = mapped_column(String(64))
    counted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
