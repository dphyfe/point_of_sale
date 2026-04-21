"""Customer-view domain service: search, read profile."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from pos_inventory.core.errors import NotFound
from pos_inventory.persistence.models.customer import Customer
from pos_inventory.persistence.repositories.customer_repo import (
    SearchResult,
    get_customer,
    search_customers,
)


@dataclass(frozen=True)
class SearchInput:
    query: str | None
    include_inactive: bool = False
    limit: int = 50
    offset: int = 0


def search(sess: Session, *, tenant_id: UUID, input: SearchInput) -> SearchResult:
    # tenant_id is enforced via RLS; passed for service-layer auditability.
    return search_customers(
        sess,
        query=input.query,
        include_inactive=input.include_inactive,
        limit=input.limit,
        offset=input.offset,
    )


def read_profile(sess: Session, *, tenant_id: UUID, customer_id: UUID) -> Customer:
    row = get_customer(sess, customer_id)
    if row is None:
        raise NotFound(f"customer {customer_id} not found")
    return row


def display_name(c: Customer) -> str:
    if c.contact_type == "company" and c.company_name:
        return c.company_name
    parts = [p for p in (c.first_name, c.last_name) if p]
    return " ".join(parts) if parts else (c.company_name or "")
