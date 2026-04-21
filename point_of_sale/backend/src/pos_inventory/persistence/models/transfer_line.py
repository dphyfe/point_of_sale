from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pos_inventory.persistence.base import Base


class TransferLine(Base):
    __tablename__ = "transfer_line"
    __table_args__ = {"schema": "xfr"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    transfer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("xfr.transfer.id"), nullable=False)
    sku_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("inv.sku.id"), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
