"""Consent service (T075) — record events and read consent matrix + history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ConsentEventInput:
    customer_id: UUID
    channel: str  # email|sms
    purpose: str  # transactional|marketing
    event_kind: str  # opt_in|opt_out|withdraw|unsubscribe
    source: str  # pos|web|provider|admin
    actor_user_id: UUID | None = None
    note: str | None = None


_KIND_TO_STATE = {
    "opt_in": "opted_in",
    "opt_out": "opted_out",
    "withdraw": "opted_out",
    "unsubscribe": "opted_out",
}


def record_event(sess: Session, *, tenant_id: UUID, ev: ConsentEventInput) -> UUID:
    new_state = _KIND_TO_STATE.get(ev.event_kind)
    if new_state is None:
        raise ValueError(f"unknown event_kind {ev.event_kind}")
    eid = uuid4()
    now = datetime.now(timezone.utc)
    sess.execute(
        text(
            """
            INSERT INTO consent.event
                (id, tenant_id, customer_id, channel, purpose, event_kind, source,
                 actor_user_id, occurred_at, note)
            VALUES (:id, :tid, :cid, :ch, :pu, :ek, :src, :actor, :ts, :note)
            """
        ),
        {
            "id": str(eid), "tid": str(tenant_id), "cid": str(ev.customer_id),
            "ch": ev.channel, "pu": ev.purpose, "ek": ev.event_kind, "src": ev.source,
            "actor": str(ev.actor_user_id) if ev.actor_user_id else None,
            "ts": now, "note": ev.note,
        },
    )
    sess.execute(
        text(
            """
            INSERT INTO consent.state
                (tenant_id, customer_id, channel, purpose, state, updated_at, last_event_id)
            VALUES (:tid, :cid, :ch, :pu, :st, :ts, :eid)
            ON CONFLICT (tenant_id, customer_id, channel, purpose)
            DO UPDATE SET state=EXCLUDED.state, updated_at=EXCLUDED.updated_at,
                          last_event_id=EXCLUDED.last_event_id
            """
        ),
        {
            "tid": str(tenant_id), "cid": str(ev.customer_id), "ch": ev.channel,
            "pu": ev.purpose, "st": new_state, "ts": now, "eid": str(eid),
        },
    )
    return eid


def get_matrix(sess: Session, *, tenant_id: UUID, customer_id: UUID) -> list[dict]:
    rows = sess.execute(
        text(
            """
            SELECT channel, purpose, state, updated_at
              FROM consent.state
             WHERE tenant_id=:tid AND customer_id=:cid
             ORDER BY channel, purpose
            """
        ),
        {"tid": str(tenant_id), "cid": str(customer_id)},
    ).all()
    return [
        {"channel": r[0], "purpose": r[1], "state": r[2], "updated_at": r[3]}
        for r in rows
    ]


def get_history(sess: Session, *, tenant_id: UUID, customer_id: UUID, limit: int = 100) -> list[dict]:
    rows = sess.execute(
        text(
            """
            SELECT id, channel, purpose, event_kind, source, actor_user_id, occurred_at, note
              FROM consent.event
             WHERE tenant_id=:tid AND customer_id=:cid
             ORDER BY occurred_at DESC
             LIMIT :lim
            """
        ),
        {"tid": str(tenant_id), "cid": str(customer_id), "lim": limit},
    ).all()
    return [
        {
            "id": r[0], "channel": r[1], "purpose": r[2], "event_kind": r[3],
            "source": r[4], "actor_user_id": r[5], "occurred_at": r[6], "note": r[7],
        }
        for r in rows
    ]
