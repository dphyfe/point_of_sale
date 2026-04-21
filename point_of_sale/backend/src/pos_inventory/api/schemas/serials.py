from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class Serial(BaseModel):
    id: UUID
    sku_id: UUID
    serial_value: str
    state: str
    current_location_id: UUID | None = None
    unit_cost: Decimal
    received_at: datetime


class SerialHistoryEntry(BaseModel):
    occurred_at: datetime
    source_kind: str
    source_doc_id: UUID
    location_id: UUID | None = None
    qty_delta: Decimal
    unit_cost: Decimal


class SerialWithHistory(BaseModel):
    serial: Serial
    history: list[SerialHistoryEntry]
