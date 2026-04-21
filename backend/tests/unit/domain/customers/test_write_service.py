"""Unit tests for US3: profile audit, optimistic concurrency, RBAC, merge."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest

from pos_inventory.core.errors import (
    BusinessRuleConflict,
    NotFound,
    RoleForbidden,
)
from pos_inventory.domain.customers import write_service
from pos_inventory.domain.customers.concurrency import StaleVersion
from pos_inventory.domain.customers.write_service import CustomerData
from pos_inventory.persistence.models.customer import Customer


@dataclass
class _Result:
    rows: list[tuple]

    def one_or_none(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)

    def scalar(self):
        return self.rows[0][0] if self.rows else None

    def scalar_one(self):
        return self.rows[0][0]


@dataclass
class FakeWriteSession:
    """Captures executed SQL + minimal `sess.get` for write_service tests."""

    inserts: list[dict[str, Any]] = field(default_factory=list)
    updates: list[dict[str, Any]] = field(default_factory=list)
    profile_changes: list[dict[str, Any]] = field(default_factory=list)
    merges: list[dict[str, Any]] = field(default_factory=list)
    rewrites: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    customers: dict[UUID, Customer] = field(default_factory=dict)
    optional_tables: set[str] = field(default_factory=set)
    idempotency_hits: dict[UUID, UUID] = field(default_factory=dict)

    # --- SQLAlchemy Session shims --------------------------------------------------
    def execute(self, stmt, params: dict[str, Any] | None = None):  # noqa: ANN001
        sql = " ".join(str(stmt).lower().split())
        params = params or {}
        if "select id from cust.customer where tenant_id" in sql and "client_request_id" in sql:
            crid = UUID(params["crid"]) if params.get("crid") else None
            hit = self.idempotency_hits.get(crid) if crid else None
            return _Result([(hit,)] if hit else [])
        if "insert into cust.customer" in sql:
            self.inserts.append({"sql": sql, **params})
            return _Result([])
        if "update cust.customer set" in sql:
            self.updates.append({"sql": sql, **params})
            cust_id = None
            if "id" in params:
                cust_id = UUID(params["id"])
            elif "aid" in params:
                cust_id = UUID(params["aid"])
            if cust_id and cust_id in self.customers:
                cust = self.customers[cust_id]
                # Apply field changes that the SQL would have applied.
                for k, v in params.items():
                    if k in {"id", "tid", "ts", "uid"}:
                        continue
                    if hasattr(cust, k):
                        setattr(cust, k, v)
                cust.version = (cust.version or 0) + 1
                if "state=" in sql and "s" in params:
                    cust.state = params["s"]
                if "state='anonymized'" in sql:
                    cust.state = "anonymized"
                if "state='merged'" in sql:
                    cust.state = "merged"
                    if "sid" in params:
                        cust.merged_into = UUID(params["sid"])
            return _Result([])
        if "insert into cust.profile_change" in sql:
            self.profile_changes.append(params)
            return _Result([])
        if "insert into cust.merge" in sql:
            self.merges.append(params)
            return _Result([])
        if sql.startswith("update ret.") or sql.startswith("update sales.") or sql.startswith("update svc."):
            table = sql.split("update ", 1)[1].split(" ", 1)[0]
            self.rewrites.append((table, params))
            return _Result([])
        if "select to_regclass" in sql:
            t = params.get("t", "")
            return _Result([(t if t in self.optional_tables else None,)])
        if "select * from cust.customer_address" in sql:
            return _Result([])
        if "select merged_into from cust.customer" in sql:
            cid = UUID(params["id"]) if params.get("id") else None
            cust = self.customers.get(cid) if cid else None
            return _Result([(cust.merged_into,)] if cust else [])
        raise AssertionError(f"unexpected sql: {sql[:200]}")

    def get(self, model, key):  # noqa: ANN001
        if model is Customer:
            return self.customers.get(key if isinstance(key, UUID) else UUID(str(key)))
        return None

    def refresh(self, obj):  # noqa: ANN001
        return None

    def commit(self):  # noqa: ANN001
        return None


def _seed(sess: FakeWriteSession, **overrides) -> Customer:
    cid = overrides.pop("id", uuid4())
    now = datetime.now(timezone.utc)
    base: dict[str, Any] = {
        "id": cid,
        "tenant_id": uuid4(),
        "client_request_id": None,
        "external_loyalty_id": None,
        "external_crm_id": None,
        "contact_type": "individual",
        "first_name": "A",
        "last_name": "B",
        "company_name": None,
        "primary_phone": None,
        "secondary_phone": None,
        "email": "a@b.com",
        "preferred_channel": "email",
        "language": None,
        "tags": [],
        "tax_id": None,
        "date_of_birth": None,
        "state": "active",
        "merged_into": None,
        "version": 1,
        "created_at": now,
        "created_by_user_id": None,
        "updated_at": now,
        "updated_by_user_id": None,
        "phone_normalized": None,
        "email_normalized": "a@b.com",
        "display_name_lower": "a b",
        "search_vector": None,
    }
    base.update(overrides)
    cust = Customer(**base)
    sess.customers[cid] = cust
    return cust


# --- T050: optimistic concurrency ----------------------------------------------

def test_update_with_wrong_if_match_raises_stale_version():
    sess = FakeWriteSession()
    cust = _seed(sess)
    with pytest.raises(StaleVersion):
        write_service.update_customer(
            sess,  # type: ignore[arg-type]
            tenant_id=cust.tenant_id,
            customer_id=cust.id,
            actor_user_id=uuid4(),
            actor_roles=frozenset({"Cashier"}),
            expected_version=999,
            data=CustomerData(first_name="C", last_name="D", email="a@b.com"),
        )


def test_update_with_correct_if_match_bumps_version():
    sess = FakeWriteSession()
    cust = _seed(sess)
    write_service.update_customer(
        sess,  # type: ignore[arg-type]
        tenant_id=cust.tenant_id,
        customer_id=cust.id,
        actor_user_id=uuid4(),
        actor_roles=frozenset({"Cashier"}),
        expected_version=1,
        data=CustomerData(first_name="C", last_name="B", email="a@b.com"),
    )
    assert cust.version == 2


# --- T049: per-field profile_change rows ---------------------------------------

def test_update_writes_one_profile_change_per_changed_field():
    sess = FakeWriteSession()
    cust = _seed(sess)
    write_service.update_customer(
        sess,  # type: ignore[arg-type]
        tenant_id=cust.tenant_id,
        customer_id=cust.id,
        actor_user_id=uuid4(),
        actor_roles=frozenset({"Cashier"}),
        expected_version=1,
        data=CustomerData(first_name="X", last_name="Y", email="a@b.com"),
    )
    fields = sorted(p["field"] for p in sess.profile_changes)
    assert fields == ["first_name", "last_name"]


def test_sensitive_field_is_hashed_in_audit():
    sess = FakeWriteSession()
    cust = _seed(sess)
    write_service.update_customer(
        sess,  # type: ignore[arg-type]
        tenant_id=cust.tenant_id,
        customer_id=cust.id,
        actor_user_id=uuid4(),
        actor_roles=frozenset({"Store Manager"}),
        expected_version=1,
        data=CustomerData(
            first_name="A", last_name="B", email="a@b.com", tax_id="123-45-6789"
        ),
    )
    tax = next(p for p in sess.profile_changes if p["field"] == "tax_id")
    assert tax["nv"].startswith("sha256:")
    assert tax["nv"].endswith("last4=6789")


# --- T052: RBAC for sensitive fields ------------------------------------------

def test_cashier_cannot_set_tax_id():
    sess = FakeWriteSession()
    cust = _seed(sess)
    with pytest.raises(RoleForbidden):
        write_service.update_customer(
            sess,  # type: ignore[arg-type]
            tenant_id=cust.tenant_id,
            customer_id=cust.id,
            actor_user_id=uuid4(),
            actor_roles=frozenset({"Cashier"}),
            expected_version=1,
            data=CustomerData(first_name="A", last_name="B", email="a@b.com", tax_id="999"),
        )


def test_manager_can_set_tax_id():
    sess = FakeWriteSession()
    cust = _seed(sess)
    write_service.update_customer(
        sess,  # type: ignore[arg-type]
        tenant_id=cust.tenant_id,
        customer_id=cust.id,
        actor_user_id=uuid4(),
        actor_roles=frozenset({"Store Manager"}),
        expected_version=1,
        data=CustomerData(first_name="A", last_name="B", email="a@b.com", tax_id="999"),
    )
    assert cust.tax_id == "999"


# --- T051: merge -------------------------------------------------------------

def test_merge_rewrites_known_table_and_marks_state():
    sess = FakeWriteSession()
    survivor = _seed(sess)
    away = _seed(sess, email="b@b.com")
    write_service.merge_customers(
        sess,  # type: ignore[arg-type]
        tenant_id=survivor.tenant_id,
        survivor_id=survivor.id,
        merged_away_id=away.id,
        actor_user_id=uuid4(),
        summary="duplicate",
    )
    assert away.state == "merged"
    assert away.merged_into == survivor.id
    rewritten_tables = [t for t, _ in sess.rewrites]
    assert "ret.customer_return" in rewritten_tables
    assert any(p["field"] == "merged_into" for p in sess.profile_changes)


def test_merge_rejects_self_merge():
    sess = FakeWriteSession()
    cust = _seed(sess)
    with pytest.raises(BusinessRuleConflict):
        write_service.merge_customers(
            sess,  # type: ignore[arg-type]
            tenant_id=cust.tenant_id,
            survivor_id=cust.id,
            merged_away_id=cust.id,
            actor_user_id=uuid4(),
        )


def test_merge_rejects_double_merge():
    sess = FakeWriteSession()
    survivor = _seed(sess)
    away = _seed(sess, state="merged", merged_into=uuid4())
    with pytest.raises(BusinessRuleConflict):
        write_service.merge_customers(
            sess,  # type: ignore[arg-type]
            tenant_id=survivor.tenant_id,
            survivor_id=survivor.id,
            merged_away_id=away.id,
            actor_user_id=uuid4(),
        )


def test_resolve_customer_id_follows_chain():
    sess = FakeWriteSession()
    final = _seed(sess)
    mid = _seed(sess, merged_into=final.id, state="merged")
    start = _seed(sess, merged_into=mid.id, state="merged")
    resolved = write_service.resolve_customer_id(
        sess,  # type: ignore[arg-type]
        tenant_id=start.tenant_id,
        customer_id=start.id,
    )
    assert resolved == final.id


# --- create / lifecycle ------------------------------------------------------

def test_create_idempotent_replays_existing_row():
    sess = FakeWriteSession()
    crid = uuid4()
    pre_existing = _seed(sess)
    sess.idempotency_hits[crid] = pre_existing.id
    cust = write_service.create_customer(
        sess,  # type: ignore[arg-type]
        tenant_id=pre_existing.tenant_id,
        actor_user_id=uuid4(),
        actor_roles=frozenset({"Cashier"}),
        data=CustomerData(
            first_name="A", last_name="B", email="a@b.com", client_request_id=crid
        ),
    )
    assert cust.id == pre_existing.id
    # No INSERT was issued because the idempotent SELECT short-circuited
    assert not sess.inserts


def test_anonymize_clears_pii_and_sets_state():
    sess = FakeWriteSession()
    cust = _seed(sess, tax_id="111-22-3333")
    write_service.anonymize_customer(
        sess,  # type: ignore[arg-type]
        tenant_id=cust.tenant_id,
        customer_id=cust.id,
        actor_user_id=uuid4(),
    )
    assert cust.state == "anonymized"
    audit = next(p for p in sess.profile_changes if p["ck"] == "anonymize")
    assert audit["field"] == "state"
