"""Customer transaction-history read repository (US2: FR-016..FR-023, R1).

Composes a UNION ALL over every transaction table that may carry a `customer_id`.
Tables that don't yet exist (e.g. `sales.sale_transaction`, `ret.exchange`,
`svc.service_order` from later features) are silently skipped via a
`to_regclass` guard so this code is forward-compatible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.visibility import VisibilityScope


@dataclass(frozen=True)
class HistoryFilters:
    start: datetime | None = None
    end: datetime | None = None
    kinds: tuple[str, ...] = ()  # subset of {sale, return, exchange, service_order}
    site_ids: tuple[UUID, ...] = ()
    min_total: Decimal | None = None
    sku_id: UUID | None = None


@dataclass(frozen=True)
class HistoryRow:
    id: UUID
    kind: str
    occurred_at: datetime
    store_name: str | None
    register_name: str | None
    cashier_user_id: UUID | None
    total: Decimal | None
    refund_total: Decimal | None
    summary: str | None


@dataclass(frozen=True)
class HistoryLine:
    sku_id: UUID
    sku_code: str | None
    description: str | None
    qty: Decimal
    unit_price: Decimal | None
    line_total: Decimal | None
    serial_numbers: tuple[str, ...] = ()


_RETURN_SQL = """
SELECT cr.id::text AS id,
       'return' AS kind,
       cr.occurred_at,
       cr.cashier_user_id,
       NULL::numeric AS total,
       cr.refund_total,
       site.name AS store_name,
       NULL::text AS register_name
  FROM ret.customer_return cr
  LEFT JOIN inv.location loc ON loc.tenant_id = cr.tenant_id
                            AND loc.id = (SELECT target_location_id
                                            FROM ret.customer_return_line
                                           WHERE return_id = cr.id
                                           LIMIT 1)
  LEFT JOIN inv.site site ON site.id = loc.site_id
 WHERE cr.tenant_id = :tid AND cr.customer_id = :cid
"""

_OPTIONAL_SOURCES = [
    # (regclass, kind, occurred_col, total_col, store_join)
    (
        "ret.exchange",
        "exchange",
        "occurred_at",
        "exchange_total",
    ),
    (
        "sales.sale_transaction",
        "sale",
        "occurred_at",
        "total",
    ),
    (
        "svc.service_order",
        "service_order",
        "occurred_at",
        "total",
    ),
]


def _table_exists(sess: Session, qualified: str) -> bool:
    return bool(
        sess.execute(text("SELECT to_regclass(:t)"), {"t": qualified}).scalar()
    )


def _optional_select(sess: Session, qualified: str, kind: str, occurred: str, total: str) -> str | None:
    if not _table_exists(sess, qualified):
        return None
    return f"""
SELECT t.id::text AS id,
       '{kind}' AS kind,
       t.{occurred} AS occurred_at,
       NULL::uuid AS cashier_user_id,
       t.{total}::numeric AS total,
       NULL::numeric AS refund_total,
       NULL::text AS store_name,
       NULL::text AS register_name
  FROM {qualified} t
 WHERE t.tenant_id = :tid AND t.customer_id = :cid
"""


def list_history(
    sess: Session,
    *,
    tenant_id: UUID,
    customer_id: UUID,
    filters: HistoryFilters,
    scope: VisibilityScope,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[HistoryRow], int]:
    parts = [_RETURN_SQL]
    for qualified, kind, occurred, total in _OPTIONAL_SOURCES:
        sql = _optional_select(sess, qualified, kind, occurred, total)
        if sql is not None:
            parts.append(sql)

    union_sql = "\nUNION ALL\n".join(parts)

    where_extra: list[str] = []
    params: dict = {"tid": str(tenant_id), "cid": str(customer_id)}
    if filters.start:
        where_extra.append("occurred_at >= :start")
        params["start"] = filters.start
    if filters.end:
        where_extra.append("occurred_at <= :end")
        params["end"] = filters.end
    if filters.kinds:
        ks = ",".join(f"'{k}'" for k in filters.kinds)
        where_extra.append(f"kind IN ({ks})")

    extra_sql = (" WHERE " + " AND ".join(where_extra)) if where_extra else ""

    full_sql = f"""
        WITH src AS ({union_sql})
        SELECT id, kind, occurred_at, cashier_user_id, total, refund_total,
               store_name, register_name
          FROM src
         {extra_sql}
         ORDER BY occurred_at DESC
         LIMIT :limit OFFSET :offset
    """
    params["limit"] = limit
    params["offset"] = offset

    rows = sess.execute(text(full_sql), params).all()
    items = [
        HistoryRow(
            id=UUID(r[0]),
            kind=r[1],
            occurred_at=r[2],
            cashier_user_id=r[3],
            total=r[4],
            refund_total=r[5],
            store_name=r[6],
            register_name=r[7],
            summary=None,
        )
        for r in rows
    ]
    # cheap separate count
    count_sql = f"WITH src AS ({union_sql}) SELECT count(*) FROM src{extra_sql}"
    count_params = {k: v for k, v in params.items() if k not in {"limit", "offset"}}
    total = int(sess.execute(text(count_sql), count_params).scalar_one())
    return items, total


def get_transaction_detail(
    sess: Session,
    *,
    tenant_id: UUID,
    customer_id: UUID,
    kind: str,
    transaction_id: UUID,
) -> tuple[HistoryRow | None, list[HistoryLine]]:
    """Drill-down: returns the row + its line items joined to inv.sku and serials."""
    if kind == "return":
        head = sess.execute(
            text(
                """
                SELECT id::text, occurred_at, refund_total, cashier_user_id
                  FROM ret.customer_return
                 WHERE tenant_id = :tid AND customer_id = :cid AND id = :rid
                """
            ),
            {"tid": str(tenant_id), "cid": str(customer_id), "rid": str(transaction_id)},
        ).one_or_none()
        if head is None:
            return None, []
        lines_rows = sess.execute(
            text(
                """
                SELECT crl.sku_id, sku.sku_code, sku.name, crl.qty,
                       NULL::numeric, crl.refund_amount,
                       coalesce(ser.serial_value, '')
                  FROM ret.customer_return_line crl
                  LEFT JOIN inv.sku sku ON sku.id = crl.sku_id
                  LEFT JOIN inv.serial ser ON ser.id = crl.serial_id
                 WHERE crl.tenant_id = :tid AND crl.return_id = :rid
                """
            ),
            {"tid": str(tenant_id), "rid": str(transaction_id)},
        ).all()
        lines = [
            HistoryLine(
                sku_id=r[0],
                sku_code=r[1],
                description=r[2],
                qty=Decimal(r[3]),
                unit_price=r[4],
                line_total=r[5],
                serial_numbers=(r[6],) if r[6] else (),
            )
            for r in lines_rows
        ]
        row = HistoryRow(
            id=UUID(head[0]),
            kind="return",
            occurred_at=head[1],
            store_name=None,
            register_name=None,
            cashier_user_id=head[3],
            total=None,
            refund_total=head[2],
            summary=None,
        )
        return row, lines

    # Optional kinds (exchange/sale/service_order): only look up if table exists.
    qualified = {
        "exchange": "ret.exchange",
        "sale": "sales.sale_transaction",
        "service_order": "svc.service_order",
    }.get(kind)
    if qualified is None or not _table_exists(sess, qualified):
        return None, []

    head = sess.execute(
        text(
            f"""
            SELECT id::text, occurred_at, total::numeric, NULL::uuid
              FROM {qualified}
             WHERE tenant_id = :tid AND customer_id = :cid AND id = :tid_
            """
        ),
        {"tid": str(tenant_id), "cid": str(customer_id), "tid_": str(transaction_id)},
    ).one_or_none()
    if head is None:
        return None, []
    return (
        HistoryRow(
            id=UUID(head[0]),
            kind=kind,
            occurred_at=head[1],
            store_name=None,
            register_name=None,
            cashier_user_id=None,
            total=head[2],
            refund_total=None,
            summary=None,
        ),
        [],
    )


def get_summary_metrics(
    sess: Session, *, tenant_id: UUID, customer_id: UUID
) -> dict:
    """Compute lifetime_spend / visit_count / aov / last_purchase_at / last_store.

    Sales-table is the authoritative source when present; otherwise we fall
    back to (refund_total counts as negative spend) over returns only — which
    is rarely meaningful but matches a returns-only deployment.
    """
    parts: list[str] = []
    if _table_exists(sess, "sales.sale_transaction"):
        parts.append(
            "SELECT total::numeric AS amount, occurred_at, NULL::uuid AS site_id "
            "FROM sales.sale_transaction "
            "WHERE tenant_id = :tid AND customer_id = :cid"
        )
    if _table_exists(sess, "ret.exchange"):
        parts.append(
            "SELECT exchange_total::numeric AS amount, occurred_at, NULL::uuid AS site_id "
            "FROM ret.exchange "
            "WHERE tenant_id = :tid AND customer_id = :cid"
        )

    if not parts:
        # Returns-only summary (best-effort)
        row = sess.execute(
            text(
                """
                SELECT COALESCE(SUM(refund_total), 0)::numeric,
                       COUNT(*),
                       MAX(occurred_at)
                  FROM ret.customer_return
                 WHERE tenant_id = :tid AND customer_id = :cid
                """
            ),
            {"tid": str(tenant_id), "cid": str(customer_id)},
        ).one_or_none()
        spend = Decimal(row[0]) if row and row[0] is not None else Decimal("0")
        visits = int(row[1]) if row and row[1] is not None else 0
        aov = (spend / visits) if visits else Decimal("0")
        return {
            "lifetime_spend": spend,
            "visit_count": visits,
            "average_order_value": aov,
            "last_purchase_at": row[2] if row else None,
            "last_store_visited": None,
        }

    union = "\nUNION ALL\n".join(parts)
    row = sess.execute(
        text(
            f"""
            WITH src AS ({union})
            SELECT COALESCE(SUM(amount), 0)::numeric,
                   COUNT(*),
                   MAX(occurred_at)
              FROM src
            """
        ),
        {"tid": str(tenant_id), "cid": str(customer_id)},
    ).one_or_none()
    spend = Decimal(row[0]) if row and row[0] is not None else Decimal("0")
    visits = int(row[1]) if row and row[1] is not None else 0
    aov = (spend / visits) if visits else Decimal("0")
    return {
        "lifetime_spend": spend,
        "visit_count": visits,
        "average_order_value": aov,
        "last_purchase_at": row[2] if row else None,
        "last_store_visited": None,
    }
