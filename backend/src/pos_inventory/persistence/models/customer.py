from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from pos_inventory.persistence.base import Base


class Customer(Base):
    __tablename__ = "customer"
    __table_args__ = {"schema": "cust"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    client_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    external_loyalty_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_crm_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_type: Mapped[str] = mapped_column(String(16), nullable=False, default="individual")
    first_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    secondary_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_channel: Mapped[str] = mapped_column(String(16), nullable=False, default="email")
    language: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    tax_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    merged_into: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cust.customer.id"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Trigger-maintained derived columns
    phone_normalized: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_normalized: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_name_lower: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
