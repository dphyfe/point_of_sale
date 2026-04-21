"""Customer transaction history endpoints (US2: FR-016..FR-023, R1)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pos_inventory.api.schemas.customer_history import (
    CustomerHistoryItem,
    CustomerHistoryResponse,
)
from pos_inventory.core.auth import Principal, get_principal, requires_role
from pos_inventory.core.tenancy import tenant_session
from pos_inventory.core.visibility import VisibilityScope, visibility_scope
from pos_inventory.domain.customer_history import service as history_service
from pos_inventory.domain.customer_history.service import HistoryFilters

router = APIRouter(prefix="/customers", tags=["customer-history"])

_READ_ROLES = ("Cashier", "Customer Service", "Store Manager", "Marketing")


class HistoryLineOut(BaseModel):
    sku_id: UUID
    sku_code: str | None
    description: str | None
    qty: str
    unit_price: str | None
    line_total: str | None
    serial_numbers: list[str]


class HistoryDetailOut(CustomerHistoryItem):
    lines: list[HistoryLineOut]


@router.get(
    "/{customer_id}/history",
    response_model=CustomerHistoryResponse,
    dependencies=[Depends(requires_role(*_READ_ROLES))],
)
def list_history_endpoint(
    customer_id: UUID,
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    kinds: list[Literal["sale", "return", "exchange", "service_order"]] | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
    scope: VisibilityScope = Depends(visibility_scope),
) -> CustomerHistoryResponse:
    items, _total = history_service.list_history(
        sess,
        tenant_id=principal.tenant_id,
        customer_id=customer_id,
        filters=HistoryFilters(start=start, end=end, kinds=tuple(kinds or ())),
        scope=scope,
        limit=limit,
        offset=offset,
    )
    return CustomerHistoryResponse(
        items=[CustomerHistoryItem.model_validate(i, from_attributes=True) for i in items]
    )


@router.get(
    "/{customer_id}/history/{transaction_kind}/{transaction_id}",
    response_model=HistoryDetailOut,
    dependencies=[Depends(requires_role(*_READ_ROLES))],
)
def get_history_detail_endpoint(
    customer_id: UUID,
    transaction_kind: Literal["sale", "return", "exchange", "service_order"],
    transaction_id: UUID,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
    scope: VisibilityScope = Depends(visibility_scope),
) -> HistoryDetailOut:
    row, lines = history_service.get_transaction_detail(
        sess,
        tenant_id=principal.tenant_id,
        customer_id=customer_id,
        kind=transaction_kind,
        transaction_id=transaction_id,
        scope=scope,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    head = CustomerHistoryItem.model_validate(row, from_attributes=True)
    return HistoryDetailOut(
        **head.model_dump(),
        lines=[
            HistoryLineOut(
                sku_id=line.sku_id,
                sku_code=line.sku_code,
                description=line.description,
                qty=str(line.qty),
                unit_price=(str(line.unit_price) if line.unit_price is not None else None),
                line_total=(str(line.line_total) if line.line_total is not None else None),
                serial_numbers=list(line.serial_numbers),
            )
            for line in lines
        ],
    )
