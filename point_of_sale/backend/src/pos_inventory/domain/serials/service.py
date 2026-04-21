"""Serial lifecycle service.

Each call locks the serial row with SELECT ... FOR UPDATE, validates the
current state against the FR-012 transition diagram, and updates the row.
The companion `inv.ledger` row is written by the caller via
`pos_inventory.domain.inventory.ledger.post_movement`.
"""

from __future__ import annotations

from typing import Iterable
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.errors import BusinessRuleConflict, NotFound

# State -> set of allowed next states (FR-012).
TRANSITIONS: dict[str, set[str]] = {
    "received": {"sellable", "scrapped"},
    "sellable": {"reserved", "sold", "in_transit", "scrapped"},
    "reserved": {"sellable", "sold"},
    "sold": {"returned"},
    "returned": {"sellable", "rma_pending", "scrapped"},
    "rma_pending": {"rma_closed", "sellable"},
    "rma_closed": set(),
    "in_transit": {"sellable", "scrapped"},
    "scrapped": set(),
}


def _lock(sess: Session, serial_id: UUID) -> tuple[str, UUID | None]:
    row = sess.execute(
        text("SELECT state, current_location_id FROM inv.serial WHERE id = :id FOR UPDATE"),
        {"id": str(serial_id)},
    ).one_or_none()
    if row is None:
        raise NotFound(f"serial {serial_id}")
    return row[0], row[1]


def _set_state(
    sess: Session,
    serial_id: UUID,
    new_state: str,
    *,
    new_location_id: UUID | None = None,
    clear_location: bool = False,
) -> None:
    if clear_location:
        sess.execute(
            text("UPDATE inv.serial SET state = :s, current_location_id = NULL WHERE id = :id"),
            {"s": new_state, "id": str(serial_id)},
        )
    elif new_location_id is not None:
        sess.execute(
            text("UPDATE inv.serial SET state = :s, current_location_id = :lid WHERE id = :id"),
            {"s": new_state, "lid": str(new_location_id), "id": str(serial_id)},
        )
    else:
        sess.execute(
            text("UPDATE inv.serial SET state = :s WHERE id = :id"),
            {"s": new_state, "id": str(serial_id)},
        )


def transition(sess: Session, serial_id: UUID, new_state: str) -> str:
    current, _ = _lock(sess, serial_id)
    if new_state not in TRANSITIONS.get(current, set()):
        raise BusinessRuleConflict(f"illegal serial transition {current} -> {new_state}")
    _set_state(sess, serial_id, new_state)
    return new_state


def reserve(sess: Session, serial_id: UUID) -> str:
    return transition(sess, serial_id, "reserved")


def sell(sess: Session, serial_id: UUID) -> str:
    current, _ = _lock(sess, serial_id)
    if current not in {"sellable", "reserved"}:
        raise BusinessRuleConflict(f"serial {serial_id} not sellable (state={current})")
    _set_state(sess, serial_id, "sold", clear_location=True)
    return "sold"


def return_(sess: Session, serial_id: UUID, *, target_location_id: UUID) -> str:
    current, _ = _lock(sess, serial_id)
    if current != "sold":
        raise BusinessRuleConflict(f"only sold serials can be returned (state={current})")
    _set_state(sess, serial_id, "returned", new_location_id=target_location_id)
    return "returned"


def mark_rma_pending(sess: Session, serial_id: UUID) -> str:
    return transition(sess, serial_id, "rma_pending")


def mark_rma_closed(sess: Session, serial_id: UUID) -> str:
    current, _ = _lock(sess, serial_id)
    if current != "rma_pending":
        raise BusinessRuleConflict(f"rma close requires rma_pending (state={current})")
    _set_state(sess, serial_id, "rma_closed", clear_location=True)
    return "rma_closed"


def mark_scrapped(sess: Session, serial_id: UUID) -> str:
    current, _ = _lock(sess, serial_id)
    if "scrapped" not in TRANSITIONS.get(current, set()):
        raise BusinessRuleConflict(f"cannot scrap from state {current}")
    _set_state(sess, serial_id, "scrapped", clear_location=True)
    return "scrapped"


def bulk_assert_sellable(sess: Session, serial_ids: Iterable[UUID]) -> None:
    ids = [str(s) for s in serial_ids]
    if not ids:
        return
    rows = sess.execute(
        text("SELECT id, state FROM inv.serial WHERE id = ANY(:ids) FOR UPDATE"),
        {"ids": ids},
    ).all()
    bad = [r[0] for r in rows if r[1] not in {"sellable", "reserved"}]
    if bad:
        raise BusinessRuleConflict(f"serials not sellable: {bad}")
