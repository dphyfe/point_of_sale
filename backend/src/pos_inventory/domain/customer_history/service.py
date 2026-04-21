"""Customer transaction-history domain service (US2)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from pos_inventory.core.visibility import VisibilityScope
from pos_inventory.persistence.repositories import customer_history_repo as repo

HistoryFilters = repo.HistoryFilters
HistoryRow = repo.HistoryRow
HistoryLine = repo.HistoryLine


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
    return repo.list_history(
        sess,
        tenant_id=tenant_id,
        customer_id=customer_id,
        filters=filters,
        scope=scope,
        limit=limit,
        offset=offset,
    )


def get_transaction_detail(
    sess: Session,
    *,
    tenant_id: UUID,
    customer_id: UUID,
    kind: str,
    transaction_id: UUID,
    scope: VisibilityScope,
) -> tuple[HistoryRow | None, list[HistoryLine]]:
    return repo.get_transaction_detail(
        sess,
        tenant_id=tenant_id,
        customer_id=customer_id,
        kind=kind,
        transaction_id=transaction_id,
    )


def get_summary_metrics(
    sess: Session, *, tenant_id: UUID, customer_id: UUID
) -> dict:
    return repo.get_summary_metrics(sess, tenant_id=tenant_id, customer_id=customer_id)
