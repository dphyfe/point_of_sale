from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pos_inventory.persistence.base import Base


class TenantConfig(Base):
    __tablename__ = "tenant_config"
    __table_args__ = {"schema": "inv"}

    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    over_receive_tolerance_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    no_receipt_returns_enabled: Mapped[bool] = mapped_column(default=True)
    extras: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
