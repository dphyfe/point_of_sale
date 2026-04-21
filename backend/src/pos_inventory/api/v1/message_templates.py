"""Message templates router (T074)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from pos_inventory.core.auth import Principal, get_principal, requires_role
from pos_inventory.core.tenancy import tenant_session
from pos_inventory.domain.messaging import template_service as ts

router = APIRouter(prefix="/message-templates", tags=["message-templates"])

_ADMIN = ("Marketing", "Admin")


class TemplateIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    channel: str = Field(..., pattern="^(email|sms)$")
    purpose: str = Field(..., pattern="^(transactional|marketing)$")
    subject_template: str | None = None
    body_template: str = Field(..., min_length=1)
    enabled: bool = True


class TemplateOut(BaseModel):
    id: UUID
    code: str
    name: str
    channel: str
    purpose: str
    subject_template: str | None
    body_template: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class TemplateListOut(BaseModel):
    items: list[TemplateOut]


@router.get(
    "",
    response_model=TemplateListOut,
    dependencies=[Depends(requires_role("Cashier", "Customer Service", "Store Manager", "Marketing", "Admin"))],
)
def list_templates(
    channel: str | None = Query(None, pattern="^(email|sms)$"),
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> TemplateListOut:
    items = ts.list_templates(sess, tenant_id=principal.tenant_id, channel=channel)
    return TemplateListOut(items=[TemplateOut(**i) for i in items])


@router.post(
    "",
    response_model=TemplateOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requires_role(*_ADMIN))],
)
def create_template(
    payload: TemplateIn,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> TemplateOut:
    new_id = ts.create_template(sess, tenant_id=principal.tenant_id, data=ts.TemplateData(**payload.model_dump()))
    sess.commit()
    items = ts.list_templates(sess, tenant_id=principal.tenant_id)
    item = next(i for i in items if i["id"] == new_id)
    return TemplateOut(**item)


@router.put(
    "/{template_id}",
    response_model=TemplateOut,
    dependencies=[Depends(requires_role(*_ADMIN))],
)
def update_template(
    template_id: UUID,
    payload: TemplateIn,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> TemplateOut:
    ts.update_template(
        sess, tenant_id=principal.tenant_id, template_id=template_id,
        data=ts.TemplateData(**payload.model_dump()),
    )
    sess.commit()
    items = ts.list_templates(sess, tenant_id=principal.tenant_id)
    item = next(i for i in items if i["id"] == template_id)
    return TemplateOut(**item)


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(requires_role(*_ADMIN))],
)
def disable_template(
    template_id: UUID,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> None:
    """Soft-disable: sets ``enabled=false`` (never hard-deletes)."""
    items = ts.list_templates(sess, tenant_id=principal.tenant_id)
    current = next((i for i in items if i["id"] == template_id), None)
    if current is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="template not found")
    ts.update_template(
        sess,
        tenant_id=principal.tenant_id,
        template_id=template_id,
        data=ts.TemplateData(
            code=current["code"],
            name=current["name"],
            channel=current["channel"],
            purpose=current["purpose"],
            subject_template=current["subject_template"],
            body_template=current["body_template"],
            enabled=False,
        ),
    )
    sess.commit()
