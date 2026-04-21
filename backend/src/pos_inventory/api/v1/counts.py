from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from pos_inventory.api.schemas.common import IdResponse
from pos_inventory.api.schemas.counts import (
    CountEntriesInput,
    CountSessionInput,
    VarianceLine,
    VarianceReport,
)
from pos_inventory.core.auth import Principal, get_principal, requires_role
from pos_inventory.core.tenancy import tenant_session
from pos_inventory.domain.counts.approve import approve_session
from pos_inventory.domain.counts.service import (
    CountScope,
    EntryInput,
    create_session,
    submit_entries,
)
from pos_inventory.domain.counts.variance import compute_variance

router = APIRouter(prefix="/count-sessions", tags=["counts"])


@router.post(
    "",
    response_model=IdResponse,
    dependencies=[Depends(requires_role("Inventory Clerk", "Store Manager"))],
)
def create(
    body: CountSessionInput,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> IdResponse:
    sid = create_session(
        sess,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        scope=CountScope(
            site_id=body.site_id,
            location_ids=body.location_ids,
            sku_ids=body.sku_ids,
        ),
        hide_system_qty=body.hide_system_qty,
    )
    return IdResponse(id=sid)


@router.post(
    "/{session_id}/entries",
    dependencies=[Depends(requires_role("Inventory Clerk", "Store Manager", "Cashier"))],
)
def add_entries(
    session_id: UUID,
    body: CountEntriesInput,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> dict:
    n = submit_entries(
        sess,
        tenant_id=principal.tenant_id,
        session_id=session_id,
        entries=[
            EntryInput(
                sku_id=e.sku_id,
                location_id=e.location_id,
                counted_qty=Decimal(e.counted_qty),
                counter_user_id=e.counter_user_id,
                serial_value=e.serial_value,
            )
            for e in body.entries
        ],
    )
    return {"session_id": str(session_id), "submitted": n}


@router.get("/{session_id}/variance", response_model=VarianceReport)
def variance(
    session_id: UUID,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> VarianceReport:
    rows = compute_variance(sess, tenant_id=principal.tenant_id, session_id=session_id)
    return VarianceReport(
        session_id=session_id,
        generated_at=datetime.now(timezone.utc),
        lines=[VarianceLine(**r.__dict__) for r in rows],
    )


@router.post(
    "/{session_id}/approve",
    dependencies=[Depends(requires_role("Store Manager"))],
)
def approve(
    session_id: UUID,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> dict:
    n = approve_session(
        sess,
        tenant_id=principal.tenant_id,
        session_id=session_id,
        actor_user_id=principal.user_id,
    )
    return {"session_id": str(session_id), "adjustments": n, "state": "approved"}
