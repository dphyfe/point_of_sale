"""Serial lookup with full lifecycle history (FR-012)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.errors import NotFound


@dataclass(frozen=True)
class SerialRecord:
    id: UUID
    sku_id: UUID
    serial_value: str
    state: str
    current_location_id: UUID | None
    unit_cost: Decimal
    received_at: datetime


@dataclass(frozen=True)
class SerialHistoryEntry:
    occurred_at: datetime
    source_kind: str
    source_doc_id: UUID
    location_id: UUID | None
    qty_delta: Decimal
    unit_cost: Decimal


def get_serial_with_history(sess: Session, *, tenant_id: UUID, serial_value: str) -> tuple[SerialRecord, list[SerialHistoryEntry]]:
    row = sess.execute(
        text(
            """
            SELECT id, sku_id, serial_value, state, current_location_id, unit_cost, received_at
              FROM inv.serial
             WHERE tenant_id = :tid AND serial_value = :sv
            """
        ),
        {"tid": str(tenant_id), "sv": serial_value},
    ).one_or_none()
    if row is None:
        raise NotFound(f"serial {serial_value}")
    serial = SerialRecord(
        id=row[0],
        sku_id=row[1],
        serial_value=row[2],
        state=row[3],
        current_location_id=row[4],
        unit_cost=Decimal(row[5]),
        received_at=row[6],
    )
    hist = sess.execute(
        text(
            """
            SELECT occurred_at, source_kind, source_doc_id, location_id, qty_delta, unit_cost
              FROM inv.ledger
             WHERE tenant_id = :tid AND serial_id = :sid
             ORDER BY occurred_at ASC
            """
        ),
        {"tid": str(tenant_id), "sid": str(serial.id)},
    ).all()
    history = [
        SerialHistoryEntry(
            occurred_at=h[0],
            source_kind=h[1],
            source_doc_id=h[2],
            location_id=h[3],
            qty_delta=Decimal(h[4]),
            unit_cost=Decimal(h[5]),
        )
        for h in hist
    ]
    return serial, history
