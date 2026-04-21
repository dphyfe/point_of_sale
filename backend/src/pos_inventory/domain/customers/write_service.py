"""Customer create/update/lifecycle/merge service (US3, FR-007..FR-015, R4-R6, R10).

All mutations write a `cust.profile_change` audit row in the same transaction as
the data change. Sensitive fields (`tax_id`, `date_of_birth`) are hashed with
last-4 retained per R6. Optimistic concurrency is enforced by `If-Match`
against the row's `version` column.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.errors import (
    BusinessRuleConflict,
    NotFound,
    RoleForbidden,
    ValidationFailed,
)
from pos_inventory.domain.customers.concurrency import check_if_match
from pos_inventory.domain.customers.normalization import (
    normalize_email,
    to_e164,
    validate_email_or_raise,
)
from pos_inventory.domain.customers.redaction import hash_with_last4
from pos_inventory.persistence.models.customer import Customer

# Field set considered "sensitive" → audit values are hashed.
SENSITIVE_FIELDS: frozenset[str] = frozenset({"tax_id", "date_of_birth"})

# Roles allowed to mutate sensitive fields (FR-010, FR-036).
SENSITIVE_WRITER_ROLES: frozenset[str] = frozenset({"Store Manager", "Admin"})

# Fields tracked for diffing (excludes derived/system).
TRACKED_FIELDS: tuple[str, ...] = (
    "contact_type",
    "first_name",
    "last_name",
    "company_name",
    "primary_phone",
    "secondary_phone",
    "email",
    "preferred_channel",
    "language",
    "tags",
    "external_loyalty_id",
    "external_crm_id",
    "tax_id",
    "date_of_birth",
)


@dataclass(frozen=True)
class CustomerData:
    contact_type: str = "individual"
    first_name: str | None = None
    last_name: str | None = None
    company_name: str | None = None
    primary_phone: str | None = None
    secondary_phone: str | None = None
    email: str | None = None
    preferred_channel: str = "email"
    language: str | None = None
    tags: tuple[str, ...] = ()
    external_loyalty_id: str | None = None
    external_crm_id: str | None = None
    tax_id: str | None = None
    date_of_birth: date | None = None
    client_request_id: UUID | None = None


def _validate_minimal_identity(d: CustomerData) -> None:
    if d.contact_type == "company":
        if not (d.company_name and d.company_name.strip()):
            raise ValidationFailed("company_name required for company contact_type")
    else:
        if not ((d.first_name and d.first_name.strip()) or (d.last_name and d.last_name.strip())):
            raise ValidationFailed("first_name or last_name required for individual contact_type")
    has_contact = bool(d.email or d.primary_phone or d.external_loyalty_id)
    if not has_contact:
        raise ValidationFailed("at least one of email, primary_phone, external_loyalty_id required")
    if d.email:
        validate_email_or_raise(d.email)


def _to_db_payload(d: CustomerData) -> dict[str, Any]:
    return {
        "contact_type": d.contact_type,
        "first_name": d.first_name,
        "last_name": d.last_name,
        "company_name": d.company_name,
        "primary_phone": d.primary_phone,
        "secondary_phone": d.secondary_phone,
        "email": normalize_email(d.email) if d.email else None,
        "preferred_channel": d.preferred_channel,
        "language": d.language,
        "tags": list(d.tags),
        "external_loyalty_id": d.external_loyalty_id,
        "external_crm_id": d.external_crm_id,
        "tax_id": d.tax_id,
        "date_of_birth": d.date_of_birth,
    }


def _write_change(
    sess: Session,
    *,
    tenant_id: UUID,
    customer_id: UUID,
    actor_user_id: UUID | None,
    field: str,
    old_value: Any,
    new_value: Any,
    change_kind: str,
) -> None:
    sensitive = field in SENSITIVE_FIELDS
    sess.execute(
        text(
            """
            INSERT INTO cust.profile_change
                (id, tenant_id, customer_id, actor_user_id, occurred_at,
                 field, old_value, new_value, change_kind)
            VALUES
                (:id, :tid, :cid, :uid, :ts, :field, :ov, :nv, :ck)
            """
        ),
        {
            "id": str(uuid4()),
            "tid": str(tenant_id),
            "cid": str(customer_id),
            "uid": str(actor_user_id) if actor_user_id else None,
            "ts": datetime.now(timezone.utc),
            "field": field,
            "ov": hash_with_last4(str(old_value)) if sensitive and old_value is not None else (str(old_value) if old_value is not None else None),
            "nv": hash_with_last4(str(new_value)) if sensitive and new_value is not None else (str(new_value) if new_value is not None else None),
            "ck": change_kind,
        },
    )


def _enforce_sensitive_rbac(roles: frozenset[str], data: CustomerData, *, prior: Customer | None) -> None:
    if SENSITIVE_WRITER_ROLES & roles:
        return
    if data.tax_id is not None and (prior is None or prior.tax_id != data.tax_id):
        raise RoleForbidden("tax_id requires Store Manager or Admin")
    if data.date_of_birth is not None and (prior is None or prior.date_of_birth != data.date_of_birth):
        raise RoleForbidden("date_of_birth requires Store Manager or Admin")


def create_customer(
    sess: Session,
    *,
    tenant_id: UUID,
    actor_user_id: UUID | None,
    actor_roles: frozenset[str],
    data: CustomerData,
) -> Customer:
    """Create a customer. Idempotent on (tenant_id, client_request_id) (R10)."""
    _validate_minimal_identity(data)
    _enforce_sensitive_rbac(actor_roles, data, prior=None)

    # Idempotent replay on client_request_id.
    if data.client_request_id is not None:
        existing = sess.execute(
            text(
                "SELECT id FROM cust.customer WHERE tenant_id = :tid AND client_request_id = :crid"
            ),
            {"tid": str(tenant_id), "crid": str(data.client_request_id)},
        ).one_or_none()
        if existing is not None:
            cust = sess.get(Customer, existing[0])
            assert cust is not None
            return cust

    new_id = uuid4()
    now = datetime.now(timezone.utc)
    payload = _to_db_payload(data)
    payload.update(
        {
            "id": str(new_id),
            "tid": str(tenant_id),
            "crid": str(data.client_request_id) if data.client_request_id else None,
            "ts": now,
            "uid": str(actor_user_id) if actor_user_id else None,
        }
    )
    sess.execute(
        text(
            """
            INSERT INTO cust.customer
                (id, tenant_id, client_request_id, contact_type, first_name, last_name,
                 company_name, primary_phone, secondary_phone, email, preferred_channel,
                 language, tags, external_loyalty_id, external_crm_id, tax_id, date_of_birth,
                 state, version, created_at, created_by_user_id, updated_at, updated_by_user_id)
            VALUES
                (:id, :tid, :crid, :contact_type, :first_name, :last_name,
                 :company_name, :primary_phone, :secondary_phone, :email, :preferred_channel,
                 :language, :tags, :external_loyalty_id, :external_crm_id, :tax_id, :date_of_birth,
                 'active', 1, :ts, :uid, :ts, :uid)
            ON CONFLICT (tenant_id, client_request_id) DO NOTHING
            """
        ),
        payload,
    )

    # Re-select (covers ON CONFLICT race).
    cust = sess.get(Customer, new_id)
    if cust is None and data.client_request_id is not None:
        existing = sess.execute(
            text("SELECT id FROM cust.customer WHERE tenant_id = :tid AND client_request_id = :crid"),
            {"tid": str(tenant_id), "crid": str(data.client_request_id)},
        ).one_or_none()
        if existing is not None:
            cust = sess.get(Customer, existing[0])
    assert cust is not None, "create_customer: row missing after insert"

    _write_change(
        sess,
        tenant_id=tenant_id,
        customer_id=cust.id,
        actor_user_id=actor_user_id,
        field="__row__",
        old_value=None,
        new_value=cust.id,
        change_kind="update",
    )
    return cust


def update_customer(
    sess: Session,
    *,
    tenant_id: UUID,
    customer_id: UUID,
    actor_user_id: UUID | None,
    actor_roles: frozenset[str],
    expected_version: int,
    data: CustomerData,
) -> Customer:
    cust = sess.get(Customer, customer_id)
    if cust is None:
        raise NotFound(f"customer {customer_id}")
    if cust.state in {"merged", "anonymized"}:
        raise BusinessRuleConflict(f"cannot edit customer in state {cust.state}")
    check_if_match(expected_version, cust.version)

    _enforce_sensitive_rbac(actor_roles, data, prior=cust)

    new_payload = _to_db_payload(data)
    diffs: list[tuple[str, Any, Any]] = []
    for field in TRACKED_FIELDS:
        old = getattr(cust, field)
        new = new_payload.get(field)
        if isinstance(old, list):
            old_cmp = list(old)
        else:
            old_cmp = old
        if old_cmp != new:
            diffs.append((field, old, new))

    if not diffs:
        return cust  # no-op, version unchanged

    # Apply update + bump version.
    new_payload.update(
        {
            "id": str(customer_id),
            "tid": str(tenant_id),
            "ts": datetime.now(timezone.utc),
            "uid": str(actor_user_id) if actor_user_id else None,
        }
    )
    sess.execute(
        text(
            """
            UPDATE cust.customer SET
                contact_type=:contact_type, first_name=:first_name, last_name=:last_name,
                company_name=:company_name, primary_phone=:primary_phone,
                secondary_phone=:secondary_phone, email=:email,
                preferred_channel=:preferred_channel, language=:language, tags=:tags,
                external_loyalty_id=:external_loyalty_id, external_crm_id=:external_crm_id,
                tax_id=:tax_id, date_of_birth=:date_of_birth,
                version=version+1, updated_at=:ts, updated_by_user_id=:uid
              WHERE id=:id AND tenant_id=:tid
            """
        ),
        new_payload,
    )

    for field, old, new in diffs:
        _write_change(
            sess,
            tenant_id=tenant_id,
            customer_id=customer_id,
            actor_user_id=actor_user_id,
            field=field,
            old_value=old,
            new_value=new,
            change_kind="update",
        )

    sess.refresh(cust)
    return cust


def deactivate_customer(
    sess: Session,
    *,
    tenant_id: UUID,
    customer_id: UUID,
    actor_user_id: UUID | None,
    reason: str | None = None,
) -> Customer:
    return _set_state(sess, tenant_id=tenant_id, customer_id=customer_id, actor_user_id=actor_user_id, new_state="inactive", change_kind="deactivate", reason=reason)


def reactivate_customer(
    sess: Session,
    *,
    tenant_id: UUID,
    customer_id: UUID,
    actor_user_id: UUID | None,
) -> Customer:
    return _set_state(sess, tenant_id=tenant_id, customer_id=customer_id, actor_user_id=actor_user_id, new_state="active", change_kind="reactivate", reason=None)


def _set_state(
    sess: Session,
    *,
    tenant_id: UUID,
    customer_id: UUID,
    actor_user_id: UUID | None,
    new_state: str,
    change_kind: str,
    reason: str | None,
) -> Customer:
    cust = sess.get(Customer, customer_id)
    if cust is None:
        raise NotFound(f"customer {customer_id}")
    if cust.state == new_state:
        return cust
    sess.execute(
        text(
            """
            UPDATE cust.customer
               SET state=:s, version=version+1, updated_at=:ts, updated_by_user_id=:uid
             WHERE id=:id AND tenant_id=:tid
            """
        ),
        {
            "s": new_state,
            "ts": datetime.now(timezone.utc),
            "uid": str(actor_user_id) if actor_user_id else None,
            "id": str(customer_id),
            "tid": str(tenant_id),
        },
    )
    _write_change(
        sess,
        tenant_id=tenant_id,
        customer_id=customer_id,
        actor_user_id=actor_user_id,
        field="state",
        old_value=cust.state,
        new_value=new_state,
        change_kind=change_kind,
    )
    if reason:
        _write_change(
            sess,
            tenant_id=tenant_id,
            customer_id=customer_id,
            actor_user_id=actor_user_id,
            field="reason",
            old_value=None,
            new_value=reason,
            change_kind=change_kind,
        )
    sess.refresh(cust)
    return cust


def anonymize_customer(
    sess: Session,
    *,
    tenant_id: UUID,
    customer_id: UUID,
    actor_user_id: UUID | None,
) -> Customer:
    cust = sess.get(Customer, customer_id)
    if cust is None:
        raise NotFound(f"customer {customer_id}")
    if cust.state == "anonymized":
        return cust
    sess.execute(
        text(
            """
            UPDATE cust.customer SET
                first_name=NULL, last_name=NULL, company_name=NULL,
                primary_phone=NULL, secondary_phone=NULL, email=NULL,
                tax_id=NULL, date_of_birth=NULL, language=NULL,
                tags='{}'::text[], external_loyalty_id=NULL, external_crm_id=NULL,
                phone_normalized=NULL, email_normalized=NULL, display_name_lower=NULL,
                search_vector=NULL,
                state='anonymized', version=version+1,
                updated_at=:ts, updated_by_user_id=:uid
             WHERE id=:id AND tenant_id=:tid
            """
        ),
        {
            "ts": datetime.now(timezone.utc),
            "uid": str(actor_user_id) if actor_user_id else None,
            "id": str(customer_id),
            "tid": str(tenant_id),
        },
    )
    _write_change(
        sess,
        tenant_id=tenant_id,
        customer_id=customer_id,
        actor_user_id=actor_user_id,
        field="state",
        old_value=cust.state,
        new_value="anonymized",
        change_kind="anonymize",
    )
    sess.refresh(cust)
    return cust


# Tables that may carry a customer_id FK and need rewriting on merge (per
# 0015_link_customer_to_sales). Optional tables guarded by to_regclass.
_LINKED_TABLES_KNOWN: tuple[str, ...] = ("ret.customer_return",)
_LINKED_TABLES_OPTIONAL: tuple[str, ...] = (
    "ret.exchange",
    "sales.sale_transaction",
    "svc.service_order",
)


def merge_customers(
    sess: Session,
    *,
    tenant_id: UUID,
    survivor_id: UUID,
    merged_away_id: UUID,
    actor_user_id: UUID | None,
    summary: str | None = None,
) -> None:
    if survivor_id == merged_away_id:
        raise BusinessRuleConflict("cannot merge a customer into itself")

    survivor = sess.get(Customer, survivor_id)
    away = sess.get(Customer, merged_away_id)
    if survivor is None or away is None:
        raise NotFound("survivor or merged-away not found")
    if away.state == "merged" or away.merged_into is not None:
        raise BusinessRuleConflict("merged-away customer is already merged")
    if survivor.state == "merged":
        raise BusinessRuleConflict("survivor is itself merged")

    sess.execute(
        text(
            """
            INSERT INTO cust.merge
                (id, tenant_id, survivor_id, merged_away_id, performed_by_user_id, occurred_at, summary)
            VALUES (:id, :tid, :sid, :aid, :uid, :ts, :sum)
            """
        ),
        {
            "id": str(uuid4()),
            "tid": str(tenant_id),
            "sid": str(survivor_id),
            "aid": str(merged_away_id),
            "uid": str(actor_user_id) if actor_user_id else None,
            "ts": datetime.now(timezone.utc),
            "sum": summary,
        },
    )

    # Rewrite linked tables.
    rewrite_targets = list(_LINKED_TABLES_KNOWN)
    for table in _LINKED_TABLES_OPTIONAL:
        if sess.execute(text("SELECT to_regclass(:t)"), {"t": table}).scalar():
            rewrite_targets.append(table)
    for table in rewrite_targets:
        sess.execute(
            text(
                f"UPDATE {table} SET customer_id=:sid WHERE tenant_id=:tid AND customer_id=:aid"
            ),
            {
                "sid": str(survivor_id),
                "tid": str(tenant_id),
                "aid": str(merged_away_id),
            },
        )

    sess.execute(
        text(
            """
            UPDATE cust.customer
               SET merged_into=:sid, state='merged', version=version+1,
                   updated_at=:ts, updated_by_user_id=:uid
             WHERE id=:aid AND tenant_id=:tid
            """
        ),
        {
            "sid": str(survivor_id),
            "ts": datetime.now(timezone.utc),
            "uid": str(actor_user_id) if actor_user_id else None,
            "aid": str(merged_away_id),
            "tid": str(tenant_id),
        },
    )
    _write_change(
        sess,
        tenant_id=tenant_id,
        customer_id=merged_away_id,
        actor_user_id=actor_user_id,
        field="merged_into",
        old_value=None,
        new_value=survivor_id,
        change_kind="merge",
    )


def resolve_customer_id(
    sess: Session, *, tenant_id: UUID, customer_id: UUID, max_depth: int = 5
) -> UUID:
    """Follow merged_into chains up to max_depth."""
    current = customer_id
    for _ in range(max_depth):
        row = sess.execute(
            text(
                "SELECT merged_into FROM cust.customer WHERE id=:id AND tenant_id=:tid"
            ),
            {"id": str(current), "tid": str(tenant_id)},
        ).one_or_none()
        if row is None or row[0] is None:
            return current
        current = row[0] if isinstance(row[0], UUID) else UUID(str(row[0]))
    raise BusinessRuleConflict(f"merge chain depth exceeded {max_depth}")


def list_audit(
    sess: Session, *, tenant_id: UUID, customer_id: UUID, limit: int = 200
) -> list[dict]:
    rows = sess.execute(
        text(
            """
            SELECT id::text, occurred_at, actor_user_id, field, old_value, new_value, change_kind
              FROM cust.profile_change
             WHERE tenant_id=:tid AND customer_id=:cid
             ORDER BY occurred_at DESC
             LIMIT :n
            """
        ),
        {"tid": str(tenant_id), "cid": str(customer_id), "n": limit},
    ).all()
    return [
        {
            "id": r[0],
            "occurred_at": r[1],
            "actor_user_id": r[2],
            "field": r[3],
            "old_value": r[4],
            "new_value": r[5],
            "change_kind": r[6],
        }
        for r in rows
    ]
