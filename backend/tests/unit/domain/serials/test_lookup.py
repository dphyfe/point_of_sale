"""Unit tests for serial lookup history reconstruction."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from pos_inventory.core.errors import NotFound
from pos_inventory.domain.serials.lookup import get_serial_with_history


@dataclass
class _Row:
    cols: tuple

    def __getitem__(self, i: int):
        return self.cols[i]


@dataclass
class _Result:
    rows: list

    def one_or_none(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


@dataclass
class FakeSession:
    serial_row: tuple | None = None
    history_rows: list[tuple] = field(default_factory=list)

    def execute(self, stmt, params=None):  # noqa: ANN001
        sql = " ".join(str(stmt).lower().split())
        if "from inv.serial" in sql and "serial_value = :sv" in sql:
            return _Result([_Row(self.serial_row)] if self.serial_row else [])
        if "from inv.ledger" in sql and "serial_id = :sid" in sql:
            return _Result([_Row(r) for r in self.history_rows])
        raise AssertionError(sql)


def test_returns_full_history_in_order():
    sid = uuid4()
    sku = uuid4()
    loc = uuid4()
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    s = FakeSession(
        serial_row=(sid, sku, "SN-1", "rma_closed", None, Decimal("100"), t0),
        history_rows=[
            (t0, "po_receipt", uuid4(), loc, Decimal("1"), Decimal("100")),
            (t0 + timedelta(days=1), "sale", uuid4(), loc, Decimal("-1"), Decimal("100")),
            (t0 + timedelta(days=2), "return", uuid4(), loc, Decimal("1"), Decimal("100")),
            (t0 + timedelta(days=3), "rma_ship", uuid4(), loc, Decimal("-1"), Decimal("100")),
        ],
    )
    serial, history = get_serial_with_history(s, tenant_id=uuid4(), serial_value="SN-1")
    assert serial.state == "rma_closed"
    assert [h.source_kind for h in history] == [
        "po_receipt",
        "sale",
        "return",
        "rma_ship",
    ]


def test_unknown_serial_raises():
    s = FakeSession(serial_row=None)
    with pytest.raises(NotFound):
        get_serial_with_history(s, tenant_id=uuid4(), serial_value="missing")
