"""Unit tests for the receiving service.

Uses a fake SQLAlchemy Session that records SQL execute() calls and serves
canned rows for the lookups receiving needs (PO state, PO line metadata,
serial uniqueness, and lot upsert). Inventory mutations are routed through
the real `post_movement` writer using the same FakeSession from the ledger
test file (so FIFO + balance bookkeeping is exercised end-to-end).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from pos_inventory.core.errors import BusinessRuleConflict, ValidationFailed
from pos_inventory.domain.purchase_orders import receiving as rcv

from ..test_ledger import FakeSession as LedgerFakeSession, _Result, _Row


@dataclass
class FakeReceiveSession(LedgerFakeSession):
    """Extends the ledger FakeSession with PO/receipt query stubs."""

    po_state: str = "approved"
    # po_line_id -> tuple(sku_id, tracking, sku_code, ordered, received, unit_cost, sku_tol)
    po_lines: dict[UUID, tuple] = field(default_factory=dict)
    existing_serials: set[str] = field(default_factory=set)
    existing_lots: dict[tuple[UUID, str], UUID] = field(default_factory=dict)
    # written
    inserted_lots: list[dict] = field(default_factory=list)
    inserted_receipts: list[dict] = field(default_factory=list)
    inserted_receipt_lines: list[dict] = field(default_factory=list)
    inserted_receipt_serials: list[dict] = field(default_factory=list)
    inserted_serials: list[dict] = field(default_factory=list)
    po_state_updates: list[str] = field(default_factory=list)
    po_line_updates: list[dict] = field(default_factory=list)

    def execute(self, stmt, params=None):  # noqa: ANN001
        sql = " ".join(str(stmt).lower().split())
        params = params or {}

        if "from po.purchase_order" in sql and "for update" in sql and "select state" in sql:
            return _Result([_Row((self.po_state,))])

        if "select pol.sku_id, sku.tracking" in sql:
            row = self.po_lines[UUID(params["id"])]
            return _Result([_Row(row)])

        if "from inv.serial" in sql and "serial_value = any" in sql:
            hits = [_Row((v,)) for v in params["vals"] if v in self.existing_serials]
            return _Result(hits)

        if "from inv.lot" in sql and "lot_code" in sql and "select id" in sql:
            key = (UUID(params["sid"]), params["lc"])
            lid = self.existing_lots.get(key)
            return _Result([_Row((lid,))] if lid else [])
        if "insert into inv.lot" in sql:
            self.inserted_lots.append(params)
            self.existing_lots[(UUID(params["sid"]), params["lc"])] = UUID(params["id"])
            return _Result([])

        if "update po.purchase_order" in sql and "state = 'receiving'" in sql:
            self.po_state = "receiving"
            self.po_state_updates.append("receiving")
            return _Result([])
        if "update po.purchase_order" in sql and "state = 'closed'" in sql:
            self.po_state = "closed"
            self.po_state_updates.append("closed")
            return _Result([])

        if "insert into po.receipt " in sql or "insert into po.receipt(" in sql or sql.startswith("insert into po.receipt "):
            self.inserted_receipts.append(params)
            return _Result([])
        if "insert into po.receipt_line" in sql:
            self.inserted_receipt_lines.append(params)
            return _Result([])
        if "insert into po.receipt_serial" in sql:
            self.inserted_receipt_serials.append(params)
            return _Result([])
        if "insert into inv.serial" in sql:
            self.inserted_serials.append(params)
            # Seed the LedgerFakeSession's `serials` map so the subsequent
            # post_movement() call (which does SELECT ... FOR UPDATE) finds it.
            self.serials[UUID(params["id"])] = [
                Decimal(params["uc"]),
                UUID(params["lid"]) if params["lid"] else None,
                "received",
            ]
            return _Result([])
        if "update po.purchase_order_line" in sql:
            self.po_line_updates.append(params)
            return _Result([])
        if "select count(*) from po.purchase_order_line" in sql:
            outstanding = sum(1 for k, v in self.po_lines.items() if Decimal(v[3]) > self._line_received_total(k))

            class _Scalar:
                def __init__(self, v):
                    self.v = v

                def scalar_one(self):
                    return self.v

            return _Scalar(outstanding)
        if "insert into audit.audit_entry" in sql or "insert into outbox.event" in sql:
            return _Result([])

        # Fall through to ledger-level handlers.
        return super().execute(stmt, params)

    def _line_received_total(self, po_line_id: UUID) -> Decimal:
        total = Decimal("0")
        for u in self.po_line_updates:
            if u["id"] == str(po_line_id):
                total = Decimal(u["rq"])  # last-write-wins
        return total


def _make_session(po_lines: dict[UUID, tuple]) -> FakeReceiveSession:
    s = FakeReceiveSession()
    s.po_lines = po_lines
    return s


def test_non_serialized_partial_receive_updates_balance_and_backorder():
    tid, uid, plid, pid, loc, sku = uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    sess = _make_session({plid: (sku, "non_serialized", "WIDGET", Decimal("10"), Decimal("0"), Decimal("3.00"), None)})

    receipt_id, lines = rcv.post_receipt(
        sess,  # type: ignore[arg-type]
        tenant_id=tid,
        actor_user_id=uid,
        po_id=pid,
        location_id=loc,
        lines=[rcv.ReceiptLineInput(po_line_id=plid, received_qty=Decimal("4"))],
    )
    assert lines[0].received_qty == Decimal("4")
    assert lines[0].backordered_qty == Decimal("6")
    assert sess.balances[(str(tid), str(sku), str(loc))][0] == Decimal("4")
    assert sess.po_state == "receiving"  # state advanced


def test_full_non_serialized_receive_closes_po():
    tid, uid, plid, pid, loc, sku = uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    sess = _make_session({plid: (sku, "non_serialized", "WIDGET", Decimal("5"), Decimal("0"), Decimal("2.00"), None)})

    rcv.post_receipt(
        sess,  # type: ignore[arg-type]
        tenant_id=tid,
        actor_user_id=uid,
        po_id=pid,
        location_id=loc,
        lines=[rcv.ReceiptLineInput(po_line_id=plid, received_qty=Decimal("5"))],
    )
    assert sess.po_state == "closed"


def test_over_receive_within_tolerance_records_overage():
    tid, uid, plid, pid, loc, sku = uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    # SKU-level tolerance 20%, ordered 10 → max 12
    sess = _make_session({plid: (sku, "non_serialized", "WIDGET", Decimal("10"), Decimal("0"), Decimal("1.00"), 20)})
    _, lines = rcv.post_receipt(
        sess,  # type: ignore[arg-type]
        tenant_id=tid,
        actor_user_id=uid,
        po_id=pid,
        location_id=loc,
        lines=[rcv.ReceiptLineInput(po_line_id=plid, received_qty=Decimal("12"))],
    )
    assert lines[0].overage_qty == Decimal("2")


def test_over_receive_beyond_tolerance_blocks():
    tid, uid, plid, pid, loc, sku = uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    sess = _make_session({plid: (sku, "non_serialized", "WIDGET", Decimal("10"), Decimal("0"), Decimal("1.00"), 5)})
    with pytest.raises(BusinessRuleConflict):
        rcv.post_receipt(
            sess,  # type: ignore[arg-type]
            tenant_id=tid,
            actor_user_id=uid,
            po_id=pid,
            location_id=loc,
            lines=[rcv.ReceiptLineInput(po_line_id=plid, received_qty=Decimal("12"))],
        )


def test_po_must_be_approved_or_later():
    tid, uid, plid, pid, loc, sku = uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    sess = _make_session({plid: (sku, "non_serialized", "W", Decimal("1"), Decimal("0"), Decimal("1"), None)})
    sess.po_state = "draft"
    with pytest.raises(BusinessRuleConflict):
        rcv.post_receipt(
            sess,  # type: ignore[arg-type]
            tenant_id=tid,
            actor_user_id=uid,
            po_id=pid,
            location_id=loc,
            lines=[rcv.ReceiptLineInput(po_line_id=plid, received_qty=Decimal("1"))],
        )


def test_serialized_requires_n_serials_matching_qty():
    tid, uid, plid, pid, loc, sku = uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    sess = _make_session({plid: (sku, "serialized", "PHONE", Decimal("3"), Decimal("0"), Decimal("100"), None)})
    with pytest.raises(ValidationFailed):
        rcv.post_receipt(
            sess,  # type: ignore[arg-type]
            tenant_id=tid,
            actor_user_id=uid,
            po_id=pid,
            location_id=loc,
            lines=[rcv.ReceiptLineInput(po_line_id=plid, received_qty=Decimal("3"), serial_values=["A", "B"])],
        )


def test_serialized_blocks_known_serial():
    tid, uid, plid, pid, loc, sku = uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    sess = _make_session({plid: (sku, "serialized", "PHONE", Decimal("2"), Decimal("0"), Decimal("100"), None)})
    sess.existing_serials.add("A")
    with pytest.raises(BusinessRuleConflict):
        rcv.post_receipt(
            sess,  # type: ignore[arg-type]
            tenant_id=tid,
            actor_user_id=uid,
            po_id=pid,
            location_id=loc,
            lines=[rcv.ReceiptLineInput(po_line_id=plid, received_qty=Decimal("2"), serial_values=["A", "B"])],
        )


def test_serialized_happy_path_creates_serials_and_ledger_rows():
    tid, uid, plid, pid, loc, sku = uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    sess = _make_session({plid: (sku, "serialized", "PHONE", Decimal("2"), Decimal("0"), Decimal("100"), None)})
    rid, lines = rcv.post_receipt(
        sess,  # type: ignore[arg-type]
        tenant_id=tid,
        actor_user_id=uid,
        po_id=pid,
        location_id=loc,
        lines=[rcv.ReceiptLineInput(po_line_id=plid, received_qty=Decimal("2"), serial_values=["S1", "S2"])],
    )
    assert len(sess.inserted_serials) == 2
    assert {p["sv"] for p in sess.inserted_serials} == {"S1", "S2"}
    assert len(sess.inserted_ledger) == 2
    assert sess.balances[(str(tid), str(sku), str(loc))][0] == Decimal("2")


def test_lot_tracked_requires_lot_code_and_creates_lot():
    tid, uid, plid, pid, loc, sku = uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    sess = _make_session({plid: (sku, "lot_tracked", "MED", Decimal("100"), Decimal("0"), Decimal("0.50"), None)})
    with pytest.raises(ValidationFailed):
        rcv.post_receipt(
            sess,  # type: ignore[arg-type]
            tenant_id=tid,
            actor_user_id=uid,
            po_id=pid,
            location_id=loc,
            lines=[rcv.ReceiptLineInput(po_line_id=plid, received_qty=Decimal("100"))],
        )

    sess2 = _make_session({plid: (sku, "lot_tracked", "MED", Decimal("100"), Decimal("0"), Decimal("0.50"), None)})
    rcv.post_receipt(
        sess2,  # type: ignore[arg-type]
        tenant_id=tid,
        actor_user_id=uid,
        po_id=pid,
        location_id=loc,
        lines=[rcv.ReceiptLineInput(po_line_id=plid, received_qty=Decimal("100"), lot_code="L42")],
    )
    assert len(sess2.inserted_lots) == 1
    assert sess2.inserted_lots[0]["lc"] == "L42"
