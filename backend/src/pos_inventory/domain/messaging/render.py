"""Template rendering with allow-listed merge fields (T057).

Channels:
  * email — body is rendered as HTML; values are HTML-escaped.
  * sms   — body is plain text; values are escaped to a printable subset.

Merge tokens use a strict ``{{namespace.field}}`` syntax. Only the
allow-listed namespaces below are accepted; unknown tokens raise
``UnknownMergeField``.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Mapping

from pos_inventory.core.errors import BusinessRuleConflict

ALLOWED_NAMESPACES: frozenset[str] = frozenset(
    {"customer", "transaction", "pickup", "business"}
)

# Allow-listed leaf fields per namespace. Anything else raises.
ALLOWED_FIELDS: dict[str, frozenset[str]] = {
    "customer": frozenset({"first_name", "last_name", "display_name", "email"}),
    "transaction": frozenset({"id", "kind", "total", "occurred_at"}),
    "pickup": frozenset({"location", "ready_at", "code"}),
    "business": frozenset({"name", "phone", "address"}),
}

_TOKEN_RE = re.compile(r"\{\{\s*([a-z_]+)\.([a-z_]+)\s*\}\}")


class UnknownMergeField(BusinessRuleConflict):
    code = "invalid_merge_field"
    http_status = 400

    def __init__(self, token: str) -> None:
        super().__init__(f"merge field not allowed: {token}")


class InvalidChannel(BusinessRuleConflict):
    code = "invalid_channel"
    http_status = 400


@dataclass(frozen=True)
class RenderedMessage:
    subject: str | None
    body: str


def _escape(value: object, channel: str) -> str:
    s = "" if value is None else str(value)
    if channel == "email":
        return html.escape(s, quote=True)
    # SMS: strip control chars; keep printable + newline + tab.
    return "".join(ch for ch in s if ch == "\n" or ch == "\t" or 0x20 <= ord(ch) < 0x7F or ord(ch) >= 0xA0)


def _resolve(token_ns: str, token_field: str, ctx: Mapping[str, Mapping[str, object]]) -> object:
    if token_ns not in ALLOWED_NAMESPACES or token_field not in ALLOWED_FIELDS[token_ns]:
        raise UnknownMergeField(f"{token_ns}.{token_field}")
    bucket = ctx.get(token_ns) or {}
    return bucket.get(token_field, "")


def render_template(
    *,
    channel: str,
    subject_template: str | None,
    body_template: str,
    context: Mapping[str, Mapping[str, object]],
) -> RenderedMessage:
    if channel not in {"email", "sms"}:
        raise InvalidChannel(f"unsupported channel {channel}")

    def repl(m: re.Match[str]) -> str:
        return _escape(_resolve(m.group(1), m.group(2), context), channel)

    rendered_body = _TOKEN_RE.sub(repl, body_template)
    rendered_subject = (
        _TOKEN_RE.sub(repl, subject_template) if (channel == "email" and subject_template) else None
    )
    return RenderedMessage(subject=rendered_subject, body=rendered_body)
