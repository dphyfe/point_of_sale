"""Purchase Order routes."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.api.schemas.common import IdResponse
from pos_inventory.api.schemas.purchase_orders import (
    PurchaseOrder,
    PurchaseOrderInput,
    PurchaseOrderLine,
)
from pos_inventory.core.auth import Principal, get_principal, requires_role
from pos_inventory.core.errors import NotFound
from pos_inventory.core.tenancy import tenant_session
from pos_inventory.domain.purchase_orders import service as svc
from pos_inventory.domain.purchase_orders.service import PoLineInput

router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])


@router.post("", response_model=IdResponse, dependencies=[Depends(requires_role("Purchasing"))])
def create_po(
    body: PurchaseOrderInput,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> IdResponse:
    pid = svc.create_po(
        sess,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        vendor_id=body.vendor_id,
        po_number=body.po_number,
        lines=[PoLineInput(sku_id=l.sku_id, ordered_qty=Decimal(l.ordered_qty), unit_cost=Decimal(l.unit_cost)) for l in body.lines],
    )
    return IdResponse(id=pid)


@router.get("", response_model=list[PurchaseOrder])
def list_pos(
    state: str | None = None,
    sess: Session = Depends(tenant_session),
    _: Principal = Depends(get_principal),
) -> list[PurchaseOrder]:
    sql = "SELECT id, vendor_id, po_number, state, expected_total, created_at FROM po.purchase_order"
    params: dict = {}
    if state:
        sql += " WHERE state = :state"
        params["state"] = state
    sql += " ORDER BY created_at DESC LIMIT 200"
    rows = sess.execute(text(sql), params).all()
    return [
        PurchaseOrder(
            id=r[0],
            vendor_id=r[1],
            po_number=r[2],
            state=r[3],
            expected_total=Decimal(r[4]),
            created_at=r[5],
            lines=[],
        )
        for r in rows
    ]


@router.get("/{po_id}", response_model=PurchaseOrder)
def get_po(po_id: UUID, sess: Session = Depends(tenant_session)) -> PurchaseOrder:
    row = sess.execute(
        text("SELECT id, vendor_id, po_number, state, expected_total, created_at FROM po.purchase_order WHERE id = :id"),
        {"id": str(po_id)},
    ).one_or_none()
    if row is None:
        raise NotFound(f"po {po_id}")
    line_rows = sess.execute(
        text("SELECT id, sku_id, ordered_qty, received_qty, backordered_qty, unit_cost FROM po.purchase_order_line WHERE po_id = :id ORDER BY id"),
        {"id": str(po_id)},
    ).all()
    return PurchaseOrder(
        id=row[0],
        vendor_id=row[1],
        po_number=row[2],
        state=row[3],
        expected_total=Decimal(row[4]),
        created_at=row[5],
        lines=[
            PurchaseOrderLine(
                id=lr[0],
                sku_id=lr[1],
                ordered_qty=Decimal(lr[2]),
                received_qty=Decimal(lr[3]),
                backordered_qty=Decimal(lr[4]),
                unit_cost=Decimal(lr[5]),
            )
            for lr in line_rows
        ],
    )


def _transition_endpoint(target: Literal["submit", "approve", "send", "cancel"]):
    fn = getattr(svc, target)

    def endpoint(
        po_id: UUID,
        sess: Session = Depends(tenant_session),
        principal: Principal = Depends(get_principal),
    ) -> dict:
        new_state = fn(
            sess,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            actor_roles=principal.roles,
            po_id=po_id,
        )
        return {"id": str(po_id), "state": new_state}

    return endpoint


router.add_api_route("/{po_id}/submit", _transition_endpoint("submit"), methods=["POST"])
router.add_api_route("/{po_id}/approve", _transition_endpoint("approve"), methods=["POST"])
router.add_api_route("/{po_id}/send", _transition_endpoint("send"), methods=["POST"])
router.add_api_route("/{po_id}/cancel", _transition_endpoint("cancel"), methods=["POST"])
