"""Unit tests for PO state machine."""

from __future__ import annotations

import pytest

from pos_inventory.core.errors import BusinessRuleConflict, RoleForbidden
from pos_inventory.domain.purchase_orders.state import (
    TransitionRequest,
    assert_transition,
)


def _req(f: str, t: str, *roles: str) -> TransitionRequest:
    return TransitionRequest(from_state=f, to_state=t, actor_roles=frozenset(roles))


def test_draft_to_submitted_requires_purchasing() -> None:
    assert_transition(_req("draft", "submitted", "Purchasing"))


def test_draft_to_submitted_denies_cashier() -> None:
    with pytest.raises(RoleForbidden):
        assert_transition(_req("draft", "submitted", "Cashier"))


def test_admin_overrides_role_pin() -> None:
    assert_transition(_req("submitted", "approved", "Admin"))


def test_submitted_to_approved_store_manager_or_purchasing() -> None:
    assert_transition(_req("submitted", "approved", "Store Manager"))
    assert_transition(_req("submitted", "approved", "Purchasing"))
    with pytest.raises(RoleForbidden):
        assert_transition(_req("submitted", "approved", "Receiver"))


def test_illegal_transition_blocked() -> None:
    with pytest.raises(BusinessRuleConflict):
        assert_transition(_req("draft", "approved", "Admin"))
    with pytest.raises(BusinessRuleConflict):
        assert_transition(_req("closed", "cancelled", "Admin"))


def test_cancellation_allowed_from_open_states() -> None:
    for s in ("draft", "submitted", "approved", "sent"):
        assert_transition(_req(s, "cancelled", "Purchasing"))


def test_sent_to_receiving_requires_receiver_or_clerk() -> None:
    assert_transition(_req("sent", "receiving", "Receiver"))
    assert_transition(_req("sent", "receiving", "Inventory Clerk"))
    with pytest.raises(RoleForbidden):
        assert_transition(_req("sent", "receiving", "Cashier"))
