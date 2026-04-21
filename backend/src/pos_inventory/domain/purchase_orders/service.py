"""Purchase Order service: create + state transitions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.audit import write_audit
from pos_inventory.core.errors import NotFound
from pos_inventory.core.events import emit_event
from pos_inventory.domain.purchase_orders.state import TransitionRequest, assert_transition


@dataclass(frozen=True)
class PoLineInput:
    sku_id: UUID
    ordered_qty: Decimal
    unit_cost: Decimal


def create_po(
    sess: Session,
    *,
    tenant_id: UUID,
    actor_user_id: UUID,
    vendor_id: UUID,
    po_number: str,
    lines: list[PoLineInput],
) -> UUID:
    pid = uuid4()
    expected = sum((l.ordered_qty * l.unit_cost for l in lines), Decimal("0"))
    sess.execute(
        text(
            """
            INSERT INTO po.purchase_order
                (id, tenant_id, vendor_id, po_number, state, expected_total,
                 created_by, created_at)
            VALUES
                (:id, :tid, :vid, :pn, 'draft', :etot, :uid, :ts)
            """
        ),
        {
            "id": str(pid),
            "tid": str(tenant_id),
            "vid": str(vendor_id),
            "pn": po_number,
            "etot": expected,
            "uid": str(actor_user_id),
            "ts": datetime.now(timezone.utc),
        },
    )
    for line in lines:
        sess.execute(
            text(
                """
                INSERT INTO po.purchase_order_line
                    (id, tenant_id, po_id, sku_id, ordered_qty, received_qty,
                     backordered_qty, unit_cost)
                VALUES (:id, :tid, :pid, :sid, :oq, 0, :oq, :uc)
                """
            ),
            {
                "id": str(uuid4()),
                "tid": str(tenant_id),
                "pid": str(pid),
                "sid": str(line.sku_id),
                "oq": line.ordered_qty,
                "uc": line.unit_cost,
            },
        )
    write_audit(
        sess,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        target_kind="purchase_order",
        target_id=pid,
        action="created",
        after={"state": "draft", "po_number": po_number},
    )
    emit_event(
        sess,
        tenant_id=tenant_id,
        event_type="purchase_order.created",
        payload={"purchase_order_id": str(pid), "po_number": po_number},
    )
    return pid


def _load_state(sess: Session, *, tenant_id: UUID, po_id: UUID) -> str:
    row = sess.execute(
        text("SELECT state FROM po.purchase_order WHERE id = :id AND tenant_id = :tid FOR UPDATE"),
        {"id": str(po_id), "tid": str(tenant_id)},
    ).one_or_none()
    if row is None:
        raise NotFound(f"purchase order {po_id} not found")
    return row[0]


def _set_state(sess: Session, *, po_id: UUID, new_state: str, ts_field: str | None) -> None:
    extra = f", {ts_field} = :ts" if ts_field else ""
    sess.execute(
        text(f"UPDATE po.purchase_order SET state = :s{extra} WHERE id = :id"),
        {"s": new_state, "ts": datetime.now(timezone.utc), "id": str(po_id)},
    )


def transition(
    sess: Session,
    *,
    tenant_id: UUID,
    actor_user_id: UUID,
    actor_roles: frozenset[str],
    po_id: UUID,
    to_state: str,
) -> str:
    current = _load_state(sess, tenant_id=tenant_id, po_id=po_id)
    assert_transition(TransitionRequest(current, to_state, actor_roles))
    ts_field = {
        "submitted": "submitted_at",
        "approved": "approved_at",
        "sent": "sent_at",
        "closed": "closed_at",
        "cancelled": "cancelled_at",
        "receiving": None,
    }.get(to_state)
    _set_state(sess, po_id=po_id, new_state=to_state, ts_field=ts_field)
    write_audit(
        sess,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        target_kind="purchase_order",
        target_id=po_id,
        action=to_state,
        before={"state": current},
        after={"state": to_state},
    )
    if to_state in ("approved", "cancelled"):
        emit_event(
            sess,
            tenant_id=tenant_id,
            event_type=f"purchase_order.{to_state}",
            payload={"purchase_order_id": str(po_id)},
        )
    return to_state


def submit(sess, *, tenant_id, actor_user_id, actor_roles, po_id):  # noqa: ANN001
    return transition(sess, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_roles=actor_roles, po_id=po_id, to_state="submitted")


def approve(sess, *, tenant_id, actor_user_id, actor_roles, po_id):  # noqa: ANN001
    return transition(sess, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_roles=actor_roles, po_id=po_id, to_state="approved")


def send(sess, *, tenant_id, actor_user_id, actor_roles, po_id):  # noqa: ANN001
    return transition(sess, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_roles=actor_roles, po_id=po_id, to_state="sent")


def cancel(sess, *, tenant_id, actor_user_id, actor_roles, po_id):  # noqa: ANN001
    return transition(sess, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_roles=actor_roles, po_id=po_id, to_state="cancelled")
