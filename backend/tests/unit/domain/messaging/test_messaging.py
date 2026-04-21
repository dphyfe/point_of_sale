"""Unit tests for messaging + consent (T066-T070)."""

from __future__ import annotations

import hashlib
import hmac
import json
from uuid import uuid4

import pytest

from pos_inventory.domain.messaging.callbacks import (
    CallbackVerificationError,
    parse,
    parse_raw,
    verify,
)
from pos_inventory.domain.messaging.provider import NullProvider
from pos_inventory.domain.messaging.render import (
    UnknownMergeField,
    InvalidChannel,
    render_template,
)


# ---------- T066: render allow-listing ----------


def test_render_allows_known_fields_and_html_escapes_email() -> None:
    out = render_template(
        channel="email",
        subject_template="Hi {{customer.first_name}}",
        body_template="<p>Hello {{customer.first_name}} &amp; co</p>",
        context={"customer": {"first_name": "<Bob>"}},
    )
    assert out.subject == "Hi &lt;Bob&gt;"
    assert "&lt;Bob&gt;" in out.body


def test_render_rejects_unknown_namespace_or_field() -> None:
    with pytest.raises(UnknownMergeField):
        render_template(
            channel="sms",
            subject_template=None,
            body_template="hi {{secret.password}}",
            context={},
        )
    with pytest.raises(UnknownMergeField):
        render_template(
            channel="sms",
            subject_template=None,
            body_template="hi {{customer.password}}",
            context={"customer": {"password": "x"}},
        )


def test_render_sms_strips_control_chars_and_no_subject() -> None:
    out = render_template(
        channel="sms",
        subject_template="ignored",
        body_template="x={{customer.first_name}}",
        context={"customer": {"first_name": "Bo\x07b"}},
    )
    assert out.subject is None
    assert out.body == "x=Bob"


def test_render_invalid_channel() -> None:
    with pytest.raises(InvalidChannel):
        render_template(channel="fax", subject_template=None, body_template="x", context={})


# ---------- T067: consent enforcement ----------


class _StubSession:
    def __init__(self, state: str | None) -> None:
        self._state = state

    def execute(self, *_a, **_kw):
        class _R:
            def __init__(self, s):
                self.s = s

            def first(self):
                return None if self.s is None else (self.s,)

        return _R(self._state)


def test_consent_marketing_blocked_when_unset() -> None:
    from pos_inventory.domain.consent.gate import ConsentRequired, assert_allowed

    sess = _StubSession(None)
    with pytest.raises(ConsentRequired):
        assert_allowed(sess, customer_id=uuid4(), channel="email", purpose="marketing")  # type: ignore[arg-type]


def test_consent_transactional_allowed_when_unset() -> None:
    from pos_inventory.domain.consent.gate import assert_allowed

    sess = _StubSession(None)
    assert_allowed(sess, customer_id=uuid4(), channel="email", purpose="transactional")  # type: ignore[arg-type]


def test_consent_transactional_blocked_when_opted_out() -> None:
    from pos_inventory.domain.consent.gate import ConsentRequired, assert_allowed

    sess = _StubSession("opted_out")
    with pytest.raises(ConsentRequired):
        assert_allowed(sess, customer_id=uuid4(), channel="sms", purpose="transactional")  # type: ignore[arg-type]


# ---------- T068: callbacks (HMAC verification + parse) ----------


def test_verify_accepts_correct_hmac() -> None:
    secret = "shh"
    body = b'{"messageId":"abc","status":"delivered"}'
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    verify(body=body, signature=sig, secret=secret)  # no raise


def test_verify_rejects_wrong_hmac() -> None:
    with pytest.raises(CallbackVerificationError):
        verify(body=b"x", signature="deadbeef", secret="shh")


def test_parse_normalizes_provider_payload() -> None:
    p = parse(provider="x", payload={"sg_message_id": "abc", "event": "delivered"})
    assert p.provider_message_id == "abc" and p.status == "delivered"
    p2 = parse_raw(provider="x", body=json.dumps({"messageId": "m1", "status": "bounced"}).encode())
    assert p2.status == "bounced"


def test_parse_rejects_unknown_status() -> None:
    with pytest.raises(CallbackVerificationError):
        parse(provider="x", payload={"messageId": "m1", "status": "??"})


# ---------- T069: outbox dispatch (provider routing) ----------


def test_null_provider_accepts_send() -> None:
    r = NullProvider().send(channel="email", to_address="x@y", subject="s", body="b")
    assert r.accepted and r.provider_message_id == "null:accepted"


# ---------- T070: send_message RBAC marker ----------
# (Full HTTP RBAC is exercised against the FastAPI app in the integration suite;
# here we only assert that the role tuples in the router include the expected
# roles, which guards against accidental drift.)


def test_send_roles_include_marketing_and_cashier() -> None:
    from pos_inventory.api.v1 import customer_messages

    assert "Marketing" in customer_messages._SEND_ROLES
    assert "Cashier" in customer_messages._SEND_ROLES
