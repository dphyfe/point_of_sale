"""Customer transaction-history schemas (FR-019..FR-023)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

TxnKind = Literal["sale", "return", "exchange", "service_order"]


class CustomerHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: TxnKind
    occurred_at: datetime
    store_name: str | None = None
    register_name: str | None = None
    cashier_user_id: UUID | None = None
    total: Decimal | None = None
    refund_total: Decimal | None = None
    summary: str | None = None


class CustomerHistoryResponse(BaseModel):
    items: list[CustomerHistoryItem]
    next_cursor: str | None = None
