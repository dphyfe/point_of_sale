"""Unit tests for transfer service: ship/receive serial pinning (FR-027/028, SC-008)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from pos_inventory.core.errors import BusinessRuleConflict, ValidationFailed
from pos_inventory.domain.transfers import service as tsvc

from ..test_ledger import FakeSession as LedgerFakeSession, _Result, _Row


@dataclass
class FakeXfrSession(LedgerFakeSession):
    state: str = "draft"
    src_loc: UUID | None = None
    dst_loc: UUID | None = None
    in_transit_loc: UUID | None = None
    sites: list[UUID] = field(default_factory=list)
    lines: list[tuple[UUID, UUID, Decimal]] = field(default_factory=list)
    line_serials: dict[UUID, list[UUID]] = field(default_factory=dict)
    inserted_transfers: list[dict] = field(default_factory=list)
    inserted_lines: list[dict] = field(default_factory=list)
    inserted_serials_xfr: list[dict] = field(default_factory=list)
    state_updates: list[dict] = field(default_factory=list)

    def execute(self, stmt, params=None):  # noqa: ANN001
        sql = " ".join(str(stmt).lower().split())
        params = params or {}
        if "select id from inv.location" in sql and "virtual_in_transit" in sql:
            if self.in_transit_loc:
                return _Result([_Row((self.in_transit_loc,))])
            return _Result([])
        if sql.startswith("select id from inv.site"):
            return _Result([_Row((s,)) for s in self.sites])
        if "insert into inv.location" in sql and "virtual_in_transit" in sql:
            self.in_transit_loc = UUID(params["id"])
            return _Result([])
        if "select state, source_location_id, destination_location_id from xfr.transfer" in sql:
            return _Result([_Row((self.state, self.src_loc, self.dst_loc))])
        if sql.startswith("select id, sku_id, qty from xfr.transfer_line"):
            return _Result([_Row(t) for t in self.lines])
        if "select serial_id from xfr.transfer_serial" in sql:
            line_id = UUID(params["id"])
            return _Result([_Row((s,)) for s in self.line_serials.get(line_id, [])])
        if sql.startswith("insert into xfr.transfer "):
            self.inserted_transfers.append(params)
            return _Result([])
        if sql.startswith("insert into xfr.transfer_line"):
            self.inserted_lines.append(params)
            return _Result([])
        if sql.startswith("insert into xfr.transfer_serial"):
            self.inserted_serials_xfr.append(params)
            return _Result([])
        if sql.startswith("update xfr.transfer"):
            self.state_updates.append(params)
            if "state = 'shipped'" in sql:
                self.state = "shipped"
            if "state = 'received'" in sql:
                self.state = "received"
            return _Result([])
        if "insert into audit.audit_entry" in sql or "insert into outbox.event" in sql:
            return _Result([])
        if "update inv.serial" in sql:
            # Mirror serial location/state updates from the ledger writer
            # so test assertions on s.serials reflect the move.
            sid_key = params.get("id")
            if sid_key is not None:
                sid = UUID(sid_key)
                row = self.serials.get(sid)
                if row is not None:
                    new_state = params.get("state") or params.get("s")
                    if "lid" in params:
                        if params.get("null_loc"):
                            row[1] = None
                        elif params["lid"] is not None:
                            row[1] = UUID(params["lid"])
                    if new_state:
                        row[2] = new_state
            # Fall through to LedgerFakeSession to also append to serial_updates.
        return super().execute(stmt, params)


def _seed_in_transit(s: FakeXfrSession, tid: UUID) -> UUID:
    loc = uuid4()
    s.sites = [uuid4()]
    return loc


def test_create_requires_distinct_source_and_destination():
    tid, uid, loc = uuid4(), uuid4(), uuid4()
    s = FakeXfrSession()
    with pytest.raises(ValidationFailed):
        tsvc.create_transfer(
            s,
            tenant_id=tid,
            actor_user_id=uid,  # type: ignore[arg-type]
            input=tsvc.TransferInput(
                source_location_id=loc,
                destination_location_id=loc,
                lines=[tsvc.TransferLineInput(sku_id=uuid4(), qty=Decimal("1"))],
            ),
        )


def test_create_serialized_requires_matching_serial_count():
    tid, uid, src, dst, sku = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    s = FakeXfrSession()
    with pytest.raises(ValidationFailed):
        tsvc.create_transfer(
            s,
            tenant_id=tid,
            actor_user_id=uid,  # type: ignore[arg-type]
            input=tsvc.TransferInput(
                source_location_id=src,
                destination_location_id=dst,
                lines=[
                    tsvc.TransferLineInput(
                        sku_id=sku,
                        qty=Decimal("2"),
                        serial_ids=[uuid4()],  # only 1 serial for qty=2
                    )
                ],
            ),
        )


def test_ship_requires_draft_state():
    s = FakeXfrSession()
    s.state = "shipped"
    with pytest.raises(BusinessRuleConflict):
        tsvc.ship(s, tenant_id=uuid4(), actor_user_id=uuid4(), transfer_id=uuid4())  # type: ignore[arg-type]


def test_ship_then_receive_serial_path_lands_at_destination():
    tid, uid, src, dst, sku, ser = uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    s = FakeXfrSession()
    s.state = "draft"
    s.src_loc, s.dst_loc = src, dst
    s.in_transit_loc = uuid4()  # already exists
    line_id = uuid4()
    s.lines = [(line_id, sku, Decimal("1"))]
    s.line_serials = {line_id: [ser]}
    # Seed serials with current state/location for ledger
    s.serials[ser] = [Decimal("100"), src, "sellable"]
    # Seed source balance for outbound
    s.balances[(str(tid), str(sku), str(src))] = [Decimal("1"), Decimal("0")]

    tsvc.ship(s, tenant_id=tid, actor_user_id=uid, transfer_id=uuid4())  # type: ignore[arg-type]
    assert s.state == "shipped"
    # serial moved to in_transit and state in_transit
    assert s.serials[ser][1] == s.in_transit_loc
    assert s.serials[ser][2] == "in_transit"
    # in_transit balance should now have +1
    in_t_bal = s.balances.get((str(tid), str(sku), str(s.in_transit_loc)))
    assert in_t_bal is not None and in_t_bal[0] == Decimal("1")

    tsvc.receive(s, tenant_id=tid, actor_user_id=uid, transfer_id=uuid4())  # type: ignore[arg-type]
    assert s.state == "received"
    assert s.serials[ser][1] == dst
    assert s.serials[ser][2] == "sellable"
    # destination balance has +1, in_transit back to 0
    assert s.balances[(str(tid), str(sku), str(dst))][0] == Decimal("1")
    assert s.balances[(str(tid), str(sku), str(s.in_transit_loc))][0] == Decimal("0")
