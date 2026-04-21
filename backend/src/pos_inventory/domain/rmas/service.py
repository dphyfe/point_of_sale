"""Vendor RMA service: open → shipped → closed (FR-017/018/035)."""

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
class RmaLineInput:
    sku_id: UUID
    qty: Decimal
    serial_id: UUID | None = None
    unit_cost: Decimal = Decimal("0")


@dataclass(frozen=True)
class RmaInput:
    vendor_id: UUID
    holding_location_id: UUID
    originating_po_id: UUID | None
    lines: list[RmaLineInput]


def create_rma(sess: Session, *, tenant_id: UUID, actor_user_id: UUID, input: RmaInput) -> UUID:
    if not input.lines:
        raise ValidationFailed("at least one rma line required")
    rid = uuid4()
    sess.execute(
        text(
            """
            INSERT INTO rma.vendor_rma
                (id, tenant_id, vendor_id, originating_po_id, state,
                 holding_location_id, created_at, credit_total)
            VALUES (:id, :tid, :vid, :opid, 'open', :hlid, :ts, 0)
            """
        ),
        {
            "id": str(rid),
            "tid": str(tenant_id),
            "vid": str(input.vendor_id),
            "opid": str(input.originating_po_id) if input.originating_po_id else None,
            "hlid": str(input.holding_location_id),
            "ts": datetime.now(timezone.utc),
        },
    )
    for line in input.lines:
        if line.qty <= 0:
            raise ValidationFailed("qty must be > 0")
        sess.execute(
            text(
                """
                INSERT INTO rma.vendor_rma_line
                    (id, tenant_id, rma_id, sku_id, qty, serial_id, unit_cost)
                VALUES (:id, :tid, :rid, :sid, :q, :ser, :uc)
                """
            ),
            {
                "id": str(uuid4()),
                "tid": str(tenant_id),
                "rid": str(rid),
                "sid": str(line.sku_id),
                "q": line.qty,
                "ser": str(line.serial_id) if line.serial_id else None,
                "uc": line.unit_cost,
            },
        )
    write_audit(
        sess,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        target_kind="vendor_rma",
        target_id=rid,
        action="created",
        after={"state": "open", "vendor_id": str(input.vendor_id)},
    )
    emit_event(
        sess,
        tenant_id=tenant_id,
        event_type="vendor_rma.created",
        payload={"vendor_rma_id": str(rid), "vendor_id": str(input.vendor_id)},
    )
    return rid


def _load_rma(sess: Session, rid: UUID) -> tuple[str, UUID]:
    row = sess.execute(
        text("SELECT state, holding_location_id FROM rma.vendor_rma WHERE id = :id FOR UPDATE"),
        {"id": str(rid)},
    ).one_or_none()
    if row is None:
        raise NotFound(f"rma {rid}")
    return row[0], row[1]


def _lines(sess: Session, rid: UUID) -> list[tuple]:
    return sess.execute(
        text("SELECT id, sku_id, qty, serial_id, unit_cost FROM rma.vendor_rma_line WHERE rma_id = :id"),
        {"id": str(rid)},
    ).all()


def ship_rma(sess: Session, *, tenant_id: UUID, actor_user_id: UUID, rma_id: UUID) -> str:
    state, holding_loc = _load_rma(sess, rma_id)
    if state != "open":
        raise BusinessRuleConflict(f"rma must be open to ship (was {state})")
    now = datetime.now(timezone.utc)
    for _lid, sku_id, qty, serial_id, unit_cost in _lines(sess, rma_id):
        post_movement(
            sess,
            tenant_id=tenant_id,
            sku_id=sku_id,
            location_id=holding_loc,
            qty_delta=-Decimal(qty),
            source_kind="rma_ship",
            source_doc_id=rma_id,
            serial_id=serial_id,
            actor_user_id=actor_user_id,
            occurred_at=now,
            # serial stays rma_pending while shipped
        )
    sess.execute(
        text("UPDATE rma.vendor_rma SET state = 'shipped', shipped_at = :ts WHERE id = :id"),
        {"ts": now, "id": str(rma_id)},
    )
    write_audit(
        sess,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        target_kind="vendor_rma",
        target_id=rma_id,
        action="shipped",
        before={"state": "open"},
        after={"state": "shipped"},
    )
    return "shipped"


def close_rma(sess: Session, *, tenant_id: UUID, actor_user_id: UUID, rma_id: UUID) -> Decimal:
    state, _ = _load_rma(sess, rma_id)
    if state != "shipped":
        raise BusinessRuleConflict(f"rma must be shipped to close (was {state})")
    credit_total = Decimal("0")
    for _lid, sku_id, qty, serial_id, unit_cost in _lines(sess, rma_id):
        if serial_id is not None:
            # Use the serial's stored unit_cost (FIFO origin already baked in).
            srow = sess.execute(
                text("SELECT unit_cost FROM inv.serial WHERE id = :id"),
                {"id": str(serial_id)},
            ).one_or_none()
            cost = Decimal(srow[0]) if srow else Decimal(unit_cost)
            credit_total += cost * Decimal(qty)
            serial_svc.mark_rma_closed(sess, serial_id)
        else:
            credit_total += Decimal(unit_cost) * Decimal(qty)
    sess.execute(
        text("UPDATE rma.vendor_rma SET state = 'closed', closed_at = :ts, credit_total = :ct WHERE id = :id"),
        {"ts": datetime.now(timezone.utc), "ct": credit_total, "id": str(rma_id)},
    )
    write_audit(
        sess,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        target_kind="vendor_rma",
        target_id=rma_id,
        action="closed",
        before={"state": "shipped"},
        after={"state": "closed", "credit_total": str(credit_total)},
    )
    emit_event(
        sess,
        tenant_id=tenant_id,
        event_type="vendor_rma.closed",
        payload={"vendor_rma_id": str(rma_id), "credit_total": str(credit_total)},
    )
    return credit_total
