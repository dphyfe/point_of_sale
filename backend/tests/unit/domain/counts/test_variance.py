"""Unit tests for count variance computation (FR-023)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from pos_inventory.domain.counts.variance import compute_variance

from ..test_ledger import _Result, _Row


@dataclass
class FakeVarianceSession:
    session_id: UUID = field(default_factory=uuid4)
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc) - timedelta(hours=1))
    snapshots: list[tuple[UUID, UUID, Decimal]] = field(default_factory=list)
    movements: dict[tuple[UUID, UUID], Decimal] = field(default_factory=dict)
    counts: dict[tuple[UUID, UUID], Decimal] = field(default_factory=dict)
    cost_layers: dict[tuple[UUID, UUID], Decimal] = field(default_factory=dict)

    def execute(self, stmt, params=None):  # noqa: ANN001
        sql = " ".join(str(stmt).lower().split())
        params = params or {}
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
        if "from inv.cost_layer" in sql:
            key = (UUID(params["sku"]), UUID(params["loc"]))
            uc = self.cost_layers.get(key)
            return _Result([_Row((uc,))] if uc is not None else [])
        return _Result([])


def test_variance_includes_mid_session_movements():
    """variance_qty = counted - (system_at_open + Δmovements_during_session).

    Open=10, Δ during session=-3 (a sale), counted=8.
    Expected: 8 - (10 + (-3)) = 1 over-count.
    """
    tid, sku, loc = uuid4(), uuid4(), uuid4()
    s = FakeVarianceSession()
    s.snapshots = [(sku, loc, Decimal("10"))]
    s.movements = {(sku, loc): Decimal("-3")}
    s.counts = {(sku, loc): Decimal("8")}
    s.cost_layers = {(sku, loc): Decimal("12.50")}

    rows = compute_variance(s, tenant_id=tid, session_id=s.session_id)  # type: ignore[arg-type]
    assert len(rows) == 1
    r = rows[0]
    assert r.variance_qty == Decimal("1")
    assert r.variance_value == Decimal("12.50")


def test_zero_variance_when_count_matches():
    tid, sku, loc = uuid4(), uuid4(), uuid4()
    s = FakeVarianceSession()
    s.snapshots = [(sku, loc, Decimal("5"))]
    s.movements = {(sku, loc): Decimal("0")}
    s.counts = {(sku, loc): Decimal("5")}
    rows = compute_variance(s, tenant_id=tid, session_id=s.session_id)  # type: ignore[arg-type]
    assert rows[0].variance_qty == Decimal("0")
    assert rows[0].variance_value == Decimal("0")


def test_under_count_yields_negative_variance():
    tid, sku, loc = uuid4(), uuid4(), uuid4()
    s = FakeVarianceSession()
    s.snapshots = [(sku, loc, Decimal("4"))]
    s.movements = {(sku, loc): Decimal("0")}
    s.counts = {(sku, loc): Decimal("3")}
    s.cost_layers = {(sku, loc): Decimal("2")}
    rows = compute_variance(s, tenant_id=tid, session_id=s.session_id)  # type: ignore[arg-type]
    assert rows[0].variance_qty == Decimal("-1")
    assert rows[0].variance_value == Decimal("-2")
