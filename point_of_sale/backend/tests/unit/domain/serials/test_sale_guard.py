"""Per-location selling restriction (FR-030)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from pos_inventory.core.errors import BusinessRuleConflict, NotFound
from pos_inventory.domain.inventory import sale_guard as inv_guard
from pos_inventory.domain.serials import sale_guard as ser_guard


@dataclass
class _Row:
    _t: tuple

    def __getitem__(self, i):
        return self._t[i]

    def __iter__(self):
        return iter(self._t)


@dataclass
class _Result:
    rows: list

    def one_or_none(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


@dataclass
class FakeGuardSession:
    serials: dict[tuple[UUID, str], tuple[UUID, UUID, str, UUID, bool]] = field(default_factory=dict)
    balances: dict[tuple[UUID, UUID, UUID], tuple[Decimal, bool]] = field(default_factory=dict)

    def execute(self, stmt, params=None):  # noqa: ANN001
        sql = " ".join(str(stmt).lower().split())
        params = params or {}
        if "from inv.serial s" in sql and "left join inv.location l" in sql:
            key = (UUID(params["tid"]), params["sv"])
            v = self.serials.get(key)
            return _Result([_Row(v)] if v else [])
        if "from inv.balance b" in sql and "join inv.location l" in sql:
            key = (UUID(params["tid"]), UUID(params["sid"]), UUID(params["lid"]))
            v = self.balances.get(key)
            return _Result([_Row(v)] if v else [])
        return _Result([])


def test_serial_sale_blocked_when_register_restricted_and_serial_elsewhere():
    tid, sku, register_loc, home_loc, serial = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    s = FakeGuardSession()
    # Serial is at home_loc; cashier tries to sell at register_loc which has restrict=true.
    s.serials[(tid, "SN-A")] = (serial, sku, "sellable", home_loc, True)
    with pytest.raises(BusinessRuleConflict):
        ser_guard.validate_sale(s, tenant_id=tid, serial_value="SN-A", sku_id=sku, location_id=register_loc)  # type: ignore[arg-type]


def test_serial_sale_allowed_when_at_register_location():
    tid, sku, loc, serial = uuid4(), uuid4(), uuid4(), uuid4()
    s = FakeGuardSession()
    s.serials[(tid, "SN-B")] = (serial, sku, "sellable", loc, True)
    sid = ser_guard.validate_sale(s, tenant_id=tid, serial_value="SN-B", sku_id=sku, location_id=loc)  # type: ignore[arg-type]
    assert sid == serial


def test_serial_unknown_raises_not_found():
    s = FakeGuardSession()
    with pytest.raises(NotFound):
        ser_guard.validate_sale(s, tenant_id=uuid4(), serial_value="missing", sku_id=uuid4(), location_id=uuid4())  # type: ignore[arg-type]


def test_serial_wrong_state_blocked():
    tid, sku, loc, serial = uuid4(), uuid4(), uuid4(), uuid4()
    s = FakeGuardSession()
    s.serials[(tid, "SN-C")] = (serial, sku, "sold", loc, False)
    with pytest.raises(BusinessRuleConflict):
        ser_guard.validate_sale(s, tenant_id=tid, serial_value="SN-C", sku_id=sku, location_id=loc)  # type: ignore[arg-type]


def test_nonserialized_sale_blocked_when_no_stock_at_restricted_location():
    tid, sku, loc = uuid4(), uuid4(), uuid4()
    s = FakeGuardSession()
    s.balances[(tid, sku, loc)] = (Decimal("0"), True)
    with pytest.raises(BusinessRuleConflict):
        inv_guard.assert_can_sell(s, tenant_id=tid, sku_id=sku, location_id=loc, qty=Decimal("1"))  # type: ignore[arg-type]


def test_nonserialized_sale_allowed_when_sufficient_stock():
    tid, sku, loc = uuid4(), uuid4(), uuid4()
    s = FakeGuardSession()
    s.balances[(tid, sku, loc)] = (Decimal("5"), True)
    inv_guard.assert_can_sell(s, tenant_id=tid, sku_id=sku, location_id=loc, qty=Decimal("3"))  # type: ignore[arg-type]
