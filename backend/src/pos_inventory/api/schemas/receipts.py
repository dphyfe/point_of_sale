from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class ReceiptLineInput(BaseModel):
    po_line_id: UUID
    received_qty: Decimal = Field(gt=0)
    serial_values: list[str] = []
    lot_code: str | None = None


class ReceiptInput(BaseModel):
    purchase_order_id: UUID
    location_id: UUID
    lines: list[ReceiptLineInput]


class ReceivedLineOut(BaseModel):
    receipt_line_id: UUID
    po_line_id: UUID
    received_qty: Decimal
    overage_qty: Decimal
    backordered_qty: Decimal
    unit_cost: Decimal


class Receipt(BaseModel):
    id: UUID
    purchase_order_id: UUID
    location_id: UUID
    lines: list[ReceivedLineOut]
