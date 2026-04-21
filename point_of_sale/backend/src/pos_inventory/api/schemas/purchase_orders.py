from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class PurchaseOrderLineInput(BaseModel):
    sku_id: UUID
    ordered_qty: Decimal = Field(gt=0)
    unit_cost: Decimal = Field(ge=0)


class PurchaseOrderInput(BaseModel):
    vendor_id: UUID
    po_number: str
    lines: list[PurchaseOrderLineInput]


class PurchaseOrderLine(BaseModel):
    id: UUID
    sku_id: UUID
    ordered_qty: Decimal
    received_qty: Decimal
    backordered_qty: Decimal
    unit_cost: Decimal


class PurchaseOrder(BaseModel):
    id: UUID
    vendor_id: UUID
    po_number: str
    state: str
    expected_total: Decimal
    created_at: datetime
    lines: list[PurchaseOrderLine] = []
