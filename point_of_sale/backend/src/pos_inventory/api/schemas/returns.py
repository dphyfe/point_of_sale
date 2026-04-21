from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class CustomerReturnLineInput(BaseModel):
    sku_id: UUID
    qty: Decimal = Field(gt=0)
    reason_code: str
    disposition: str  # sellable|hold|scrap|vendor_rma
    target_location_id: UUID
    serial_value: str | None = None
    refund_amount: Decimal = Decimal("0")


class CustomerReturnInput(BaseModel):
    cashier_user_id: UUID
    occurred_at: datetime | None = None
    original_sale_id: UUID | None = None
    no_receipt: bool = False
    manager_approval_user_id: UUID | None = None
    refund_method: str = "original"
    lines: list[CustomerReturnLineInput]
