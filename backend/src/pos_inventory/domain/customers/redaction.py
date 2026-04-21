"""Audit value redaction for sensitive customer fields (FR-011, R6).

Stores `sha256:<hex>:last4=<...>` form in `cust.profile_change.{old,new}_value`
so changes are queryable without leaking PII.
"""

from __future__ import annotations

import hashlib


def hash_with_last4(value: str | None) -> str | None:
    if value is None:
        return None
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    last4 = value[-4:] if len(value) >= 4 else value
    return f"sha256:{digest}:last4={last4}"
