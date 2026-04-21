from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pos_inventory.persistence.base import Base


class CountAssignment(Base):
    __tablename__ = "count_assignment"
    __table_args__ = {"schema": "cnt"}

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    session_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("cnt.count_session.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    location_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("inv.location.id"), nullable=False)
