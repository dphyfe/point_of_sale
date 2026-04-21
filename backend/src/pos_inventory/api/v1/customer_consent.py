"""Customer consent router (T077)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from pos_inventory.core.auth import Principal, get_principal, requires_role
from pos_inventory.core.tenancy import tenant_session
from pos_inventory.domain.consent import service as consent_service

router = APIRouter(prefix="/customers", tags=["customer-consent"])

_READ_ROLES = ("Cashier", "Customer Service", "Store Manager", "Marketing", "Admin")
_WRITE_ROLES = ("Customer Service", "Store Manager", "Admin")


class ConsentMatrixRow(BaseModel):
    channel: str
    purpose: str
    state: str
    updated_at: datetime


class ConsentHistoryRow(BaseModel):
    id: UUID
    channel: str
    purpose: str
    event_kind: str
    source: str
    actor_user_id: UUID | None
    occurred_at: datetime
    note: str | None


class ConsentResponse(BaseModel):
    matrix: list[ConsentMatrixRow]
    history: list[ConsentHistoryRow]


class ConsentEventIn(BaseModel):
    channel: str = Field(..., pattern="^(email|sms)$")
    purpose: str = Field(..., pattern="^(transactional|marketing)$")
    event_kind: str = Field(..., pattern="^(opt_in|opt_out|withdraw|unsubscribe)$")
    source: str = Field("pos", pattern="^(pos|web|provider|admin)$")
    note: str | None = None


@router.get(
    "/{customer_id}/consent",
    response_model=ConsentResponse,
    dependencies=[Depends(requires_role(*_READ_ROLES))],
)
def get_consent(
    customer_id: UUID,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> ConsentResponse:
    matrix = consent_service.get_matrix(sess, tenant_id=principal.tenant_id, customer_id=customer_id)
    history = consent_service.get_history(sess, tenant_id=principal.tenant_id, customer_id=customer_id)
    return ConsentResponse(
        matrix=[ConsentMatrixRow(**m) for m in matrix],
        history=[ConsentHistoryRow(**h) for h in history],
    )


@router.post(
    "/{customer_id}/consent",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(requires_role(*_WRITE_ROLES))],
)
def post_consent_event(
    customer_id: UUID,
    payload: ConsentEventIn,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> None:
    consent_service.record_event(
        sess,
        tenant_id=principal.tenant_id,
        ev=consent_service.ConsentEventInput(
            customer_id=customer_id,
            channel=payload.channel,
            purpose=payload.purpose,
            event_kind=payload.event_kind,
            source=payload.source,
            actor_user_id=principal.user_id,
            note=payload.note,
        ),
    )
    sess.commit()
