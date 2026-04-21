"""Customer-view HTTP routes (FR-001..FR-018, US3 mutations)."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pos_inventory.api.schemas.customers import (
    CustomerCreate,
    CustomerRead,
    CustomerSearchResponse,
    CustomerSummary,
    CustomerUpdate,
    DeactivateRequest,
    MergeRequest,
)
from pos_inventory.core.auth import Principal, get_principal, requires_role
from pos_inventory.core.tenancy import tenant_session
from pos_inventory.domain.customer_history import service as history_service
from pos_inventory.domain.customers import service as customers_service
from pos_inventory.domain.customers import write_service
from pos_inventory.domain.customers.service import SearchInput, display_name
from pos_inventory.domain.customers.write_service import CustomerData
from pos_inventory.persistence.models.customer import Customer

router = APIRouter(prefix="/customers", tags=["customers"])


# Read-side roles per FR-036 (002 extension).
_READ_ROLES = ("Cashier", "Customer Service", "Store Manager", "Marketing")
_WRITE_ROLES = ("Cashier", "Customer Service", "Store Manager")
_LIFECYCLE_ROLES = ("Store Manager",)
_MERGE_ROLES = ("Store Manager",)


def _to_summary(c: Customer) -> CustomerSummary:
    return CustomerSummary(
        id=c.id,
        contact_type=c.contact_type,  # type: ignore[arg-type]
        display_name=display_name(c),
        email=c.email,
        primary_phone=c.primary_phone,
        state=c.state,  # type: ignore[arg-type]
        tags=list(c.tags or []),
    )


def _to_data(payload: CustomerCreate | CustomerUpdate) -> CustomerData:
    return CustomerData(
        contact_type=payload.contact_type,
        first_name=payload.first_name,
        last_name=payload.last_name,
        company_name=payload.company_name,
        primary_phone=payload.primary_phone,
        secondary_phone=payload.secondary_phone,
        email=payload.email,
        preferred_channel=payload.preferred_channel,
        language=payload.language,
        tags=tuple(payload.tags or ()),
        external_loyalty_id=payload.external_loyalty_id,
        external_crm_id=payload.external_crm_id,
        tax_id=getattr(payload, "tax_id", None),
        date_of_birth=getattr(payload, "date_of_birth", None),
        client_request_id=getattr(payload, "client_request_id", None),
    )


def _read_payload(c: Customer, principal: Principal, sess: Session) -> CustomerRead:
    metrics = history_service.get_summary_metrics(
        sess, tenant_id=principal.tenant_id, customer_id=c.id
    )
    privileged = bool(principal.roles & {"Store Manager", "Admin"})
    return CustomerRead.model_validate(c).model_copy(
        update={
            "display_name": display_name(c),
            "tax_id_masked": (
                f"****{c.tax_id[-4:]}"
                if c.tax_id and not privileged
                else c.tax_id
            ),
            "lifetime_spend": metrics["lifetime_spend"],
            "visit_count": metrics["visit_count"],
            "average_order_value": metrics["average_order_value"],
            "last_purchase_at": metrics["last_purchase_at"],
            "last_store_visited": metrics["last_store_visited"],
        }
    )


@router.get(
    "",
    response_model=CustomerSearchResponse,
    dependencies=[Depends(requires_role(*_READ_ROLES))],
)
def search_customers_endpoint(
    q: str = Query(..., min_length=1, max_length=200),
    include_inactive: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> CustomerSearchResponse:
    result = customers_service.search(
        sess,
        tenant_id=principal.tenant_id,
        input=SearchInput(query=q, include_inactive=include_inactive, limit=limit, offset=offset),
    )
    return CustomerSearchResponse(
        items=[_to_summary(c) for c in result.items],
        total=result.total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{customer_id}",
    response_model=CustomerRead,
    dependencies=[Depends(requires_role(*_READ_ROLES))],
)
def get_customer_endpoint(
    customer_id: UUID,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> CustomerRead:
    customer = customers_service.read_profile(
        sess, tenant_id=principal.tenant_id, customer_id=customer_id
    )
    return _read_payload(customer, principal, sess)


@router.post(
    "",
    response_model=CustomerRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requires_role(*_WRITE_ROLES))],
)
def create_customer_endpoint(
    payload: CustomerCreate,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> CustomerRead:
    cust = write_service.create_customer(
        sess,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        actor_roles=principal.roles,
        data=_to_data(payload),
    )
    sess.commit()
    sess.refresh(cust)
    return _read_payload(cust, principal, sess)


@router.put(
    "/{customer_id}",
    response_model=CustomerRead,
    dependencies=[Depends(requires_role(*_WRITE_ROLES))],
)
def update_customer_endpoint(
    customer_id: UUID,
    payload: CustomerUpdate,
    if_match: str = Header(..., alias="If-Match"),
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> CustomerRead:
    try:
        expected_version = int(if_match.strip().strip('"'))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid If-Match") from exc
    cust = write_service.update_customer(
        sess,
        tenant_id=principal.tenant_id,
        customer_id=customer_id,
        actor_user_id=principal.user_id,
        actor_roles=principal.roles,
        expected_version=expected_version,
        data=_to_data(payload),
    )
    sess.commit()
    sess.refresh(cust)
    return _read_payload(cust, principal, sess)


@router.post(
    "/{customer_id}/deactivate",
    response_model=CustomerRead,
    dependencies=[Depends(requires_role(*_LIFECYCLE_ROLES))],
)
def deactivate_endpoint(
    customer_id: UUID,
    payload: DeactivateRequest | None = None,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> CustomerRead:
    cust = write_service.deactivate_customer(
        sess,
        tenant_id=principal.tenant_id,
        customer_id=customer_id,
        actor_user_id=principal.user_id,
        reason=(payload.reason if payload else None),
    )
    sess.commit()
    return _read_payload(cust, principal, sess)


@router.post(
    "/{customer_id}/reactivate",
    response_model=CustomerRead,
    dependencies=[Depends(requires_role(*_LIFECYCLE_ROLES))],
)
def reactivate_endpoint(
    customer_id: UUID,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> CustomerRead:
    cust = write_service.reactivate_customer(
        sess,
        tenant_id=principal.tenant_id,
        customer_id=customer_id,
        actor_user_id=principal.user_id,
    )
    sess.commit()
    return _read_payload(cust, principal, sess)


@router.post(
    "/{customer_id}/anonymize",
    response_model=CustomerRead,
    dependencies=[Depends(requires_role(*_LIFECYCLE_ROLES))],
)
def anonymize_endpoint(
    customer_id: UUID,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> CustomerRead:
    cust = write_service.anonymize_customer(
        sess,
        tenant_id=principal.tenant_id,
        customer_id=customer_id,
        actor_user_id=principal.user_id,
    )
    sess.commit()
    return _read_payload(cust, principal, sess)


class MergeResponse(BaseModel):
    survivor_id: UUID
    merged_away_id: UUID


@router.post(
    "/{customer_id}/merge",
    response_model=MergeResponse,
    dependencies=[Depends(requires_role(*_MERGE_ROLES))],
)
def merge_endpoint(
    customer_id: UUID,
    payload: MergeRequest,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> MergeResponse:
    # path id is the survivor; body declares the merged-away id.
    if payload.survivor_id != customer_id:
        raise HTTPException(status_code=400, detail="survivor_id must match path id")
    write_service.merge_customers(
        sess,
        tenant_id=principal.tenant_id,
        survivor_id=customer_id,
        merged_away_id=payload.merged_away_id,
        actor_user_id=principal.user_id,
        summary=payload.summary,
    )
    sess.commit()
    return MergeResponse(survivor_id=customer_id, merged_away_id=payload.merged_away_id)


class AuditEntry(BaseModel):
    id: str
    occurred_at: str
    actor_user_id: UUID | None = None
    field: str
    old_value: str | None = None
    new_value: str | None = None
    change_kind: str


class AuditResponse(BaseModel):
    items: list[AuditEntry]


@router.get(
    "/{customer_id}/audit",
    response_model=AuditResponse,
    dependencies=[Depends(requires_role(*_READ_ROLES))],
)
def list_audit_endpoint(
    customer_id: UUID,
    limit: int = Query(200, ge=1, le=500),
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> AuditResponse:
    rows = write_service.list_audit(
        sess, tenant_id=principal.tenant_id, customer_id=customer_id, limit=limit
    )
    return AuditResponse(
        items=[
            AuditEntry(
                id=r["id"],
                occurred_at=r["occurred_at"].isoformat() if r["occurred_at"] else "",
                actor_user_id=r["actor_user_id"],
                field=r["field"],
                old_value=r["old_value"],
                new_value=r["new_value"],
                change_kind=r["change_kind"],
            )
            for r in rows
        ]
    )
