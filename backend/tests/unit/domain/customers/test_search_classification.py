"""Unit tests for customer search query classification (FR-001..FR-005)."""

from __future__ import annotations

from pos_inventory.persistence.repositories.customer_repo import _classify


def test_classify_email() -> None:
    mode, q = _classify("Jane.Doe@Example.COM")
    assert mode == "email"
    assert q == "jane.doe@example.com"


def test_classify_phone_with_punctuation() -> None:
    mode, q = _classify("(415) 555-2671")
    assert mode == "phone"
    assert q == "4155552671"


def test_classify_phone_just_digits() -> None:
    mode, q = _classify("4155552671")
    assert mode == "phone"
    assert q == "4155552671"


def test_classify_text_short_digits_is_text() -> None:
    mode, _ = _classify("12")
    assert mode == "text"


def test_classify_freeform_text() -> None:
    mode, q = _classify("Acme Corp")
    assert mode == "text"
    assert q == "Acme Corp"
