"""Receipt routes."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from pos_inventory.api.schemas.receipts import Receipt, ReceiptInput, ReceivedLineOut
from pos_inventory.core.auth import Principal, get_principal, requires_role
from pos_inventory.core.tenancy import tenant_session
from pos_inventory.domain.purchase_orders.receiving import (
    ReceiptLineInput as DomainLine,
    post_receipt,
)

router = APIRouter(prefix="/receipts", tags=["receipts"])


@router.post(
    "",
    response_model=Receipt,
    dependencies=[Depends(requires_role("Receiver", "Inventory Clerk"))],
)
def create_receipt(
    body: ReceiptInput,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> Receipt:
    receipt_id, received = post_receipt(
        sess,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        po_id=body.purchase_order_id,
        location_id=body.location_id,
        lines=[
            DomainLine(
                po_line_id=l.po_line_id,
                received_qty=Decimal(l.received_qty),
                serial_values=list(l.serial_values),
                lot_code=l.lot_code,
            )
            for l in body.lines
        ],
    )
    return Receipt(
        id=receipt_id,
        purchase_order_id=body.purchase_order_id,
        location_id=body.location_id,
        lines=[
            ReceivedLineOut(
                receipt_line_id=r.receipt_line_id,
                po_line_id=r.po_line_id,
                received_qty=r.received_qty,
                overage_qty=r.overage_qty,
                backordered_qty=r.backordered_qty,
                unit_cost=r.unit_cost,
            )
            for r in received
        ],
    )
