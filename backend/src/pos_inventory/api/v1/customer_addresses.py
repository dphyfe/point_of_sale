"""Customer addresses (US3, FR-009): CRUD with at-most-one-default-per-kind.

Each mutation writes one `audit.audit_entry` row with `target_kind='customer.address'`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.api.schemas.customers import (
    CustomerAddressCreate,
    CustomerAddressRead,
)
from pos_inventory.core.audit import write_audit
from pos_inventory.core.auth import Principal, get_principal, requires_role
from pos_inventory.core.errors import NotFound
from pos_inventory.core.tenancy import tenant_session
from pos_inventory.persistence.models.customer_address import CustomerAddress

router = APIRouter(prefix="/customers", tags=["customer-addresses"])

_ROLES = ("Cashier", "Customer Service", "Store Manager")


class AddressList(BaseModel):
    items: list[CustomerAddressRead]


def _clear_default(sess: Session, *, tenant_id: UUID, customer_id: UUID, kind: str) -> None:
    sess.execute(
        text(
            """
            UPDATE cust.customer_address
               SET is_default_for_kind = FALSE
             WHERE tenant_id=:tid AND customer_id=:cid AND kind=:kind
                   AND is_default_for_kind = TRUE
            """
        ),
        {"tid": str(tenant_id), "cid": str(customer_id), "kind": kind},
    )


@router.get(
    "/{customer_id}/addresses",
    response_model=AddressList,
    dependencies=[Depends(requires_role(*_ROLES, "Marketing"))],
)
def list_addresses_endpoint(
    customer_id: UUID,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> AddressList:
    rows = sess.execute(
        text("SELECT * FROM cust.customer_address WHERE tenant_id=:tid AND customer_id=:cid ORDER BY kind, created_at"),
        {"tid": str(principal.tenant_id), "cid": str(customer_id)},
    ).mappings().all()
    return AddressList(items=[CustomerAddressRead.model_validate(dict(r)) for r in rows])


@router.post(
    "/{customer_id}/addresses",
    response_model=CustomerAddressRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requires_role(*_ROLES))],
)
def create_address_endpoint(
    customer_id: UUID,
    payload: CustomerAddressCreate,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> CustomerAddressRead:
    new_id = uuid4()
    now = datetime.now(timezone.utc)
    if payload.is_default_for_kind:
        _clear_default(sess, tenant_id=principal.tenant_id, customer_id=customer_id, kind=payload.kind)
    sess.execute(
        text(
            """
            INSERT INTO cust.customer_address
                (id, tenant_id, customer_id, kind, is_default_for_kind, line1, line2,
                 city, region, postal_code, country, created_at, updated_at)
            VALUES (:id, :tid, :cid, :kind, :def, :l1, :l2, :city, :region, :pc, :country, :ts, :ts)
            """
        ),
        {
            "id": str(new_id),
            "tid": str(principal.tenant_id),
            "cid": str(customer_id),
            "kind": payload.kind,
            "def": payload.is_default_for_kind,
            "l1": payload.line1,
            "l2": payload.line2,
            "city": payload.city,
            "region": payload.region,
            "pc": payload.postal_code,
            "country": payload.country,
            "ts": now,
        },
    )
    write_audit(
        sess,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        target_kind="customer.address",
        target_id=new_id,
        action="created",
        before=None,
        after=payload.model_dump(),
    )
    sess.commit()
    row = sess.get(CustomerAddress, new_id)
    assert row is not None
    return CustomerAddressRead.model_validate(row, from_attributes=True)


@router.put(
    "/{customer_id}/addresses/{address_id}",
    response_model=CustomerAddressRead,
    dependencies=[Depends(requires_role(*_ROLES))],
)
def update_address_endpoint(
    customer_id: UUID,
    address_id: UUID,
    payload: CustomerAddressCreate,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> CustomerAddressRead:
    row = sess.get(CustomerAddress, address_id)
    if row is None or row.customer_id != customer_id or row.tenant_id != principal.tenant_id:
        raise NotFound("address")
    before = {
        "kind": row.kind,
        "is_default_for_kind": row.is_default_for_kind,
        "line1": row.line1,
        "line2": row.line2,
        "city": row.city,
        "region": row.region,
        "postal_code": row.postal_code,
        "country": row.country,
    }
    if payload.is_default_for_kind:
        _clear_default(sess, tenant_id=principal.tenant_id, customer_id=customer_id, kind=payload.kind)
    sess.execute(
        text(
            """
            UPDATE cust.customer_address SET
                kind=:kind, is_default_for_kind=:def, line1=:l1, line2=:l2,
                city=:city, region=:region, postal_code=:pc, country=:country,
                updated_at=:ts
             WHERE id=:id AND tenant_id=:tid
            """
        ),
        {
            "kind": payload.kind,
            "def": payload.is_default_for_kind,
            "l1": payload.line1,
            "l2": payload.line2,
            "city": payload.city,
            "region": payload.region,
            "pc": payload.postal_code,
            "country": payload.country,
            "ts": datetime.now(timezone.utc),
            "id": str(address_id),
            "tid": str(principal.tenant_id),
        },
    )
    write_audit(
        sess,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        target_kind="customer.address",
        target_id=address_id,
        action="updated",
        before=before,
        after=payload.model_dump(),
    )
    sess.commit()
    sess.refresh(row)
    return CustomerAddressRead.model_validate(row, from_attributes=True)


@router.delete(
    "/{customer_id}/addresses/{address_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(requires_role(*_ROLES))],
)
def delete_address_endpoint(
    customer_id: UUID,
    address_id: UUID,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> None:
    row = sess.get(CustomerAddress, address_id)
    if row is None or row.customer_id != customer_id or row.tenant_id != principal.tenant_id:
        raise NotFound("address")
    before = {
        "kind": row.kind,
        "line1": row.line1,
    }
    sess.execute(
        text("DELETE FROM cust.customer_address WHERE id=:id AND tenant_id=:tid"),
        {"id": str(address_id), "tid": str(principal.tenant_id)},
    )
    write_audit(
        sess,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        target_kind="customer.address",
        target_id=address_id,
        action="deleted",
        before=before,
        after=None,
    )
    sess.commit()
