"""Count approval: post one inv.adjustment + ledger row per non-zero variance."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.audit import write_audit
from pos_inventory.core.errors import BusinessRuleConflict, NotFound
from pos_inventory.domain.counts.variance import compute_variance
from pos_inventory.domain.inventory.ledger import post_movement


def approve_session(
    sess: Session,
    *,
    tenant_id: UUID,
    session_id: UUID,
    actor_user_id: UUID,
    reason: str = "physical_count",
) -> int:
    state_row = sess.execute(
        text("SELECT state FROM cnt.count_session WHERE id = :id"),
        {"id": str(session_id)},
    ).one_or_none()
    if state_row is None:
        raise NotFound(f"count session {session_id}")
    if state_row[0] not in {"submitted", "open"}:
        raise BusinessRuleConflict(f"cannot approve count session in state {state_row[0]}")

    now = datetime.now(timezone.utc)
    rows = compute_variance(sess, tenant_id=tenant_id, session_id=session_id)
    n_adj = 0
    for r in rows:
        if r.variance_qty == 0:
            continue
        adj_id = uuid4()
        sess.execute(
            text(
                """
                INSERT INTO inv.adjustment
                    (id, tenant_id, sku_id, location_id, qty_delta, reason,
                     counter_user_id, occurred_at, source_kind, source_doc_id)
                VALUES (:id, :tid, :sku, :loc, :qd, :rsn, :uid, :ts, 'count_adjustment', :sess)
                """
            ),
            {
                "id": str(adj_id),
                "tid": str(tenant_id),
                "sku": str(r.sku_id),
                "loc": str(r.location_id),
                "qd": r.variance_qty,
                "rsn": reason,
                "uid": str(actor_user_id),
                "ts": now,
                "sess": str(session_id),
            },
        )
        post_movement(
            sess,
            tenant_id=tenant_id,
            sku_id=r.sku_id,
            location_id=r.location_id,
            qty_delta=Decimal(r.variance_qty),
            unit_cost=Decimal("0"),
            source_kind="count_adjustment",
            source_doc_id=adj_id,
            actor_user_id=actor_user_id,
            occurred_at=now,
        )
        n_adj += 1

    sess.execute(
        text("UPDATE cnt.count_session SET state = 'approved', closed_at = :ts WHERE id = :id"),
        {"ts": now, "id": str(session_id)},
    )
    write_audit(
        sess,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        target_kind="count_session",
        target_id=session_id,
        action="approved",
        after={"adjustments": n_adj},
    )
    return n_adj
