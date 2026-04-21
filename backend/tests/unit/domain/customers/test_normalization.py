"""Unit tests for customers normalization helpers (R3, R11)."""

from __future__ import annotations

import pytest

from pos_inventory.core.errors import ValidationFailed
from pos_inventory.domain.customers.normalization import (
    digits_only,
    normalize_email,
    to_e164,
    validate_email_or_raise,
)


def test_digits_only_strips_punctuation() -> None:
    assert digits_only("(415) 555-2671") == "4155552671"
    assert digits_only(None) is None
    assert digits_only("") is None


def test_to_e164_with_region() -> None:
    assert to_e164("(415) 555-2671", default_region="US") == "+14155552671"


def test_to_e164_unparseable_falls_back_to_digits() -> None:
    # Without a region and without a leading +, libphonenumber rejects;
    # we expect the digits-only fallback for searchability.
    assert to_e164("415 555 2671") == "4155552671"


def test_normalize_email_lowercases_and_trims() -> None:
    assert normalize_email("  Jane.Doe@Example.com ") == "jane.doe@example.com"
    assert normalize_email(None) is None


def test_validate_email_or_raise_valid() -> None:
    assert validate_email_or_raise("jane@example.com") == "jane@example.com"


def test_validate_email_or_raise_invalid() -> None:
    with pytest.raises(ValidationFailed):
        validate_email_or_raise("not-an-email")
