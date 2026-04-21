"""Send / retry service for outbound customer messages (T059, T060).

* `send_message()` is idempotent on (tenant_id, client_request_id).
* Inserts `msg.message`, an initial `msg.message_status_event(status='queued')`,
  and a `msg.outbox(event_kind='customer_message.send')` row inside the same
  transaction (outbox pattern).
* `retry_message()` is allowed only for messages whose latest status is
  ``failed`` or ``bounced``; emits a ``customer_message.retry`` outbox row and a
  ``retrying`` status event.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.errors import BusinessRuleConflict, NotFound
from pos_inventory.domain.consent.gate import assert_allowed
from pos_inventory.domain.messaging.render import render_template


@dataclass(frozen=True)
class SendRequest:
    customer_id: UUID
    template_code: str | None
    channel: str  # "email" | "sms"
    purpose: str  # "transactional" | "marketing"
    to_address: str
    free_text_subject: str | None = None
    free_text_body: str | None = None
    related_transaction_id: UUID | None = None
    related_transaction_kind: str | None = None
    context: dict | None = None
    client_request_id: UUID | None = None
    sent_by_user_id: UUID | None = None


def _load_template(sess: Session, *, tenant_id: UUID, code: str) -> tuple[UUID, str | None, str, str, str]:
    row = sess.execute(
        text(
            """
            SELECT id, subject_template, body_template, channel, purpose
              FROM msg.template
             WHERE tenant_id = :tid AND code = :c AND enabled = true
            """
        ),
        {"tid": str(tenant_id), "c": code},
    ).first()
    if row is None:
        raise NotFound(f"template not found: {code}")
    return (UUID(str(row[0])), row[1], row[2], str(row[3]), str(row[4]))


def _existing_by_crid(sess: Session, *, tenant_id: UUID, crid: UUID) -> UUID | None:
    row = sess.execute(
        text(
            """
            SELECT id FROM msg.message
             WHERE tenant_id = :tid AND client_request_id = :crid
            """
        ),
        {"tid": str(tenant_id), "crid": str(crid)},
    ).first()
    return UUID(str(row[0])) if row else None


def send_message(sess: Session, *, tenant_id: UUID, req: SendRequest) -> UUID:
    if req.client_request_id and (existing := _existing_by_crid(sess, tenant_id=tenant_id, crid=req.client_request_id)):
        return existing

    template_id: UUID | None = None
    subject_tpl: str | None = req.free_text_subject
    body_tpl: str | None = req.free_text_body
    channel = req.channel
    purpose = req.purpose

    if req.template_code:
        template_id, subject_tpl, body_tpl, channel, purpose = _load_template(
            sess, tenant_id=tenant_id, code=req.template_code
        )

    if not body_tpl:
        raise BusinessRuleConflict("body required (template or free-text)")

    assert_allowed(sess, customer_id=req.customer_id, channel=channel, purpose=purpose)

    rendered = render_template(
        channel=channel,
        subject_template=subject_tpl,
        body_template=body_tpl,
        context=req.context or {},
    )

    message_id = uuid4()
    now = datetime.now(timezone.utc)
    sess.execute(
        text(
            """
            INSERT INTO msg.message
                (id, tenant_id, client_request_id, customer_id, template_id, channel, purpose,
                 to_address, subject, body, related_transaction_id, related_transaction_kind,
                 status, sent_by_user_id, created_at, updated_at)
            VALUES
                (:id, :tid, :crid, :cust, :tpl, :ch, :pu, :to, :subj, :body,
                 :rtid, :rtkind, 'queued', :sender, :ts, :ts)
            """
        ),
        {
            "id": str(message_id),
            "tid": str(tenant_id),
            "crid": str(req.client_request_id) if req.client_request_id else None,
            "cust": str(req.customer_id),
            "tpl": str(template_id) if template_id else None,
            "ch": channel,
            "pu": purpose,
            "to": req.to_address,
            "subj": rendered.subject,
            "body": rendered.body,
            "rtid": str(req.related_transaction_id) if req.related_transaction_id else None,
            "rtkind": req.related_transaction_kind,
            "sender": str(req.sent_by_user_id) if req.sent_by_user_id else None,
            "ts": now,
        },
    )
    sess.execute(
        text(
            """
            INSERT INTO msg.message_status_event
                (id, tenant_id, message_id, status, occurred_at)
            VALUES (:id, :tid, :mid, 'queued', :ts)
            """
        ),
        {"id": str(uuid4()), "tid": str(tenant_id), "mid": str(message_id), "ts": now},
    )
    sess.execute(
        text(
            """
            INSERT INTO msg.outbox
                (id, tenant_id, event_kind, payload, created_at, attempts)
            VALUES (:id, :tid, 'customer_message.send', CAST(:p AS JSONB), :ts, 0)
            """
        ),
        {
            "id": str(uuid4()),
            "tid": str(tenant_id),
            "p": json.dumps({"message_id": str(message_id)}),
            "ts": now,
        },
    )
    return message_id


def retry_message(sess: Session, *, tenant_id: UUID, message_id: UUID) -> None:
    row = sess.execute(
        text("SELECT status FROM msg.message WHERE tenant_id = :tid AND id = :mid"),
        {"tid": str(tenant_id), "mid": str(message_id)},
    ).first()
    if row is None:
        raise NotFound(f"message {message_id}")
    if row[0] not in {"failed", "bounced"}:
        raise BusinessRuleConflict(f"cannot retry message in status {row[0]}")

    now = datetime.now(timezone.utc)
    sess.execute(
        text(
            """
            INSERT INTO msg.message_status_event
                (id, tenant_id, message_id, status, occurred_at)
            VALUES (:id, :tid, :mid, 'retrying', :ts)
            """
        ),
        {"id": str(uuid4()), "tid": str(tenant_id), "mid": str(message_id), "ts": now},
    )
    sess.execute(
        text("UPDATE msg.message SET status='retrying', updated_at=:ts WHERE id=:mid"),
        {"mid": str(message_id), "ts": now},
    )
    sess.execute(
        text(
            """
            INSERT INTO msg.outbox
                (id, tenant_id, event_kind, payload, created_at, attempts)
            VALUES (:id, :tid, 'customer_message.retry', CAST(:p AS JSONB), :ts, 0)
            """
        ),
        {
            "id": str(uuid4()),
            "tid": str(tenant_id),
            "p": json.dumps({"message_id": str(message_id)}),
            "ts": now,
        },
    )
