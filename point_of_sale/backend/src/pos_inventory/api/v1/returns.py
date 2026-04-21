from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from pos_inventory.api.schemas.common import IdResponse
from pos_inventory.api.schemas.returns import CustomerReturnInput
from pos_inventory.core.auth import Principal, get_principal, requires_role
from pos_inventory.core.errors import RoleForbidden
from pos_inventory.core.tenancy import tenant_session
from pos_inventory.domain.returns.service import (
    ReturnInput,
    ReturnLineInput,
    post_return,
)

router = APIRouter(prefix="/returns", tags=["returns"])


@router.post(
    "",
    response_model=IdResponse,
    dependencies=[Depends(requires_role("Cashier", "Store Manager"))],
)
def create_return(
    body: CustomerReturnInput,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> IdResponse:
    if body.no_receipt and not (principal.has_any({"Store Manager"}) or "Admin" in principal.roles):
        raise RoleForbidden("no-receipt returns require Store Manager")

    rid = post_return(
        sess,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        input=ReturnInput(
            cashier_user_id=body.cashier_user_id,
            occurred_at=body.occurred_at,
            original_sale_id=body.original_sale_id,
            no_receipt=body.no_receipt,
            manager_approval_user_id=body.manager_approval_user_id,
            refund_method=body.refund_method,
            lines=[
                ReturnLineInput(
                    sku_id=l.sku_id,
                    qty=Decimal(l.qty),
                    reason_code=l.reason_code,
                    disposition=l.disposition,
                    target_location_id=l.target_location_id,
                    serial_value=l.serial_value,
                    refund_amount=Decimal(l.refund_amount),
                )
                for l in body.lines
            ],
        ),
    )
    return IdResponse(id=rid)
