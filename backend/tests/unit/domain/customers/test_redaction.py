"""Unit tests for redaction helper (FR-011, R6)."""

from __future__ import annotations

from pos_inventory.domain.customers.redaction import hash_with_last4


def test_hash_with_last4_format() -> None:
    out = hash_with_last4("jane@example.com")
    assert out is not None
    assert out.startswith("sha256:")
    assert out.endswith(":last4=.com")


def test_hash_with_last4_short_value() -> None:
    out = hash_with_last4("ab")
    assert out is not None
    assert out.endswith(":last4=ab")


def test_hash_with_last4_none() -> None:
    assert hash_with_last4(None) is None
