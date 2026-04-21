"""Unit tests for serial lifecycle service.

Uses an in-memory FakeSession that stores serial state and emulates
SELECT ... FOR UPDATE locking semantics enough to assert one-winner races.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest

from pos_inventory.core.errors import BusinessRuleConflict, NotFound
from pos_inventory.domain.serials import service as svc


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
    serials: dict[UUID, dict[str, Any]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    locked_ids: set[UUID] = field(default_factory=set)

    def execute(self, stmt, params=None):  # noqa: ANN001
        sql = " ".join(str(stmt).lower().split())
        params = params or {}
        if "select state, current_location_id from inv.serial" in sql:
            sid = UUID(params["id"])
            with self.lock:
                if sid in self.locked_ids:
                    return _Result([])
                self.locked_ids.add(sid)
            row = self.serials.get(sid)
            return _Result([_Row((row["state"], row["loc"]))] if row else [])
        if "update inv.serial set state = :s, current_location_id = null" in sql:
            sid = UUID(params["id"])
            self.serials[sid]["state"] = params["s"]
            self.serials[sid]["loc"] = None
            self.locked_ids.discard(sid)
            return _Result([])
        if "update inv.serial set state = :s, current_location_id = :lid" in sql:
            sid = UUID(params["id"])
            self.serials[sid]["state"] = params["s"]
            self.serials[sid]["loc"] = UUID(params["lid"])
            self.locked_ids.discard(sid)
            return _Result([])
        if "update inv.serial set state = :s where id" in sql:
            sid = UUID(params["id"])
            self.serials[sid]["state"] = params["s"]
            self.locked_ids.discard(sid)
            return _Result([])
        raise AssertionError(f"unexpected sql: {sql[:120]}")


def _seed(state: str = "sellable", loc: UUID | None = None) -> tuple[FakeSession, UUID]:
    sid = uuid4()
    s = FakeSession()
    s.serials[sid] = {"state": state, "loc": loc or uuid4()}
    return s, sid


def test_received_to_sellable():
    s, sid = _seed("received")
    assert svc.transition(s, sid, "sellable") == "sellable"
    assert s.serials[sid]["state"] == "sellable"


def test_sell_clears_location_and_advances_state():
    s, sid = _seed("sellable")
    assert svc.sell(s, sid) == "sold"
    assert s.serials[sid]["state"] == "sold"
    assert s.serials[sid]["loc"] is None


def test_double_sell_blocked():
    s, sid = _seed("sellable")
    svc.sell(s, sid)
    with pytest.raises(BusinessRuleConflict):
        svc.sell(s, sid)


def test_unknown_serial_raises_not_found():
    s = FakeSession()
    with pytest.raises(NotFound):
        svc.sell(s, uuid4())


def test_returned_then_rma_pending_then_closed():
    s, sid = _seed("sold")
    loc = uuid4()
    svc.return_(s, sid, target_location_id=loc)
    assert s.serials[sid]["state"] == "returned"
    assert s.serials[sid]["loc"] == loc
    svc.mark_rma_pending(s, sid)
    svc.mark_rma_closed(s, sid)
    assert s.serials[sid]["state"] == "rma_closed"
    assert s.serials[sid]["loc"] is None


def test_return_requires_sold_state():
    s, sid = _seed("sellable")
    with pytest.raises(BusinessRuleConflict):
        svc.return_(s, sid, target_location_id=uuid4())


def test_no_double_sell_race_one_winner():
    """Two threads concurrently call sell on the same serial; exactly one wins."""
    s, sid = _seed("sellable")
    results: list[Exception | str] = []

    def attempt():
        try:
            results.append(svc.sell(s, sid))
        except Exception as e:  # noqa: BLE001
            results.append(e)

    t1 = threading.Thread(target=attempt)
    t2 = threading.Thread(target=attempt)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    successes = [r for r in results if r == "sold"]
    failures = [r for r in results if isinstance(r, Exception)]
    assert len(successes) == 1
    assert len(failures) == 1


def test_illegal_transitions_blocked():
    s, sid = _seed("rma_closed")
    with pytest.raises(BusinessRuleConflict):
        svc.transition(s, sid, "sellable")
    s2, sid2 = _seed("scrapped")
    with pytest.raises(BusinessRuleConflict):
        svc.transition(s2, sid2, "sellable")


def test_scrap_from_sellable():
    s, sid = _seed("sellable")
    svc.mark_scrapped(s, sid)
    assert s.serials[sid]["state"] == "scrapped"
