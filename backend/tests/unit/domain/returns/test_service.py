"""Unit tests for the returns service.

The fake session emulates just enough SQL: serial lookup, prior-sale check,
and pass-through to the ledger writer for inbound movements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from pos_inventory.core.errors import BusinessRuleConflict, NotFound
from pos_inventory.domain.returns import service as rsvc

from ..test_ledger import FakeSession as LedgerFakeSession, _Result, _Row


@dataclass
class FakeRetSession(LedgerFakeSession):
    serials_by_value: dict[tuple[UUID, str], tuple[UUID, UUID]] = field(default_factory=dict)
    prior_sales: set[UUID] = field(default_factory=set)
    serial_state: dict[UUID, str] = field(default_factory=dict)
    inserted_returns: list[dict] = field(default_factory=list)
    inserted_return_lines: list[dict] = field(default_factory=list)

    def execute(self, stmt, params=None):  # noqa: ANN001
        sql = " ".join(str(stmt).lower().split())
        params = params or {}

        if "from inv.serial" in sql and "serial_value = :sv" in sql and "select id, sku_id" in sql:
            key = (UUID(params["tid"]), params["sv"])
            v = self.serials_by_value.get(key)
            return _Result([_Row(v)] if v else [])

        if "from inv.ledger" in sql and "source_kind = 'sale'" in sql:
            sid = UUID(params["sid"])
            return _Result([_Row((1,))] if sid in self.prior_sales else [])

        if "select state, current_location_id from inv.serial" in sql:
            sid = UUID(params["id"])
            st = self.serial_state.get(sid)
            return _Result([_Row((st, None))] if st else [])

        if "update inv.serial" in sql:
            sid = UUID(params["id"])
            # serial_svc._set_state uses param key "s"; ledger uses "state".
            new_state = params.get("s") or params.get("state")
            if new_state:
                self.serial_state[sid] = new_state
            return _Result([])

        if "insert into ret.customer_return " in sql or sql.startswith("insert into ret.customer_return("):
            self.inserted_returns.append(params)
            return _Result([])
        if "insert into ret.customer_return_line" in sql:
            self.inserted_return_lines.append(params)
            return _Result([])
        if "insert into audit.audit_entry" in sql or "insert into outbox.event" in sql:
            return _Result([])

        return super().execute(stmt, params)


def test_with_receipt_non_serialized_writes_inbound_movement():
    tid, uid, cashier, sku, loc = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    s = FakeRetSession()
    rid = rsvc.post_return(
        s,  # type: ignore[arg-type]
        tenant_id=tid,
        actor_user_id=uid,
        input=rsvc.ReturnInput(
            cashier_user_id=cashier,
            occurred_at=None,
            original_sale_id=uuid4(),
            no_receipt=False,
            lines=[
                rsvc.ReturnLineInput(
                    sku_id=sku,
                    qty=Decimal("2"),
                    reason_code="defective",
                    disposition="hold",
                    target_location_id=loc,
                    refund_amount=Decimal("10"),
                ),
            ],
        ),
    )
    assert s.inserted_returns[-1]["rm"] == "original"
    assert s.inserted_returns[-1]["nr"] is False
    # ledger inbound posted
    assert any(p["sk"] == "return" and Decimal(p["qd"]) == Decimal("2") for p in s.inserted_ledger)


def test_no_receipt_requires_manager_approval():
    tid, uid, cashier, sku, loc = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    s = FakeRetSession()
    with pytest.raises(BusinessRuleConflict):
        rsvc.post_return(
            s,  # type: ignore[arg-type]
            tenant_id=tid,
            actor_user_id=uid,
            input=rsvc.ReturnInput(
                cashier_user_id=cashier,
                occurred_at=None,
                no_receipt=True,
                manager_approval_user_id=None,
                lines=[
                    rsvc.ReturnLineInput(
                        sku_id=sku,
                        qty=Decimal("1"),
                        reason_code="x",
                        disposition="hold",
                        target_location_id=loc,
                    )
                ],
            ),
        )


def test_no_receipt_forces_store_credit():
    tid, uid, cashier, mgr, sku, loc = uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    s = FakeRetSession()
    rsvc.post_return(
        s,  # type: ignore[arg-type]
        tenant_id=tid,
        actor_user_id=uid,
        input=rsvc.ReturnInput(
            cashier_user_id=cashier,
            occurred_at=None,
            no_receipt=True,
            manager_approval_user_id=mgr,
            refund_method="cash",  # explicitly try cash
            lines=[
                rsvc.ReturnLineInput(
                    sku_id=sku,
                    qty=Decimal("1"),
                    reason_code="x",
                    disposition="hold",
                    target_location_id=loc,
                )
            ],
        ),
    )
    assert s.inserted_returns[-1]["rm"] == "store_credit"


def test_no_receipt_serialized_requires_prior_sale():
    tid, uid, cashier, mgr, sku, loc, ser = uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    s = FakeRetSession()
    s.serials_by_value[(tid, "SN-1")] = (ser, sku)
    # prior_sales empty → must raise
    with pytest.raises(BusinessRuleConflict):
        rsvc.post_return(
            s,  # type: ignore[arg-type]
            tenant_id=tid,
            actor_user_id=uid,
            input=rsvc.ReturnInput(
                cashier_user_id=cashier,
                occurred_at=None,
                no_receipt=True,
                manager_approval_user_id=mgr,
                lines=[
                    rsvc.ReturnLineInput(
                        sku_id=sku,
                        qty=Decimal("1"),
                        reason_code="x",
                        disposition="hold",
                        target_location_id=loc,
                        serial_value="SN-1",
                    )
                ],
            ),
        )


def test_serialized_with_vendor_rma_disposition_marks_rma_pending():
    tid, uid, cashier, sku, loc, ser = uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    s = FakeRetSession()
    s.serials_by_value[(tid, "SN-2")] = (ser, sku)
    s.serial_state[ser] = "sold"  # required precondition for return_
    # Ledger SELECT (unit_cost, current_location_id, state) FOR UPDATE.
    s.serials[ser] = [Decimal("100"), None, "sold"]

    rsvc.post_return(
        s,  # type: ignore[arg-type]
        tenant_id=tid,
        actor_user_id=uid,
        input=rsvc.ReturnInput(
            cashier_user_id=cashier,
            occurred_at=None,
            original_sale_id=uuid4(),
            no_receipt=False,
            lines=[
                rsvc.ReturnLineInput(
                    sku_id=sku,
                    qty=Decimal("1"),
                    reason_code="defective",
                    disposition="vendor_rma",
                    target_location_id=loc,
                    serial_value="SN-2",
                )
            ],
        ),
    )
    assert s.serial_state[ser] == "rma_pending"


def test_serialized_scrap_disposition_skips_inbound_and_marks_scrapped():
    tid, uid, cashier, sku, loc, ser = uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    s = FakeRetSession()
    s.serials_by_value[(tid, "SN-3")] = (ser, sku)
    s.serial_state[ser] = "sold"
    s.serials[ser] = [Decimal("100"), None, "sold"]

    rsvc.post_return(
        s,  # type: ignore[arg-type]
        tenant_id=tid,
        actor_user_id=uid,
        input=rsvc.ReturnInput(
            cashier_user_id=cashier,
            occurred_at=None,
            original_sale_id=uuid4(),
            lines=[
                rsvc.ReturnLineInput(
                    sku_id=sku,
                    qty=Decimal("1"),
                    reason_code="damage",
                    disposition="scrap",
                    target_location_id=loc,
                    serial_value="SN-3",
                )
            ],
        ),
    )
    assert s.serial_state[ser] == "scrapped"
    assert not any(p["sk"] == "return" for p in s.inserted_ledger)
