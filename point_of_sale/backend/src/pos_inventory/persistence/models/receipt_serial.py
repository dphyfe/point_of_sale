from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from pos_inventory.persistence.base import Base


class ReceiptSerial(Base):
    __tablename__ = "receipt_serial"
    __table_args__ = {"schema": "po"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    receipt_line_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("po.receipt_line.id"), nullable=False)
    serial_value: Mapped[str] = mapped_column(String(255), nullable=False)
