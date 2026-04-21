"""Unit tests for core/auth role gating (no DB required)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from pos_inventory.core.auth import CANONICAL_ROLES, Principal, requires_role


def _principal(*roles: str) -> Principal:
    return Principal(user_id=uuid4(), tenant_id=uuid4(), roles=frozenset(roles))


def test_canonical_role_set_matches_spec():
    assert CANONICAL_ROLES == {
        "Cashier",
        "Receiver",
        "Inventory Clerk",
        "Store Manager",
        "Purchasing",
        "Admin",
    }


def test_requires_role_passes_when_principal_has_role():
    dep = requires_role("Receiver")
    p = _principal("Receiver")
    assert dep(p) is p


def test_admin_can_pass_any_role_check():
    dep = requires_role("Store Manager")
    p = _principal("Admin")
    assert dep(p) is p


def test_requires_role_rejects_when_missing():
    dep = requires_role("Purchasing")
    with pytest.raises(Exception) as exc:  # RoleForbidden
        dep(_principal("Cashier"))
    assert "Purchasing" in str(exc.value)


def test_requires_role_rejects_non_canonical_at_definition_time():
    with pytest.raises(AssertionError):
        requires_role("SuperUser")  # type: ignore[arg-type]
