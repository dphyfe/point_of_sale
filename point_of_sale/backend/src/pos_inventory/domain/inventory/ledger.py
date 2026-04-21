"""Inventory ledger writer — the only path that mutates `inv.balance`,
`inv.cost_layer`, and serial location/state in concert with `inv.ledger`.

All callers must hold an open SQLAlchemy Session. The writer:

1. Acquires `SELECT ... FOR UPDATE` on the affected `inv.balance` row,
   plus the affected `inv.serial` row (when serial-tracked) or the
   FIFO `inv.cost_layer` rows (for outbound non-serial movements).
2. For inbound (qty_delta > 0): creates/upserts a cost_layer with the
   inbound unit_cost, and increments balance.on_hand. For serial-tracked
   inbound, persists the unit_cost on the serial row and sets state.
3. For outbound (qty_delta < 0): for serial-tracked, computes unit_cost
   from the serial; for others, consumes FIFO cost layers (oldest first)
   to compute the outbound unit_cost.
4. Inserts the immutable `inv.ledger` row with the resolved unit_cost.
5. Updates serial state/current_location_id when serial-tracked.

(See research.md R1, R2; FR-033, FR-035.)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.errors import BusinessRuleConflict, ValidationFailed

SourceKind = Literal[
    "po_receipt",
    "sale",
    "return",
    "rma_ship",
    "transfer_ship",
    "transfer_receive",
    "count_adjustment",
    "scrap",
]


@dataclass(frozen=True)
class LedgerResult:
    ledger_id: UUID
    unit_cost: Decimal


def _ensure_balance_locked(sess: Session, *, tenant_id: UUID, sku_id: UUID, location_id: UUID) -> tuple[Decimal, Decimal]:
    row = sess.execute(
        text(
            """
            SELECT on_hand, reserved
              FROM inv.balance
             WHERE tenant_id = :tid AND sku_id = :sid AND location_id = :lid
             FOR UPDATE
            """
        ),
        {"tid": str(tenant_id), "sid": str(sku_id), "lid": str(location_id)},
    ).one_or_none()
    if row is None:
        sess.execute(
            text(
                """
                INSERT INTO inv.balance (tenant_id, sku_id, location_id, on_hand, reserved)
                VALUES (:tid, :sid, :lid, 0, 0)
                ON CONFLICT DO NOTHING
                """
            ),
            {"tid": str(tenant_id), "sid": str(sku_id), "lid": str(location_id)},
        )
        return Decimal("0"), Decimal("0")
    return Decimal(row[0]), Decimal(row[1])


def _consume_fifo(
    sess: Session,
    *,
    tenant_id: UUID,
    sku_id: UUID,
    location_id: UUID,
    qty: Decimal,
) -> Decimal:
    """Consume qty (positive) from FIFO cost layers; return qty-weighted unit_cost."""
    layers = sess.execute(
        text(
            """
            SELECT id, qty_remaining, unit_cost
              FROM inv.cost_layer
             WHERE tenant_id = :tid AND sku_id = :sid AND location_id = :lid
               AND qty_remaining > 0
             ORDER BY received_at ASC, id ASC
             FOR UPDATE
            """
        ),
        {"tid": str(tenant_id), "sid": str(sku_id), "lid": str(location_id)},
    ).all()

    remaining = qty
    cost_total = Decimal("0")
    for lid, qty_rem, unit_cost in layers:
        if remaining <= 0:
            break
        take = min(Decimal(qty_rem), remaining)
        cost_total += take * Decimal(unit_cost)
        sess.execute(
            text("UPDATE inv.cost_layer SET qty_remaining = qty_remaining - :t WHERE id = :id"),
            {"t": take, "id": str(lid)},
        )
        remaining -= take

    if remaining > 0:
        # Allow negative inventory? No — block.
        raise BusinessRuleConflict(f"Insufficient cost layers for sku={sku_id} loc={location_id}; short by {remaining}")
    return (cost_total / qty).quantize(Decimal("0.0001"))


def post_movement(
    sess: Session,
    *,
    tenant_id: UUID,
    sku_id: UUID,
    location_id: UUID,
    qty_delta: Decimal,
    source_kind: SourceKind,
    source_doc_id: UUID,
    serial_id: UUID | None = None,
    lot_id: UUID | None = None,
    unit_cost: Decimal | None = None,
    client_intake_id: UUID | None = None,
    actor_user_id: UUID | None = None,
    occurred_at: datetime | None = None,
    serial_state_after: str | None = None,
) -> LedgerResult:
    if qty_delta == 0:
        raise ValidationFailed("qty_delta must be non-zero")

    occurred_at = occurred_at or datetime.now(timezone.utc)
    on_hand, reserved = _ensure_balance_locked(sess, tenant_id=tenant_id, sku_id=sku_id, location_id=location_id)

    resolved_unit_cost: Decimal

    if serial_id is not None:
        # Lock the serial row.
        srow = sess.execute(
            text("SELECT unit_cost, current_location_id, state FROM inv.serial WHERE id = :id FOR UPDATE"),
            {"id": str(serial_id)},
        ).one_or_none()
        if srow is None:
            raise ValidationFailed(f"unknown serial_id {serial_id}")
        if qty_delta > 0:
            # Inbound: persist unit_cost on serial. For transfer-style
            # inbounds the serial keeps its existing cost; only require
            # unit_cost when the serial has none yet (initial receipt).
            if unit_cost is None:
                existing_uc = srow[0]
                if existing_uc is None:
                    raise ValidationFailed("unit_cost required for inbound serialized movement")
                resolved_unit_cost = Decimal(existing_uc)
                sess.execute(
                    text(
                        """
                        UPDATE inv.serial
                           SET current_location_id = :lid,
                               state = COALESCE(:state, state),
                               received_at = COALESCE(received_at, :ts)
                         WHERE id = :id
                        """
                    ),
                    {
                        "lid": str(location_id),
                        "state": serial_state_after,
                        "ts": occurred_at,
                        "id": str(serial_id),
                    },
                )
            else:
                resolved_unit_cost = Decimal(unit_cost)
                sess.execute(
                    text(
                        """
                        UPDATE inv.serial
                           SET unit_cost = :uc,
                               current_location_id = :lid,
                               state = COALESCE(:state, state),
                               received_at = COALESCE(received_at, :ts)
                         WHERE id = :id
                        """
                    ),
                    {
                        "uc": resolved_unit_cost,
                        "lid": str(location_id),
                        "state": serial_state_after,
                        "ts": occurred_at,
                        "id": str(serial_id),
                    },
                )
        else:
            resolved_unit_cost = Decimal(srow[0])
            sess.execute(
                text(
                    """
                    UPDATE inv.serial
                       SET current_location_id = CASE WHEN :null_loc THEN NULL ELSE :lid END,
                           state = COALESCE(:state, state)
                     WHERE id = :id
                    """
                ),
                {
                    "null_loc": serial_state_after in ("sold", "scrapped", "rma_closed"),
                    "lid": str(location_id) if serial_state_after in ("transfer_receive", None, "in_transit", "received", "returned", "rma_pending") else None,
                    "state": serial_state_after,
                    "id": str(serial_id),
                },
            )
    else:
        if qty_delta > 0:
            if unit_cost is None:
                raise ValidationFailed("unit_cost required for inbound non-serialized movement")
            resolved_unit_cost = Decimal(unit_cost)
            sess.execute(
                text(
                    """
                    INSERT INTO inv.cost_layer
                        (id, tenant_id, sku_id, location_id, received_at, qty_remaining, unit_cost)
                    VALUES (:id, :tid, :sid, :lid, :ts, :qr, :uc)
                    """
                ),
                {
                    "id": str(uuid4()),
                    "tid": str(tenant_id),
                    "sid": str(sku_id),
                    "lid": str(location_id),
                    "ts": occurred_at,
                    "qr": qty_delta,
                    "uc": resolved_unit_cost,
                },
            )
        else:
            resolved_unit_cost = _consume_fifo(
                sess,
                tenant_id=tenant_id,
                sku_id=sku_id,
                location_id=location_id,
                qty=-qty_delta,
            )

    new_on_hand = on_hand + qty_delta
    if new_on_hand < 0:
        raise BusinessRuleConflict("Insufficient on-hand for outbound movement")

    sess.execute(
        text(
            """
            UPDATE inv.balance
               SET on_hand = :oh
             WHERE tenant_id = :tid AND sku_id = :sid AND location_id = :lid
            """
        ),
        {"oh": new_on_hand, "tid": str(tenant_id), "sid": str(sku_id), "lid": str(location_id)},
    )

    ledger_id = uuid4()
    sess.execute(
        text(
            """
            INSERT INTO inv.ledger
                (id, tenant_id, occurred_at, sku_id, location_id, qty_delta,
                 unit_cost, source_kind, source_doc_id, serial_id, lot_id,
                 client_intake_id, actor_user_id)
            VALUES
                (:id, :tid, :ts, :sid, :lid, :qd, :uc, :sk, :doc, :ser, :lot,
                 :cli, :uid)
            """
        ),
        {
            "id": str(ledger_id),
            "tid": str(tenant_id),
            "ts": occurred_at,
            "sid": str(sku_id),
            "lid": str(location_id),
            "qd": qty_delta,
            "uc": resolved_unit_cost,
            "sk": source_kind,
            "doc": str(source_doc_id),
            "ser": str(serial_id) if serial_id else None,
            "lot": str(lot_id) if lot_id else None,
            "cli": str(client_intake_id) if client_intake_id else None,
            "uid": str(actor_user_id) if actor_user_id else None,
        },
    )
    return LedgerResult(ledger_id=ledger_id, unit_cost=resolved_unit_cost)
