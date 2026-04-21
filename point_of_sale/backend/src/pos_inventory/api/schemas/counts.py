from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class CountSessionInput(BaseModel):
    site_id: UUID
    location_ids: list[UUID] | None = None
    sku_ids: list[UUID] | None = None
    hide_system_qty: bool = True


class CountEntryInput(BaseModel):
    sku_id: UUID
    location_id: UUID
    counted_qty: Decimal = Field(ge=0)
    counter_user_id: UUID
    serial_value: str | None = None


class CountEntriesInput(BaseModel):
    entries: list[CountEntryInput]


class VarianceLine(BaseModel):
    sku_id: UUID
    location_id: UUID
    system_at_open: Decimal
    delta_movements: Decimal
    counted_qty: Decimal
    variance_qty: Decimal
    variance_value: Decimal


class VarianceReport(BaseModel):
    session_id: UUID
    generated_at: datetime
    lines: list[VarianceLine]
