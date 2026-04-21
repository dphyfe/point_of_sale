"""Count session service (FR-019..FR-024)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.audit import write_audit
from pos_inventory.core.errors import BusinessRuleConflict, NotFound, ValidationFailed


@dataclass(frozen=True)
class CountScope:
    site_id: UUID
    location_ids: list[UUID] | None = None  # None = all locations under site
    sku_ids: list[UUID] | None = None  # None = all SKUs


@dataclass(frozen=True)
class EntryInput:
    sku_id: UUID
    location_id: UUID
    counted_qty: Decimal
    counter_user_id: UUID
    serial_value: str | None = None


def _scope_pairs(sess: Session, *, tenant_id: UUID, scope: CountScope) -> list[tuple[UUID, UUID, Decimal]]:
    """Return (sku_id, location_id, on_hand) for in-scope balance rows."""
    where = ["tenant_id = :tid"]
    params: dict = {"tid": str(tenant_id)}
    if scope.location_ids is not None:
        where.append("location_id = ANY(:lids)")
        params["lids"] = [str(x) for x in scope.location_ids]
    else:
        where.append("location_id IN (SELECT id FROM inv.location WHERE site_id = :sid AND tenant_id = :tid)")
        params["sid"] = str(scope.site_id)
    if scope.sku_ids is not None:
        where.append("sku_id = ANY(:skids)")
        params["skids"] = [str(x) for x in scope.sku_ids]
    rows = sess.execute(
        text("SELECT sku_id, location_id, on_hand FROM inv.balance WHERE " + " AND ".join(where)),
        params,
    ).all()
    return [(r[0], r[1], Decimal(r[2])) for r in rows]


def create_session(
    sess: Session,
    *,
    tenant_id: UUID,
    actor_user_id: UUID,
    scope: CountScope,
    hide_system_qty: bool = True,
) -> UUID:
    sid = uuid4()
    now = datetime.now(timezone.utc)
    sess.execute(
        text(
            """
            INSERT INTO cnt.count_session
                (id, tenant_id, site_id, state, created_at, hide_system_qty, scope_kind, created_by)
            VALUES (:id, :tid, :sid, 'open', :ts, :hide, :sk, :uid)
            """
        ),
        {
            "id": str(sid),
            "tid": str(tenant_id),
            "sid": str(scope.site_id),
            "ts": now,
            "hide": hide_system_qty,
            "sk": "partial" if (scope.location_ids or scope.sku_ids) else "full",
            "uid": str(actor_user_id),
        },
    )
    pairs = _scope_pairs(sess, tenant_id=tenant_id, scope=scope)
    for sku_id, loc_id, on_hand in pairs:
        sess.execute(
            text(
                """
                INSERT INTO cnt.count_session_snapshot
                    (id, tenant_id, session_id, sku_id, location_id, on_hand_at_open)
                VALUES (:id, :tid, :sess, :sku, :loc, :oh)
                """
            ),
            {
                "id": str(uuid4()),
                "tid": str(tenant_id),
                "sess": str(sid),
                "sku": str(sku_id),
                "loc": str(loc_id),
                "oh": on_hand,
            },
        )
    write_audit(
        sess,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        target_kind="count_session",
        target_id=sid,
        action="created",
        after={"site_id": str(scope.site_id), "pairs": len(pairs), "hide_system_qty": hide_system_qty},
    )
    return sid


def assign(sess: Session, *, tenant_id: UUID, session_id: UUID, user_id: UUID, location_id: UUID) -> UUID:
    aid = uuid4()
    sess.execute(
        text(
            """
            INSERT INTO cnt.count_assignment (id, tenant_id, session_id, user_id, location_id)
            VALUES (:id, :tid, :sess, :uid, :loc)
            """
        ),
        {"id": str(aid), "tid": str(tenant_id), "sess": str(session_id), "uid": str(user_id), "loc": str(location_id)},
    )
    return aid


def submit_entries(
    sess: Session,
    *,
    tenant_id: UUID,
    session_id: UUID,
    entries: list[EntryInput],
) -> int:
    state = sess.execute(
        text("SELECT state FROM cnt.count_session WHERE id = :id"),
        {"id": str(session_id)},
    ).one_or_none()
    if state is None:
        raise NotFound(f"count session {session_id}")
    if state[0] not in {"open", "submitted"}:
        raise BusinessRuleConflict(f"cannot submit entries to count session in state {state[0]}")
    now = datetime.now(timezone.utc)
    for e in entries:
        if e.counted_qty < 0:
            raise ValidationFailed("counted_qty must be >= 0")
        sess.execute(
            text(
                """
                INSERT INTO cnt.count_entry
                    (id, tenant_id, session_id, sku_id, location_id, counted_qty,
                     counter_user_id, serial_value, counted_at)
                VALUES (:id, :tid, :sess, :sku, :loc, :q, :uid, :sv, :ts)
                """
            ),
            {
                "id": str(uuid4()),
                "tid": str(tenant_id),
                "sess": str(session_id),
                "sku": str(e.sku_id),
                "loc": str(e.location_id),
                "q": e.counted_qty,
                "uid": str(e.counter_user_id),
                "sv": e.serial_value,
                "ts": now,
            },
        )
    sess.execute(
        text("UPDATE cnt.count_session SET state = 'submitted' WHERE id = :id AND state = 'open'"),
        {"id": str(session_id)},
    )
    return len(entries)
