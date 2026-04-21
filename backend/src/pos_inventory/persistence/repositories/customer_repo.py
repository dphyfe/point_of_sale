"""Customer search + lookup repository (R3, FR-001..FR-005).

Search strategy:
1. Phone digits → exact prefix match against `phone_normalized`.
2. Email substring → exact prefix match against `email_normalized`.
3. Free text → tsvector match against `search_vector` (GIN), ranked.

All queries are tenant-scoped via RLS (the GUC is set by `tenant_session`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, func, or_, text
from sqlalchemy.orm import Session

from pos_inventory.persistence.models.customer import Customer

_DIGITS = re.compile(r"\D+")


@dataclass(frozen=True)
class SearchResult:
    items: list[Customer]
    total: int


def _classify(query: str) -> tuple[str, str]:
    """Return (mode, normalized_query). mode in {'phone','email','text'}."""
    q = query.strip()
    if "@" in q:
        return "email", q.lower()
    digits = _DIGITS.sub("", q)
    # treat as phone if at least 3 digits and >=70% of chars are digits or punctuation
    if len(digits) >= 3 and len(digits) / max(len(q), 1) >= 0.5:
        return "phone", digits
    return "text", q


def search_customers(
    sess: Session,
    *,
    query: str | None,
    include_inactive: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> SearchResult:
    q = (query or "").strip()
    stmt = select(Customer)
    if q:
        mode, normalized = _classify(q)
        if mode == "phone":
            stmt = stmt.where(Customer.phone_normalized.like(f"{normalized}%"))
        elif mode == "email":
            stmt = stmt.where(Customer.email_normalized.like(f"{normalized}%"))
        else:
            ts = func.plainto_tsquery("simple", normalized)
            stmt = stmt.where(Customer.search_vector.op("@@")(ts))
            stmt = stmt.order_by(func.ts_rank_cd(Customer.search_vector, ts).desc())
    else:
        # No query: surface most-recently-updated customers as a default list view.
        stmt = stmt.order_by(Customer.updated_at.desc())

    if not include_inactive:
        stmt = stmt.where(Customer.state == "active")

    # cheap total via a windowed count on a wrapping query when needed; for now,
    # do a lightweight separate count for accuracy at small page sizes.
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int(sess.execute(count_stmt).scalar_one())

    rows = sess.execute(stmt.offset(offset).limit(limit)).scalars().all()
    return SearchResult(items=list(rows), total=total)


def get_customer(sess: Session, customer_id: UUID) -> Customer | None:
    return sess.get(Customer, customer_id)
