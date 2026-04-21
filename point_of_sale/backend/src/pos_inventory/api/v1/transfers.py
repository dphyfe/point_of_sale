from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from pos_inventory.api.schemas.common import IdResponse
from pos_inventory.api.schemas.transfers import TransferInput
from pos_inventory.core.auth import Principal, get_principal, requires_role
from pos_inventory.core.tenancy import tenant_session
from pos_inventory.domain.transfers.service import (
    TransferInput as DomainTransferInput,
    TransferLineInput,
    create_transfer,
    receive,
    ship,
)

router = APIRouter(prefix="/transfers", tags=["transfers"])


@router.post(
    "",
    response_model=IdResponse,
    dependencies=[Depends(requires_role("Inventory Clerk", "Store Manager"))],
)
def create(
    body: TransferInput,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> IdResponse:
    tid = create_transfer(
        sess,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        input=DomainTransferInput(
            source_location_id=body.source_location_id,
            destination_location_id=body.destination_location_id,
            lines=[TransferLineInput(sku_id=l.sku_id, qty=Decimal(l.qty), serial_ids=l.serial_ids) for l in body.lines],
        ),
    )
    return IdResponse(id=tid)


@router.post(
    "/{transfer_id}/ship",
    dependencies=[Depends(requires_role("Inventory Clerk", "Store Manager"))],
)
def post_ship(
    transfer_id: UUID,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> dict:
    state = ship(sess, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, transfer_id=transfer_id)
    return {"id": str(transfer_id), "state": state}


@router.post(
    "/{transfer_id}/receive",
    dependencies=[Depends(requires_role("Receiver", "Inventory Clerk", "Store Manager"))],
)
def post_receive(
    transfer_id: UUID,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> dict:
    state = receive(sess, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, transfer_id=transfer_id)
    return {"id": str(transfer_id), "state": state}
