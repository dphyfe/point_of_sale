"""Unit tests for count approval (FR-024, SC-004)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from pos_inventory.core.errors import BusinessRuleConflict
from pos_inventory.domain.counts.approve import approve_session

from ..test_ledger import FakeSession as LedgerFakeSession, _Result, _Row


@dataclass
class FakeApproveSession(LedgerFakeSession):
    session_state: str = "submitted"
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc) - timedelta(hours=1))
    snapshots: list[tuple[UUID, UUID, Decimal]] = field(default_factory=list)
    movements: dict[tuple[UUID, UUID], Decimal] = field(default_factory=dict)
    counts: dict[tuple[UUID, UUID], Decimal] = field(default_factory=dict)
    cost_layers_view: dict[tuple[UUID, UUID], Decimal] = field(default_factory=dict)
    inserted_adjustments: list[dict] = field(default_factory=list)
    state_updates: list[dict] = field(default_factory=list)
    audits: list[dict] = field(default_factory=list)

    def execute(self, stmt, params=None):  # noqa: ANN001
        sql = " ".join(str(stmt).lower().split())
        params = params or {}
        if "select state from cnt.count_session" in sql:
            return _Result([_Row((self.session_state,))])
        if "select created_at, closed_at from cnt.count_session" in sql:
            return _Result([_Row((self.opened_at, None))])
        if "from cnt.count_session_snapshot" in sql:
            return _Result([_Row(t) for t in self.snapshots])
        if "from inv.ledger" in sql and "sum(qty_delta)" in sql:
            key = (UUID(params["sku"]), UUID(params["loc"]))
            return _Result([_Row((self.movements.get(key, Decimal("0")),))])
        if "from cnt.count_entry" in sql and "sum(counted_qty)" in sql:
            key = (UUID(params["sku"]), UUID(params["loc"]))
            return _Result([_Row((self.counts.get(key, Decimal("0")),))])
        if "from inv.cost_layer" in sql and "remaining_qty > 0" in sql:
            key = (UUID(params["sku"]), UUID(params["loc"]))
            uc = self.cost_layers_view.get(key)
            return _Result([_Row((uc,))] if uc is not None else [])
        if "insert into inv.adjustment" in sql:
            self.inserted_adjustments.append(params)
            return _Result([])
        if sql.startswith("update cnt.count_session"):
            self.state_updates.append(params)
            self.session_state = "approved"
            return _Result([])
        if "insert into audit.audit_entry" in sql:
            self.audits.append(params)
            return _Result([])
        return super().execute(stmt, params)


def test_approve_creates_one_adjustment_per_nonzero_variance():
    tid, uid = uuid4(), uuid4()
    sku1, loc1 = uuid4(), uuid4()
    sku2, loc2 = uuid4(), uuid4()
    sku3, loc3 = uuid4(), uuid4()
    s = FakeApproveSession()
    s.snapshots = [
        (sku1, loc1, Decimal("10")),
        (sku2, loc2, Decimal("5")),
        (sku3, loc3, Decimal("7")),  # zero variance
    ]
    s.counts = {(sku1, loc1): Decimal("8"), (sku2, loc2): Decimal("6"), (sku3, loc3): Decimal("7")}
    s.cost_layers_view = {(sku1, loc1): Decimal("1"), (sku2, loc2): Decimal("1")}
    # Seed balances so post_movement (LedgerFakeSession) can write outbound for sku1.
    s.balances[(str(tid), str(sku1), str(loc1))] = [Decimal("10"), Decimal("0")]
    s.balances[(str(tid), str(sku2), str(loc2))] = [Decimal("5"), Decimal("0")]
    # LedgerFakeSession.cost_layers is list[dict]; seed an outbound layer for sku1.
    s.cost_layers.append(
        {
            "id": uuid4(),
            "key": (str(tid), str(sku1), str(loc1)),
            "qty": Decimal("10"),
            "uc": Decimal("1"),
        }
    )

    n = approve_session(s, tenant_id=tid, session_id=uuid4(), actor_user_id=uid)  # type: ignore[arg-type]
    assert n == 2
    assert len(s.inserted_adjustments) == 2
    assert s.session_state == "approved"
    assert len(s.audits) == 1


def test_approve_rejects_already_approved_session():
    s = FakeApproveSession()
    s.session_state = "approved"
    with pytest.raises(BusinessRuleConflict):
        approve_session(s, tenant_id=uuid4(), session_id=uuid4(), actor_user_id=uuid4())  # type: ignore[arg-type]
