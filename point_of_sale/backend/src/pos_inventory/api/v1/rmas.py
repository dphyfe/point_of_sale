from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from pos_inventory.api.schemas.common import IdResponse
from pos_inventory.api.schemas.rmas import VendorRmaInput
from pos_inventory.core.auth import Principal, get_principal, requires_role
from pos_inventory.core.tenancy import tenant_session
from pos_inventory.domain.rmas.service import RmaInput, RmaLineInput, close_rma, create_rma, ship_rma

router = APIRouter(prefix="/vendor-rmas", tags=["vendor-rmas"])


@router.post(
    "",
    response_model=IdResponse,
    dependencies=[Depends(requires_role("Inventory Clerk", "Store Manager", "Purchasing"))],
)
def create(
    body: VendorRmaInput,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> IdResponse:
    rid = create_rma(
        sess,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        input=RmaInput(
            vendor_id=body.vendor_id,
            holding_location_id=body.holding_location_id,
            originating_po_id=body.originating_po_id,
            lines=[
                RmaLineInput(
                    sku_id=l.sku_id,
                    qty=Decimal(l.qty),
                    serial_id=l.serial_id,
                    unit_cost=Decimal(l.unit_cost),
                )
                for l in body.lines
            ],
        ),
    )
    return IdResponse(id=rid)


@router.post(
    "/{rma_id}/ship",
    dependencies=[Depends(requires_role("Inventory Clerk", "Store Manager"))],
)
def ship(
    rma_id: UUID,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> dict:
    state = ship_rma(sess, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, rma_id=rma_id)
    return {"id": str(rma_id), "state": state}


@router.post(
    "/{rma_id}/close",
    dependencies=[Depends(requires_role("Store Manager", "Purchasing"))],
)
def close(
    rma_id: UUID,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> dict:
    credit = close_rma(sess, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, rma_id=rma_id)
    return {"id": str(rma_id), "state": "closed", "credit_total": str(credit)}
