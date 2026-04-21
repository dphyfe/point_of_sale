from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from pos_inventory.persistence.base import Base


class ConsentState(Base):
    __tablename__ = "state"
    __table_args__ = {"schema": "consent"}

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cust.customer.id"), primary_key=True
    )
    channel: Mapped[str] = mapped_column(String(8), primary_key=True)
    purpose: Mapped[str] = mapped_column(String(16), primary_key=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="unset")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consent.event.id"), nullable=True
    )
