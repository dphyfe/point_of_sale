from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class VendorRmaLineInput(BaseModel):
    sku_id: UUID
    qty: Decimal = Field(gt=0)
    serial_id: UUID | None = None
    unit_cost: Decimal = Decimal("0")


class VendorRmaInput(BaseModel):
    vendor_id: UUID
    holding_location_id: UUID
    originating_po_id: UUID | None = None
    lines: list[VendorRmaLineInput]
