"""Count variance computation (FR-023, FR-035)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.errors import NotFound


@dataclass(frozen=True)
class VarianceRow:
    sku_id: UUID
    location_id: UUID
    system_at_open: Decimal
    delta_movements: Decimal
    counted_qty: Decimal
    variance_qty: Decimal
    variance_value: Decimal


def compute_variance(sess: Session, *, tenant_id: UUID, session_id: UUID) -> list[VarianceRow]:
    sess_row = sess.execute(
        text("SELECT created_at, closed_at FROM cnt.count_session WHERE id = :id"),
        {"id": str(session_id)},
    ).one_or_none()
    if sess_row is None:
        raise NotFound(f"count session {session_id}")
    opened_at = sess_row[0]

    snaps = sess.execute(
        text(
            """
            SELECT sku_id, location_id, on_hand_at_open
              FROM cnt.count_session_snapshot
             WHERE tenant_id = :tid AND session_id = :sid
            """
        ),
        {"tid": str(tenant_id), "sid": str(session_id)},
    ).all()

    out: list[VarianceRow] = []
    for sku_id, loc_id, opening in snaps:
        # Movements during the session window for this (sku, location).
        delta = sess.execute(
            text(
                """
                SELECT COALESCE(SUM(qty_delta), 0)
                  FROM inv.ledger
                 WHERE tenant_id = :tid
                   AND sku_id = :sku
                   AND location_id = :loc
                   AND occurred_at >= :ts
                """
            ),
            {"tid": str(tenant_id), "sku": str(sku_id), "loc": str(loc_id), "ts": opened_at},
        ).scalar_one()
        delta = Decimal(delta or 0)

        # Sum counted entries.
        counted = sess.execute(
            text(
                """
                SELECT COALESCE(SUM(counted_qty), 0)
                  FROM cnt.count_entry
                 WHERE tenant_id = :tid AND session_id = :sid
                   AND sku_id = :sku AND location_id = :loc
                """
            ),
            {"tid": str(tenant_id), "sid": str(session_id), "sku": str(sku_id), "loc": str(loc_id)},
        ).scalar_one()
        counted = Decimal(counted or 0)

        opening = Decimal(opening)
        variance_qty = counted - (opening + delta)

        # Value variance: use current oldest cost layer for non-serialized,
        # else 0 (serialized variance is rare and uses serial.unit_cost).
        unit_cost_row = sess.execute(
            text(
                """
                SELECT unit_cost FROM inv.cost_layer
                 WHERE tenant_id = :tid AND sku_id = :sku AND location_id = :loc
                   AND remaining_qty > 0
                 ORDER BY received_at ASC
                 LIMIT 1
                """
            ),
            {"tid": str(tenant_id), "sku": str(sku_id), "loc": str(loc_id)},
        ).one_or_none()
        unit_cost = Decimal(unit_cost_row[0]) if unit_cost_row else Decimal("0")
        variance_value = variance_qty * unit_cost

        out.append(
            VarianceRow(
                sku_id=sku_id,
                location_id=loc_id,
                system_at_open=opening,
                delta_movements=delta,
                counted_qty=counted,
                variance_qty=variance_qty,
                variance_value=variance_value,
            )
        )
    return out
