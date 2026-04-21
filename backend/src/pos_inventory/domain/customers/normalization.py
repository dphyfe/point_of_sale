"""Phone + email normalization helpers (R3, R11).

`to_e164` returns E.164 form when parseable; falls back to digits-only when not
(matches the trigger-side `phone_normalized` floor).

`normalize_email` lower-cases and strips whitespace. `validate_email_or_raise`
raises `ValidationFailed` when the address fails RFC 5322 + DNS-syntax check.
"""

from __future__ import annotations

import re

import phonenumbers
from email_validator import EmailNotValidError, validate_email

from pos_inventory.core.errors import ValidationFailed

_DIGITS_RE = re.compile(r"\D+")


def digits_only(value: str | None) -> str | None:
    if value is None:
        return None
    digits = _DIGITS_RE.sub("", value)
    return digits or None


def to_e164(value: str | None, default_region: str | None = None) -> str | None:
    """Best-effort E.164. Returns digits-only fallback when unparseable."""
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = phonenumbers.parse(raw, default_region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass
    return digits_only(raw)


def normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().lower()
    return cleaned or None


def validate_email_or_raise(value: str) -> str:
    try:
        result = validate_email(value, check_deliverability=False)
    except EmailNotValidError as e:
        raise ValidationFailed(f"invalid_email: {e}") from e
    return result.normalized
