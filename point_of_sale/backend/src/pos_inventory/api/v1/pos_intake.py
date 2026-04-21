"""POS intake: idempotent batch sale endpoint for offline-first POS clients.

The offline path is **non-serialized only** (FR-034 / R3). Any envelope
carrying a serialized SKU line is rejected with 400 so the client knows
not to enqueue serialized sales while offline.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pos_inventory.core.auth import Principal, get_principal, requires_role
from pos_inventory.core.errors import BusinessRuleConflict, IdempotencyConflict, ValidationFailed
from pos_inventory.core.tenancy import tenant_session
from pos_inventory.domain.inventory.ledger import post_movement
from pos_inventory.domain.inventory.sale_guard import assert_can_sell

router = APIRouter(prefix="/pos-intake", tags=["pos-intake"])


class PosSaleLine(BaseModel):
    sku_id: UUID
    qty: Decimal = Field(gt=0)


class PosSaleIntake(BaseModel):
    client_intake_id: UUID
    register_id: UUID
    location_id: UUID
    occurred_at: datetime
    lines: list[PosSaleLine]


class PosIntakeResult(BaseModel):
    client_intake_id: UUID
    status: Literal["accepted", "already_processed"]


class PosIntakeBatch(BaseModel):
    items: list[PosSaleIntake]


def _is_serialized(sess: Session, sku_id: UUID) -> bool:
    row = sess.execute(text("SELECT tracking FROM inv.sku WHERE id = :id"), {"id": str(sku_id)}).one_or_none()
    if row is None:
        raise ValidationFailed(f"unknown sku {sku_id}")
    return row[0] == "serialized"


@router.post(
    "/sales",
    response_model=list[PosIntakeResult],
    dependencies=[Depends(requires_role("Cashier"))],
)
def post_sales(
    body: PosIntakeBatch,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> list[PosIntakeResult]:
    out: list[PosIntakeResult] = []
    for env in body.items:
        # Reject envelopes containing serialized lines (offline path is
        # non-serialized only).
        for ln in env.lines:
            if _is_serialized(sess, ln.sku_id):
                raise BusinessRuleConflict("serialized SKUs cannot be sold via offline pos-intake")

        # Idempotency check using the partial unique index on inv.ledger.
        # Try one ledger insert per line; if the first insert hits the unique
        # constraint, the entire envelope was already processed.
        sale_doc = uuid4()
        ts = env.occurred_at or datetime.now(timezone.utc)
        try:
            with sess.begin_nested():
                for idx, ln in enumerate(env.lines):
                    assert_can_sell(
                        sess,
                        tenant_id=principal.tenant_id,
                        sku_id=ln.sku_id,
                        location_id=env.location_id,
                        qty=ln.qty,
                    )
                    # Only the first line carries the client_intake_id (so the
                    # unique index trips on duplicate envelopes).
                    cli = env.client_intake_id if idx == 0 else None
                    post_movement(
                        sess,
                        tenant_id=principal.tenant_id,
                        sku_id=ln.sku_id,
                        location_id=env.location_id,
                        qty_delta=-ln.qty,
                        source_kind="sale",
                        source_doc_id=sale_doc,
                        client_intake_id=cli,
                        actor_user_id=principal.user_id,
                        occurred_at=ts,
                    )
            out.append(PosIntakeResult(client_intake_id=env.client_intake_id, status="accepted"))
        except IntegrityError:
            sess.rollback()
            out.append(PosIntakeResult(client_intake_id=env.client_intake_id, status="already_processed"))
            # Surface as 409 only if a single envelope was supplied; for a batch
            # the result entry already encodes the per-envelope status.
            if len(body.items) == 1:
                raise IdempotencyConflict("envelope already processed", code="already_processed")
    return out
