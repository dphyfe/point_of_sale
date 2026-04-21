"""Tests for customer transaction-history composition (US2: FR-019..FR-023).

Uses an in-memory FakeSession that satisfies the small set of SQL strings
emitted by `customer_history_repo.list_history` and friends. We assert
reverse-chronological ordering and graceful handling of missing optional
tables (sales/exchange/service_order).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from pos_inventory.core.visibility import VisibilityScope
from pos_inventory.domain.customer_history import service as history_service
from pos_inventory.domain.customer_history.service import HistoryFilters


@dataclass
class _FakeResult:
    rows: list[tuple]

    def all(self):
        return list(self.rows)

    def one_or_none(self):
        return self.rows[0] if self.rows else None

    def scalar_one(self):
        return self.rows[0][0]

    def scalar(self):
        return self.rows[0][0] if self.rows else None


@dataclass
class FakeHistorySession:
    returns: list[tuple] = field(default_factory=list)
    sql_log: list[str] = field(default_factory=list)
    table_exists: dict[str, bool] = field(default_factory=dict)

    def execute(self, stmt, params: dict[str, Any] | None = None):  # noqa: ANN001
        sql = str(stmt).lower()
        self.sql_log.append(sql)
        if "select to_regclass" in sql:
            t = (params or {}).get("t", "")
            return _FakeResult([(t if self.table_exists.get(t, False) else None,)])
        if "with src as" in sql and "select count(*)" in sql:
            return _FakeResult([(len(self.returns),)])
        if "with src as" in sql and "order by occurred_at desc" in sql:
            # Mimic ORDER BY occurred_at DESC LIMIT/OFFSET
            sorted_rows = sorted(self.returns, key=lambda r: r[2], reverse=True)
            limit = (params or {}).get("limit", 50)
            offset = (params or {}).get("offset", 0)
            return _FakeResult(sorted_rows[offset : offset + limit])
        raise AssertionError(f"unexpected sql: {sql[:160]}")


def test_list_history_orders_reverse_chrono_returns_only():
    sess = FakeHistorySession()
    cid = uuid4()
    now = datetime.now(timezone.utc)
    sess.returns = [
        # (id, kind, occurred_at, cashier_user_id, total, refund_total, store_name, register_name)
        (str(uuid4()), "return", now - timedelta(days=2), uuid4(), None, Decimal("10"), "S1", None),
        (str(uuid4()), "return", now - timedelta(days=1), uuid4(), None, Decimal("12"), "S1", None),
        (str(uuid4()), "return", now, uuid4(), None, Decimal("5"), "S2", None),
    ]
    items, total = history_service.list_history(
        sess,  # type: ignore[arg-type]
        tenant_id=uuid4(),
        customer_id=cid,
        filters=HistoryFilters(),
        scope=VisibilityScope(scope="all", site_ids=frozenset()),
        limit=10,
        offset=0,
    )
    assert total == 3
    assert [i.occurred_at for i in items] == sorted(
        [r[2] for r in sess.returns], reverse=True
    )


def test_list_history_handles_missing_optional_tables():
    sess = FakeHistorySession(table_exists={"ret.exchange": False, "sales.sale_transaction": False, "svc.service_order": False})
    items, total = history_service.list_history(
        sess,  # type: ignore[arg-type]
        tenant_id=uuid4(),
        customer_id=uuid4(),
        filters=HistoryFilters(),
        scope=VisibilityScope(scope="all", site_ids=frozenset()),
        limit=10,
        offset=0,
    )
    assert items == []
    assert total == 0
    # Ensure the regclass guard fired for each optional source.
    regclass_calls = [s for s in sess.sql_log if "select to_regclass" in s]
    assert len(regclass_calls) == 3
