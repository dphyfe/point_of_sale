"""Unit tests for optimistic concurrency check (R5)."""

from __future__ import annotations

import pytest

from pos_inventory.domain.customers.concurrency import StaleVersion, check_if_match


def test_check_if_match_passes_when_equal() -> None:
    check_if_match(3, 3)


def test_check_if_match_raises_on_mismatch() -> None:
    with pytest.raises(StaleVersion) as exc:
        check_if_match(2, 5)
    assert exc.value.code == "stale_version"
    assert exc.value.http_status == 409
