"""Optimistic concurrency check (R5).

Callers compare the client-supplied `If-Match` version against the persisted
row version and raise on mismatch.
"""

from __future__ import annotations

from pos_inventory.core.errors import DomainError


class StaleVersion(DomainError):
    code = "stale_version"
    http_status = 409


def check_if_match(expected_version: int, actual_version: int) -> None:
    if expected_version != actual_version:
        raise StaleVersion(
            f"stale_version: expected {expected_version}, found {actual_version}"
        )
