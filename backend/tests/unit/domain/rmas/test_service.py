"""Unit tests for vendor RMA service: open → shipped → closed."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from pos_inventory.core.errors import BusinessRuleConflict
from pos_inventory.domain.rmas import service as rsvc

from ..test_ledger import FakeSession as LedgerFakeSession, _Result, _Row


@dataclass
class FakeRmaSession(LedgerFakeSession):
    rma_state: str = "open"
    holding_loc: UUID | None = None
    rma_lines: list[tuple] = field(default_factory=list)  # (line_id, sku_id, qty, serial_id, unit_cost)
    serial_unit_cost: dict[UUID, Decimal] = field(default_factory=dict)
    serial_state: dict[UUID, str] = field(default_factory=dict)
    inserted_rmas: list[dict] = field(default_factory=list)
    inserted_rma_lines: list[dict] = field(default_factory=list)
    state_updates: list[dict] = field(default_factory=list)

    def execute(self, stmt, params=None):  # noqa: ANN001
        sql = " ".join(str(stmt).lower().split())
        params = params or {}

        if "select state, holding_location_id from rma.vendor_rma" in sql:
            return _Result([_Row((self.rma_state, self.holding_loc))])
        if sql.startswith("select id, sku_id, qty, serial_id, unit_cost from rma.vendor_rma_line"):
            return _Result([_Row(t) for t in self.rma_lines])
        if "select unit_cost from inv.serial" in sql:
            sid = UUID(params["id"])
            uc = self.serial_unit_cost.get(sid)
            return _Result([_Row((uc,))] if uc is not None else [])
        if "select state, current_location_id from inv.serial" in sql:
            sid = UUID(params["id"])
            return _Result([_Row((self.serial_state.get(sid), None))])
        if "update inv.serial set state" in sql:
            self.serial_state[UUID(params["id"])] = params["s"]
            return _Result([])
        if "insert into rma.vendor_rma " in sql or sql.startswith("insert into rma.vendor_rma("):
            self.inserted_rmas.append(params)
            return _Result([])
        if "insert into rma.vendor_rma_line" in sql:
            self.inserted_rma_lines.append(params)
            return _Result([])
        if "update rma.vendor_rma" in sql:
            self.state_updates.append(params)
            if "state = 'shipped'" in sql:
                self.rma_state = "shipped"
            if "state = 'closed'" in sql:
                self.rma_state = "closed"
            return _Result([])
        if "insert into audit.audit_entry" in sql or "insert into outbox.event" in sql:
            return _Result([])
        return super().execute(stmt, params)


def test_create_rma_inserts_header_and_lines():
    tid, uid, vid, hold, sku = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    s = FakeRmaSession()
    rid = rsvc.create_rma(
        s,  # type: ignore[arg-type]
        tenant_id=tid,
        actor_user_id=uid,
        input=rsvc.RmaInput(
            vendor_id=vid,
            holding_location_id=hold,
            originating_po_id=None,
            lines=[rsvc.RmaLineInput(sku_id=sku, qty=Decimal("2"), unit_cost=Decimal("50"))],
        ),
    )
    assert rid is not None
    assert len(s.inserted_rmas) == 1
    assert len(s.inserted_rma_lines) == 1


def test_ship_requires_open_state():
    s = FakeRmaSession()
    s.rma_state = "shipped"
    with pytest.raises(BusinessRuleConflict):
        rsvc.ship_rma(s, tenant_id=uuid4(), actor_user_id=uuid4(), rma_id=uuid4())  # type: ignore[arg-type]


def test_ship_then_close_advances_serials_and_credits_via_serial_cost():
    tid, uid, hold, sku, ser = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    s = FakeRmaSession()
    s.holding_loc = hold
    s.rma_lines = [(uuid4(), sku, Decimal("1"), ser, Decimal("0"))]
    s.serial_unit_cost[ser] = Decimal("199.99")
    s.serial_state[ser] = "rma_pending"
    # Seed cost layer for non-serialized branch isn't needed (serial path).
    # Mark the serial in the ledger fake's serials map for post_movement.
    s.serials[ser] = [Decimal("199.99"), hold, "rma_pending"]
    # Seed balance so outbound from holding loc succeeds (qty=1 outbound).
    s.balances[(str(tid), str(sku), str(hold))] = [Decimal("1"), Decimal("0")]

    rsvc.ship_rma(s, tenant_id=tid, actor_user_id=uid, rma_id=uuid4())  # type: ignore[arg-type]
    assert s.rma_state == "shipped"

    credit = rsvc.close_rma(s, tenant_id=tid, actor_user_id=uid, rma_id=uuid4())  # type: ignore[arg-type]
    assert credit == Decimal("199.99")
    assert s.serial_state[ser] == "rma_closed"
    assert s.rma_state == "closed"


def test_close_requires_shipped_state():
    s = FakeRmaSession()
    s.rma_state = "open"
    with pytest.raises(BusinessRuleConflict):
        rsvc.close_rma(s, tenant_id=uuid4(), actor_user_id=uuid4(), rma_id=uuid4())  # type: ignore[arg-type]
