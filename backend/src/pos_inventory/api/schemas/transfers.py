from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class TransferLineInput(BaseModel):
    sku_id: UUID
    qty: Decimal = Field(gt=0)
    serial_ids: list[UUID] | None = None


class TransferInput(BaseModel):
    source_location_id: UUID
    destination_location_id: UUID
    lines: list[TransferLineInput]
