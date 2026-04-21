"""Unit tests for audit and outbox writers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from pos_inventory.core.audit import write_audit
from pos_inventory.core.events import emit_event


@dataclass
class FakeSession:
    sql_log: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def execute(self, stmt, params=None):  # noqa: ANN001
        self.sql_log.append((str(stmt), params or {}))


def test_write_audit_inserts_into_audit_audit_entry():
    s = FakeSession()
    tid, uid = uuid4(), uuid4()
    eid = write_audit(
        s,  # type: ignore[arg-type]
        tenant_id=tid,
        actor_user_id=uid,
        target_kind="purchase_order",
        target_id=uuid4(),
        action="approved",
        before={"state": "submitted"},
        after={"state": "approved"},
    )
    assert eid is not None
    sql, params = s.sql_log[-1]
    assert "audit.audit_entry" in sql
    assert params["kind"] == "purchase_order"
    assert params["action"] == "approved"
    assert params["tid"] == str(tid)


def test_emit_event_inserts_into_outbox_event():
    s = FakeSession()
    tid = uuid4()
    eid = emit_event(s, tenant_id=tid, event_type="receipt.posted", payload={"qty": 5})  # type: ignore[arg-type]
    assert eid is not None
    sql, params = s.sql_log[-1]
    assert "outbox.event" in sql
    assert params["etype"] == "receipt.posted"
    assert "qty" in params["payload"]
