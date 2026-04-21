"""Transactional outbox: emit_event writes to outbox.event in the current tx."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session


def emit_event(
    sess: Session,
    *,
    tenant_id: UUID,
    event_type: str,
    payload: dict[str, Any],
) -> UUID:
    eid = uuid4()
    sess.execute(
        text(
            """
            INSERT INTO outbox.event
                (id, tenant_id, event_type, payload, occurred_at, status, attempts)
            VALUES
                (:id, :tid, :etype, CAST(:payload AS jsonb), :ts, 'pending', 0)
            """
        ),
        {
            "id": str(eid),
            "tid": str(tenant_id),
            "etype": event_type,
            "payload": json.dumps(payload, default=str),
            "ts": datetime.now(timezone.utc),
        },
    )
    return eid
