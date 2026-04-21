"""Receipt posting: validates state + serial/lot rules and updates PO line totals."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.audit import write_audit
from pos_inventory.core.config import get_settings
from pos_inventory.core.errors import BusinessRuleConflict, NotFound, ValidationFailed
from pos_inventory.core.events import emit_event
from pos_inventory.domain.inventory.ledger import post_movement


@dataclass(frozen=True)
class ReceiptLineInput:
    po_line_id: UUID
    received_qty: Decimal
    serial_values: list[str] = field(default_factory=list)
    lot_code: str | None = None


@dataclass(frozen=True)
class ReceivedLine:
    receipt_line_id: UUID
    po_line_id: UUID
    received_qty: Decimal
    overage_qty: Decimal
    backordered_qty: Decimal
    unit_cost: Decimal


def _load_po_state_and_lock(sess: Session, *, tenant_id: UUID, po_id: UUID) -> str:
    row = sess.execute(
        text("SELECT state FROM po.purchase_order WHERE id = :id AND tenant_id = :tid FOR UPDATE"),
        {"id": str(po_id), "tid": str(tenant_id)},
    ).one_or_none()
    if row is None:
        raise NotFound(f"purchase order {po_id} not found")
    return row[0]


def _load_po_line(sess: Session, *, po_line_id: UUID) -> tuple[UUID, str, str, Decimal, Decimal, Decimal, int | None]:
    row = sess.execute(
        text(
            """
            SELECT pol.sku_id, sku.tracking, sku.sku_code,
                   pol.ordered_qty, pol.received_qty, pol.unit_cost,
                   sku.over_receive_tolerance_pct
              FROM po.purchase_order_line pol
              JOIN inv.sku ON sku.id = pol.sku_id
             WHERE pol.id = :id
             FOR UPDATE OF pol
            """
        ),
        {"id": str(po_line_id)},
    ).one_or_none()
    if row is None:
        raise NotFound(f"po_line {po_line_id} not found")
    return row  # type: ignore[return-value]


def _ensure_serials_unique(sess: Session, *, tenant_id: UUID, sku_id: UUID, serials: Iterable[str]) -> list[str]:
    serials = list(serials)
    if len(set(serials)) != len(serials):
        raise ValidationFailed("duplicate serials in input")
    if not serials:
        return serials
    existing = (
        sess.execute(
            text("SELECT serial_value FROM inv.serial WHERE tenant_id = :tid AND serial_value = ANY(:vals)"),
            {"tid": str(tenant_id), "vals": serials},
        )
        .scalars()
        .all()
    )
    if existing:
        raise BusinessRuleConflict(f"serial(s) already known: {sorted(existing)[:5]}")
    return serials


def _get_or_create_lot(sess: Session, *, tenant_id: UUID, sku_id: UUID, lot_code: str) -> UUID:
    row = sess.execute(
        text("SELECT id FROM inv.lot WHERE tenant_id = :tid AND sku_id = :sid AND lot_code = :lc"),
        {"tid": str(tenant_id), "sid": str(sku_id), "lc": lot_code},
    ).one_or_none()
    if row is not None:
        return row[0]
    lid = uuid4()
    sess.execute(
        text("INSERT INTO inv.lot (id, tenant_id, sku_id, lot_code, created_at) VALUES (:id, :tid, :sid, :lc, :ts)"),
        {"id": str(lid), "tid": str(tenant_id), "sid": str(sku_id), "lc": lot_code, "ts": datetime.now(timezone.utc)},
    )
    return lid


def post_receipt(
    sess: Session,
    *,
    tenant_id: UUID,
    actor_user_id: UUID,
    po_id: UUID,
    location_id: UUID,
    lines: list[ReceiptLineInput],
) -> tuple[UUID, list[ReceivedLine]]:
    settings = get_settings()
    state = _load_po_state_and_lock(sess, tenant_id=tenant_id, po_id=po_id)
    if state not in {"approved", "sent", "receiving"}:
        raise BusinessRuleConflict(f"PO must be approved/sent/receiving (was {state})")

    # Move PO into receiving on first receipt.
    if state != "receiving":
        sess.execute(
            text("UPDATE po.purchase_order SET state = 'receiving' WHERE id = :id"),
            {"id": str(po_id)},
        )

    receipt_id = uuid4()
    now = datetime.now(timezone.utc)
    sess.execute(
        text("INSERT INTO po.receipt (id, tenant_id, po_id, location_id, occurred_at, received_by) VALUES (:id, :tid, :pid, :lid, :ts, :uid)"),
        {
            "id": str(receipt_id),
            "tid": str(tenant_id),
            "pid": str(po_id),
            "lid": str(location_id),
            "ts": now,
            "uid": str(actor_user_id),
        },
    )

    received_lines: list[ReceivedLine] = []
    all_lines_complete = True

    for line in lines:
        if line.received_qty <= 0:
            raise ValidationFailed("received_qty must be > 0")

        sku_id, tracking, sku_code, ordered_qty, received_so_far, unit_cost, sku_tol = _load_po_line(sess, po_line_id=line.po_line_id)

        # Tolerance (FR-005)
        tol_pct = sku_tol if sku_tol is not None else settings.over_receive_tolerance_pct_default
        max_total = Decimal(ordered_qty) * (Decimal(100) + Decimal(tol_pct)) / Decimal(100)
        new_total = Decimal(received_so_far) + Decimal(line.received_qty)
        if new_total > max_total:
            raise BusinessRuleConflict(f"over-receive of {sku_code} exceeds tolerance ({tol_pct}%)")
        overage = max(Decimal("0"), new_total - Decimal(ordered_qty))
        backordered = max(Decimal("0"), Decimal(ordered_qty) - new_total)

        # Tracking-specific validation
        lot_id: UUID | None = None
        if tracking == "serialized":
            if len(line.serial_values) != int(line.received_qty):
                raise ValidationFailed(f"serialized SKU {sku_code} requires N distinct serials matching received_qty")
            _ensure_serials_unique(sess, tenant_id=tenant_id, sku_id=sku_id, serials=line.serial_values)
        elif tracking == "lot_tracked":
            if not line.lot_code:
                raise ValidationFailed(f"lot_tracked SKU {sku_code} requires lot_code")
            lot_id = _get_or_create_lot(sess, tenant_id=tenant_id, sku_id=sku_id, lot_code=line.lot_code)

        rl_id = uuid4()
        sess.execute(
            text(
                """
                INSERT INTO po.receipt_line
                    (id, tenant_id, receipt_id, po_line_id, received_qty, overage_qty, lot_code, unit_cost)
                VALUES (:id, :tid, :rid, :plid, :rq, :ovr, :lc, :uc)
                """
            ),
            {
                "id": str(rl_id),
                "tid": str(tenant_id),
                "rid": str(receipt_id),
                "plid": str(line.po_line_id),
                "rq": line.received_qty,
                "ovr": overage,
                "lc": line.lot_code,
                "uc": Decimal(unit_cost),
            },
        )

        # Post inventory movements
        if tracking == "serialized":
            for sv in line.serial_values:
                serial_id = uuid4()
                sess.execute(
                    text(
                        """
                        INSERT INTO inv.serial
                            (id, tenant_id, sku_id, serial_value, state, current_location_id, unit_cost, received_at)
                        VALUES (:id, :tid, :sid, :sv, 'received', :lid, :uc, :ts)
                        """
                    ),
                    {
                        "id": str(serial_id),
                        "tid": str(tenant_id),
                        "sid": str(sku_id),
                        "sv": sv,
                        "lid": str(location_id),
                        "uc": Decimal(unit_cost),
                        "ts": now,
                    },
                )
                sess.execute(
                    text("INSERT INTO po.receipt_serial (id, tenant_id, receipt_line_id, serial_value) VALUES (:id, :tid, :rl, :sv)"),
                    {"id": str(uuid4()), "tid": str(tenant_id), "rl": str(rl_id), "sv": sv},
                )
                post_movement(
                    sess,
                    tenant_id=tenant_id,
                    sku_id=sku_id,
                    location_id=location_id,
                    qty_delta=Decimal("1"),
                    unit_cost=Decimal(unit_cost),
                    source_kind="po_receipt",
                    source_doc_id=receipt_id,
                    serial_id=serial_id,
                    actor_user_id=actor_user_id,
                    occurred_at=now,
                    serial_state_after="sellable",
                )
        else:
            post_movement(
                sess,
                tenant_id=tenant_id,
                sku_id=sku_id,
                location_id=location_id,
                qty_delta=Decimal(line.received_qty),
                unit_cost=Decimal(unit_cost),
                source_kind="po_receipt",
                source_doc_id=receipt_id,
                lot_id=lot_id,
                actor_user_id=actor_user_id,
                occurred_at=now,
            )

        # Update PO line totals
        sess.execute(
            text(
                """
                UPDATE po.purchase_order_line
                   SET received_qty = :rq, backordered_qty = :bo
                 WHERE id = :id
                """
            ),
            {"rq": new_total, "bo": backordered, "id": str(line.po_line_id)},
        )

        if backordered > 0:
            all_lines_complete = False
        received_lines.append(
            ReceivedLine(
                receipt_line_id=rl_id,
                po_line_id=line.po_line_id,
                received_qty=Decimal(line.received_qty),
                overage_qty=overage,
                backordered_qty=backordered,
                unit_cost=Decimal(unit_cost),
            )
        )

    # Check whether ALL po_lines are now complete (across all receipts, not just this one)
    if all_lines_complete:
        outstanding = sess.execute(
            text("SELECT COUNT(*) FROM po.purchase_order_line WHERE po_id = :pid AND backordered_qty > 0"),
            {"pid": str(po_id)},
        ).scalar_one()
        if outstanding == 0:
            sess.execute(
                text("UPDATE po.purchase_order SET state = 'closed', closed_at = :ts WHERE id = :id"),
                {"ts": now, "id": str(po_id)},
            )
            write_audit(
                sess,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                target_kind="purchase_order",
                target_id=po_id,
                action="closed",
                after={"state": "closed"},
            )

    write_audit(
        sess,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        target_kind="receipt",
        target_id=receipt_id,
        action="posted",
        after={"po_id": str(po_id), "lines": len(received_lines)},
    )
    emit_event(
        sess,
        tenant_id=tenant_id,
        event_type="receipt.posted",
        payload={
            "receipt_id": str(receipt_id),
            "purchase_order_id": str(po_id),
            "location_id": str(location_id),
            "lines": [{"po_line_id": str(rl.po_line_id), "received_qty": str(rl.received_qty)} for rl in received_lines],
        },
    )
    return receipt_id, received_lines
