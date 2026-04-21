"""Customer returns service.

Implements FR-013/14/15/16/18 with the Q4 default no-receipt policy:
- no-receipt requires manager_approval_user_id
- no-receipt forces refund_method='store_credit'
- serialized no-receipt requires the serial to have a prior sale by this tenant

Each line posts an inventory movement of `source_kind='return'` to a
`target_location_id` derived from the disposition. Serialized lines also
update the serial via `serials.return_`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.audit import write_audit
from pos_inventory.core.errors import BusinessRuleConflict, NotFound, ValidationFailed
from pos_inventory.core.events import emit_event
from pos_inventory.domain.inventory.ledger import post_movement
from pos_inventory.domain.serials import service as serial_svc


@dataclass(frozen=True)
class ReturnLineInput:
    sku_id: UUID
    qty: Decimal
    reason_code: str
    disposition: str  # sellable | hold | scrap | vendor_rma
    target_location_id: UUID
    serial_value: str | None = None
    refund_amount: Decimal = Decimal("0")


@dataclass(frozen=True)
class ReturnInput:
    cashier_user_id: UUID
    occurred_at: datetime | None
    lines: list[ReturnLineInput]
    original_sale_id: UUID | None = None
    no_receipt: bool = False
    manager_approval_user_id: UUID | None = None
    refund_method: str = "original"


def _resolve_serial_id(sess: Session, *, tenant_id: UUID, sku_id: UUID, serial_value: str) -> UUID:
    row = sess.execute(
        text("SELECT id, sku_id FROM inv.serial WHERE tenant_id = :tid AND serial_value = :sv"),
        {"tid": str(tenant_id), "sv": serial_value},
    ).one_or_none()
    if row is None:
        raise NotFound(f"serial {serial_value}")
    if row[1] != sku_id:
        raise BusinessRuleConflict("serial does not belong to this SKU")
    return row[0]


def _no_receipt_serial_must_have_prior_sale(sess: Session, *, tenant_id: UUID, serial_id: UUID) -> None:
    row = sess.execute(
        text(
            """
            SELECT 1 FROM inv.ledger
             WHERE tenant_id = :tid AND serial_id = :sid AND source_kind = 'sale'
             LIMIT 1
            """
        ),
        {"tid": str(tenant_id), "sid": str(serial_id)},
    ).one_or_none()
    if row is None:
        raise BusinessRuleConflict("no-receipt return: serial has no prior sale by this tenant")


def post_return(
    sess: Session,
    *,
    tenant_id: UUID,
    actor_user_id: UUID,
    input: ReturnInput,
) -> UUID:
    if input.no_receipt:
        if input.manager_approval_user_id is None:
            raise BusinessRuleConflict("no-receipt return requires manager approval")
        # Q4 default policy: force refund to store_credit.
        refund_method = "store_credit"
    else:
        refund_method = input.refund_method

    if not input.lines:
        raise ValidationFailed("at least one return line required")

    return_id = uuid4()
    occurred_at = input.occurred_at or datetime.now(timezone.utc)
    refund_total = sum((l.refund_amount for l in input.lines), Decimal("0"))

    sess.execute(
        text(
            """
            INSERT INTO ret.customer_return
                (id, tenant_id, original_sale_id, occurred_at, cashier_user_id,
                 no_receipt, manager_approval_user_id, refund_method, refund_total)
            VALUES
                (:id, :tid, :osid, :ts, :uid, :nr, :mgr, :rm, :rt)
            """
        ),
        {
            "id": str(return_id),
            "tid": str(tenant_id),
            "osid": str(input.original_sale_id) if input.original_sale_id else None,
            "ts": occurred_at,
            "uid": str(input.cashier_user_id),
            "nr": input.no_receipt,
            "mgr": str(input.manager_approval_user_id) if input.manager_approval_user_id else None,
            "rm": refund_method,
            "rt": refund_total,
        },
    )

    for line in input.lines:
        if line.qty <= 0:
            raise ValidationFailed("qty must be > 0")
        if line.disposition not in {"sellable", "hold", "scrap", "vendor_rma"}:
            raise ValidationFailed(f"invalid disposition {line.disposition}")
        if not line.reason_code:
            raise ValidationFailed("reason_code required")

        serial_id: UUID | None = None
        if line.serial_value is not None:
            serial_id = _resolve_serial_id(sess, tenant_id=tenant_id, sku_id=line.sku_id, serial_value=line.serial_value)
            if input.no_receipt:
                _no_receipt_serial_must_have_prior_sale(sess, tenant_id=tenant_id, serial_id=serial_id)

        sess.execute(
            text(
                """
                INSERT INTO ret.customer_return_line
                    (id, tenant_id, return_id, sku_id, qty, serial_id,
                     reason_code, disposition, target_location_id, refund_amount)
                VALUES (:id, :tid, :rid, :sid, :q, :ser, :rc, :disp, :tlid, :ra)
                """
            ),
            {
                "id": str(uuid4()),
                "tid": str(tenant_id),
                "rid": str(return_id),
                "sid": str(line.sku_id),
                "q": line.qty,
                "ser": str(serial_id) if serial_id else None,
                "rc": line.reason_code,
                "disp": line.disposition,
                "tlid": str(line.target_location_id),
                "ra": line.refund_amount,
            },
        )

        # Inventory effect: post inbound to target_location_id (positive qty).
        # For scrap, post inbound to target_location_id and immediately scrap?
        # Simpler: post the movement and let the serial state convey scrap.
        if serial_id is not None:
            # Update serial state per disposition.
            if line.disposition == "scrap":
                # Skip ledger inbound for scrap — there's nothing to put back.
                # Transition sold→returned first so the scrap is legal.
                serial_svc.return_(sess, serial_id, target_location_id=line.target_location_id)
                serial_svc.mark_scrapped(sess, serial_id)
            else:
                post_movement(
                    sess,
                    tenant_id=tenant_id,
                    sku_id=line.sku_id,
                    location_id=line.target_location_id,
                    qty_delta=line.qty,
                    unit_cost=Decimal("0"),  # serial carries its own cost
                    source_kind="return",
                    source_doc_id=return_id,
                    serial_id=serial_id,
                    actor_user_id=actor_user_id,
                    occurred_at=occurred_at,
                    serial_state_after="returned",
                )
                if line.disposition == "vendor_rma":
                    serial_svc.mark_rma_pending(sess, serial_id)
        else:
            if line.disposition != "scrap":
                # Need a unit_cost for new cost layer; use 0 (returns don't
                # establish purchase cost). Better: derive from prior sale.
                post_movement(
                    sess,
                    tenant_id=tenant_id,
                    sku_id=line.sku_id,
                    location_id=line.target_location_id,
                    qty_delta=line.qty,
                    unit_cost=Decimal("0"),
                    source_kind="return",
                    source_doc_id=return_id,
                    actor_user_id=actor_user_id,
                    occurred_at=occurred_at,
                )

    write_audit(
        sess,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        target_kind="customer_return",
        target_id=return_id,
        action="posted",
        after={"no_receipt": input.no_receipt, "refund_method": refund_method, "lines": len(input.lines)},
    )
    emit_event(
        sess,
        tenant_id=tenant_id,
        event_type="customer_return.posted",
        payload={"customer_return_id": str(return_id), "no_receipt": input.no_receipt},
    )
    return return_id
