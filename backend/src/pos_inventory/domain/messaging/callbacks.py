"""Provider-callback verification & parsing (T062).

The HMAC scheme is shared across providers: HMAC-SHA256 over the raw request
body, hex-encoded; the signature header convention is documented per provider.
This module does NOT touch the database; callers persist the resulting
``MessageStatusEvent`` rows themselves.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ParsedCallback:
    provider_message_id: str
    status: str
    error_code: str | None
    error_message: str | None
    provider_event_id: str | None


class CallbackVerificationError(Exception):
    pass


def verify(*, body: bytes, signature: str, secret: str) -> None:
    if not signature or not secret:
        raise CallbackVerificationError("missing signature or secret")
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.strip()):
        raise CallbackVerificationError("signature mismatch")


_STATUS_MAP = {
    # Generic
    "delivered": "delivered",
    "failed": "failed",
    "bounced": "bounced",
    "opened": "opened",
    "clicked": "clicked",
    "unsubscribed": "unsubscribed",
}


def parse(*, provider: str, payload: dict[str, Any]) -> ParsedCallback:
    """Normalize a provider payload into our internal status event shape.

    Providers vary; we accept either ``{"messageId":..,"status":..}`` or a
    SendGrid-like ``{"sg_message_id":..,"event":..}`` shape.
    """
    pmid = (
        payload.get("provider_message_id")
        or payload.get("messageId")
        or payload.get("sg_message_id")
        or payload.get("MessageId")
    )
    raw_status = (payload.get("status") or payload.get("event") or "").lower()
    status = _STATUS_MAP.get(raw_status)
    if pmid is None or status is None:
        raise CallbackVerificationError(f"unrecognized {provider} payload")
    return ParsedCallback(
        provider_message_id=str(pmid),
        status=status,
        error_code=payload.get("error_code") or payload.get("reason"),
        error_message=payload.get("error_message") or payload.get("description"),
        provider_event_id=payload.get("event_id") or payload.get("sg_event_id"),
    )


def parse_raw(*, provider: str, body: bytes) -> ParsedCallback:
    return parse(provider=provider, payload=json.loads(body.decode("utf-8") or "{}"))
