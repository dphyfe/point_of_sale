"""Unit tests for the inventory ledger writer using an in-memory fake session.

The tests verify control-flow shape (FIFO consumption, balance update,
serial state transitions, ledger row payload) without requiring Postgres.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from pos_inventory.core.errors import BusinessRuleConflict, ValidationFailed
from pos_inventory.domain.inventory import ledger as ledger_mod


@dataclass
class _Row:
    cols: tuple

    def __getitem__(self, i: int):
        return self.cols[i]


@dataclass
class _Result:
    rows: list[_Row]

    def one_or_none(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows

    def scalar_one(self):
        return self.rows[0].cols[0]

    def scalar_one_or_none(self):
        return self.rows[0].cols[0] if self.rows else None

    def scalars(self):
        outer = self

        class _S:
            def all(self_inner):
                return [r.cols[0] for r in outer.rows]

            def first(self_inner):
                return outer.rows[0].cols[0] if outer.rows else None

        return _S()


@dataclass
class FakeSession:
    """Minimal stand-in for SQLAlchemy Session.execute."""

    balances: dict[tuple, list[Decimal]] = field(default_factory=dict)
    serials: dict[UUID, list[Any]] = field(default_factory=dict)
    cost_layers: list[dict] = field(default_factory=list)
    inserted_ledger: list[dict] = field(default_factory=list)
    inserted_layers: list[dict] = field(default_factory=list)
    serial_updates: list[dict] = field(default_factory=list)
    balance_updates: list[dict] = field(default_factory=list)
    layer_decrements: list[dict] = field(default_factory=list)

    def execute(self, stmt, params=None):  # noqa: D401, ANN001
        sql = str(stmt).lower()
        params = params or {}
        if "from inv.balance" in sql and "for update" in sql:
            key = (params["tid"], params["sid"], params["lid"])
            vals = self.balances.get(key)
            return _Result([_Row(tuple(vals))] if vals else [])
        if "insert into inv.balance" in sql:
            key = (params["tid"], params["sid"], params["lid"])
            self.balances.setdefault(key, [Decimal("0"), Decimal("0")])
            return _Result([])
        if "from inv.serial" in sql and "for update" in sql:
            sid = UUID(params["id"])
            row = self.serials.get(sid)
            return _Result([_Row(tuple(row))] if row else [])
        if "from inv.cost_layer" in sql and "for update" in sql:
            key = (params["tid"], params["sid"], params["lid"])
            rows = [_Row((cl["id"], cl["qty"], cl["uc"])) for cl in self.cost_layers if cl["key"] == key and Decimal(cl["qty"]) > 0]
            return _Result(rows)
        if "update inv.cost_layer" in sql:
            self.layer_decrements.append(params)
            for cl in self.cost_layers:
                if cl["id"] == params["id"]:
                    cl["qty"] = Decimal(cl["qty"]) - Decimal(params["t"])
            return _Result([])
        if "insert into inv.cost_layer" in sql:
            self.inserted_layers.append(params)
            self.cost_layers.append(
                {
                    "id": params["id"],
                    "key": (params["tid"], params["sid"], params["lid"]),
                    "qty": Decimal(params["qr"]),
                    "uc": Decimal(params["uc"]),
                }
            )
            return _Result([])
        if "update inv.balance" in sql:
            self.balance_updates.append(params)
            key = (params["tid"], params["sid"], params["lid"])
            self.balances[key][0] = Decimal(params["oh"])
            return _Result([])
        if "insert into inv.ledger" in sql:
            self.inserted_ledger.append(params)
            return _Result([])
        if "update inv.serial" in sql:
            self.serial_updates.append(params)
            return _Result([])
        raise AssertionError(f"unexpected sql: {sql[:120]}")


def _ids():
    return uuid4(), uuid4(), uuid4()


def test_inbound_non_serialized_creates_cost_layer_and_balance():
    sess = FakeSession()
    tid, sid, lid = _ids()
    res = ledger_mod.post_movement(
        sess,  # type: ignore[arg-type]
        tenant_id=tid,
        sku_id=sid,
        location_id=lid,
        qty_delta=Decimal("10"),
        unit_cost=Decimal("4.50"),
        source_kind="po_receipt",
        source_doc_id=uuid4(),
    )
    assert res.unit_cost == Decimal("4.50")
    assert len(sess.inserted_layers) == 1
    assert sess.balances[(str(tid), str(sid), str(lid))][0] == Decimal("10")
    assert len(sess.inserted_ledger) == 1
    assert sess.inserted_ledger[0]["sk"] == "po_receipt"


def test_outbound_non_serialized_consumes_fifo_and_computes_unit_cost():
    sess = FakeSession()
    tid, sid, lid = _ids()
    # seed two layers: 4 @ 1.00 then 6 @ 2.00
    ledger_mod.post_movement(
        sess,
        tenant_id=tid,
        sku_id=sid,
        location_id=lid,  # type: ignore[arg-type]
        qty_delta=Decimal("4"),
        unit_cost=Decimal("1.00"),
        source_kind="po_receipt",
        source_doc_id=uuid4(),
    )
    ledger_mod.post_movement(
        sess,
        tenant_id=tid,
        sku_id=sid,
        location_id=lid,  # type: ignore[arg-type]
        qty_delta=Decimal("6"),
        unit_cost=Decimal("2.00"),
        source_kind="po_receipt",
        source_doc_id=uuid4(),
    )
    res = ledger_mod.post_movement(
        sess,
        tenant_id=tid,
        sku_id=sid,
        location_id=lid,  # type: ignore[arg-type]
        qty_delta=Decimal("-7"),  # 4 @ 1.00 + 3 @ 2.00 = 10 / 7
        source_kind="sale",
        source_doc_id=uuid4(),
    )
    assert res.unit_cost == Decimal("1.4286")
    assert sess.balances[(str(tid), str(sid), str(lid))][0] == Decimal("3")


def test_outbound_short_raises_business_rule_conflict():
    sess = FakeSession()
    tid, sid, lid = _ids()
    ledger_mod.post_movement(
        sess,
        tenant_id=tid,
        sku_id=sid,
        location_id=lid,  # type: ignore[arg-type]
        qty_delta=Decimal("2"),
        unit_cost=Decimal("5"),
        source_kind="po_receipt",
        source_doc_id=uuid4(),
    )
    with pytest.raises(BusinessRuleConflict):
        ledger_mod.post_movement(
            sess,
            tenant_id=tid,
            sku_id=sid,
            location_id=lid,  # type: ignore[arg-type]
            qty_delta=Decimal("-5"),
            source_kind="sale",
            source_doc_id=uuid4(),
        )


def test_zero_delta_is_validation_failed():
    sess = FakeSession()
    tid, sid, lid = _ids()
    with pytest.raises(ValidationFailed):
        ledger_mod.post_movement(
            sess,
            tenant_id=tid,
            sku_id=sid,
            location_id=lid,  # type: ignore[arg-type]
            qty_delta=Decimal("0"),
            unit_cost=Decimal("1"),
            source_kind="po_receipt",
            source_doc_id=uuid4(),
        )


def test_inbound_serialized_persists_unit_cost_on_serial():
    sess = FakeSession()
    tid, sid, lid = _ids()
    serial_id = uuid4()
    sess.serials[serial_id] = [Decimal("0"), None, "received"]
    ledger_mod.post_movement(
        sess,
        tenant_id=tid,
        sku_id=sid,
        location_id=lid,  # type: ignore[arg-type]
        qty_delta=Decimal("1"),
        unit_cost=Decimal("199.99"),
        source_kind="po_receipt",
        source_doc_id=uuid4(),
        serial_id=serial_id,
        serial_state_after="sellable",
    )
    assert sess.serial_updates[-1]["uc"] == Decimal("199.99")
    assert sess.serial_updates[-1]["state"] == "sellable"
