"""Immutable audit writer.

write_audit inserts into `audit.audit_entry` within the current transaction.
It is the caller's responsibility to call this from inside the same Session
as the business mutation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session


def write_audit(
    sess: Session,
    *,
    tenant_id: UUID,
    actor_user_id: UUID | None,
    target_kind: str,
    target_id: UUID | str,
    action: str,
    before: Any | None = None,
    after: Any | None = None,
) -> UUID:
    eid = uuid4()
    sess.execute(
        text(
            """
            INSERT INTO audit.audit_entry
                (id, tenant_id, actor_user_id, target_kind, target_id, action,
                 before_state, after_state, occurred_at)
            VALUES
                (:id, :tid, :uid, :kind, :tgt, :action,
                 CAST(:before AS jsonb), CAST(:after AS jsonb), :ts)
            """
        ),
        {
            "id": str(eid),
            "tid": str(tenant_id),
            "uid": str(actor_user_id) if actor_user_id else None,
            "kind": target_kind,
            "tgt": str(target_id),
            "action": action,
            "before": json.dumps(before) if before is not None else None,
            "after": json.dumps(after) if after is not None else None,
            "ts": datetime.now(timezone.utc),
        },
    )
    return eid
