from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pos_inventory.persistence.base import Base


class CountSessionSnapshot(Base):
    __tablename__ = "count_session_snapshot"
    __table_args__ = {"schema": "cnt"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    session_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("cnt.count_session.id"), nullable=False)
    sku_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("inv.sku.id"), nullable=False)
    location_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("inv.location.id"), nullable=False)
    on_hand_at_open: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
