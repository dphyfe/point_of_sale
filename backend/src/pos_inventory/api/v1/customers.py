"""Customer-view HTTP routes (FR-001..FR-018).

US1 (search + read profile) is fully wired here. Profile mutation (US3),
addresses, and merge endpoints are provided as placeholders that will be
fleshed out in their respective phases.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from pos_inventory.api.schemas.customers import (
    CustomerRead,
    CustomerSearchResponse,
    CustomerSummary,
)
from pos_inventory.core.auth import Principal, get_principal, requires_role
from pos_inventory.core.tenancy import tenant_session
from pos_inventory.domain.customers import service as customers_service
from pos_inventory.domain.customers.service import SearchInput, display_name
from pos_inventory.persistence.models.customer import Customer

router = APIRouter(prefix="/customers", tags=["customers"])


# Read-side roles per FR-036 (002 extension).
_READ_ROLES = ("Cashier", "Customer Service", "Store Manager", "Marketing")


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
    return CustomerRead.model_validate(customer)
