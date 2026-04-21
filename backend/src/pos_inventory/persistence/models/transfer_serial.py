from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pos_inventory.persistence.base import Base


class TransferSerial(Base):
    __tablename__ = "transfer_serial"
    __table_args__ = (
        UniqueConstraint("transfer_line_id", "serial_id", name="uq_transfer_serial"),
        {"schema": "xfr"},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    transfer_line_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("xfr.transfer_line.id"), nullable=False)
    serial_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("inv.serial.id"), nullable=False)
