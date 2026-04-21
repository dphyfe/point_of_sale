from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pos_inventory.persistence.base import Base


class CountSession(Base):
    __tablename__ = "count_session"
    __table_args__ = {"schema": "cnt"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    site_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("inv.site.id"), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hide_system_qty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    scope_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="full")  # full|partial
    created_by: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
