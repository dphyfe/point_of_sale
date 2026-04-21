from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from pos_inventory.persistence.base import Base


class Ledger(Base):
    """Append-only inventory movement ledger.

    Updates and deletes are denied at the database level via trigger
    (see migration 0003).
    """

    __tablename__ = "ledger"
    __table_args__ = (
        Index("ix_ledger_sku_loc_time", "tenant_id", "sku_id", "location_id", "occurred_at"),
        Index(
            "uq_ledger_client_intake",
            "tenant_id",
            "client_intake_id",
            unique=True,
            postgresql_where="client_intake_id IS NOT NULL",
        ),
        {"schema": "inv"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sku_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("inv.sku.id"), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("inv.location.id"), nullable=False)
    qty_delta: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # po_receipt | sale | return | rma_ship | transfer_ship | transfer_receive | count_adjustment | scrap
    source_doc_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    serial_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("inv.serial.id"), nullable=True)
    lot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("inv.lot.id"), nullable=True)
    client_intake_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
