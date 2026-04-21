"""Customer messages API (T064, T065)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.auth import Principal, get_principal, requires_role
from pos_inventory.core.tenancy import tenant_session
from pos_inventory.domain.messaging import callbacks as cb
from pos_inventory.domain.messaging.service import SendRequest, retry_message, send_message

log = logging.getLogger(__name__)

router = APIRouter(tags=["customer-messages"])

_SEND_ROLES = ("Cashier", "Customer Service", "Store Manager", "Marketing")
_READ_ROLES = ("Cashier", "Customer Service", "Store Manager", "Marketing")


class SendMessageIn(BaseModel):
    template_code: str | None = None
    channel: str = Field(..., pattern="^(email|sms)$")
    purpose: str = Field(..., pattern="^(transactional|marketing)$")
    to_address: str = Field(..., min_length=1, max_length=320)
    free_text_subject: str | None = None
    free_text_body: str | None = None
    related_transaction_id: UUID | None = None
    related_transaction_kind: str | None = None
    context: dict | None = None
    client_request_id: UUID | None = None


class SendMessageOut(BaseModel):
    id: UUID


class MessageOut(BaseModel):
    id: UUID
    channel: str
    purpose: str
    to_address: str
    subject: str | None
    body: str
    status: str
    provider: str | None
    provider_message_id: str | None
    related_transaction_id: UUID | None
    created_at: datetime
    updated_at: datetime


class MessageListOut(BaseModel):
    items: list[MessageOut]


@router.post(
    "/customers/{customer_id}/messages",
    response_model=SendMessageOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(requires_role(*_SEND_ROLES))],
)
def send_customer_message(
    customer_id: UUID,
    payload: SendMessageIn,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> SendMessageOut:
    req = SendRequest(
        customer_id=customer_id,
        template_code=payload.template_code,
        channel=payload.channel,
        purpose=payload.purpose,
        to_address=payload.to_address,
        free_text_subject=payload.free_text_subject,
        free_text_body=payload.free_text_body,
        related_transaction_id=payload.related_transaction_id,
        related_transaction_kind=payload.related_transaction_kind,
        context=payload.context,
        client_request_id=payload.client_request_id,
        sent_by_user_id=principal.user_id,
    )
    mid = send_message(sess, tenant_id=principal.tenant_id, req=req)
    sess.commit()
    return SendMessageOut(id=mid)


@router.get(
    "/customers/{customer_id}/messages",
    response_model=MessageListOut,
    dependencies=[Depends(requires_role(*_READ_ROLES))],
)
def list_customer_messages(
    customer_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> MessageListOut:
    rows = sess.execute(
        text(
            """
            SELECT id, channel, purpose, to_address, subject, body, status, provider,
                   provider_message_id, related_transaction_id, created_at, updated_at
              FROM msg.message
             WHERE tenant_id=:tid AND customer_id=:cid
             ORDER BY created_at DESC
             LIMIT :lim OFFSET :off
            """
        ),
        {"tid": str(principal.tenant_id), "cid": str(customer_id), "lim": limit, "off": offset},
    ).all()
    items = [
        MessageOut(
            id=r[0], channel=r[1], purpose=r[2], to_address=r[3], subject=r[4], body=r[5],
            status=r[6], provider=r[7], provider_message_id=r[8],
            related_transaction_id=r[9], created_at=r[10], updated_at=r[11],
        )
        for r in rows
    ]
    return MessageListOut(items=items)


@router.post(
    "/customer-messages/{message_id}/retry",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(requires_role("Cashier", "Customer Service", "Store Manager"))],
)
def retry_customer_message(
    message_id: UUID,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> None:
    retry_message(sess, tenant_id=principal.tenant_id, message_id=message_id)
    sess.commit()


@router.post(
    "/customer-messages/callbacks/{provider}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def provider_callback(
    provider: str,
    request: Request,
    x_signature: str = Header(..., alias="X-Signature"),
) -> None:
    """Provider webhook — HMAC-verified, intentionally outside JWT auth."""
    body = await request.body()
    secret = os.environ.get("POS_MSG_CALLBACK_SECRET", "")
    try:
        cb.verify(body=body, signature=x_signature, secret=secret)
        parsed = cb.parse_raw(provider=provider, body=body)
    except cb.CallbackVerificationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    from pos_inventory.core.db import session_factory

    sf = session_factory()
    with sf() as sess:
        row = sess.execute(
            text("SELECT id, tenant_id FROM msg.message WHERE provider_message_id = :pmid"),
            {"pmid": parsed.provider_message_id},
        ).first()
        if row is None:
            log.warning("callback for unknown provider_message_id=%s", parsed.provider_message_id)
            return
        message_id, tenant_id = row
        sess.execute(
            text("SELECT set_config('app.current_tenant', :tid, false)"),
            {"tid": str(tenant_id)},
        )
        now = datetime.now(timezone.utc)
        sess.execute(
            text(
                """
                INSERT INTO msg.message_status_event
                    (id, tenant_id, message_id, status, occurred_at,
                     provider_event_id, error_code, error_message)
                VALUES (:id, :tid, :mid, :st, :ts, :pev, :ec, :em)
                """
            ),
            {
                "id": str(uuid4()), "tid": str(tenant_id), "mid": str(message_id),
                "st": parsed.status, "ts": now,
                "pev": parsed.provider_event_id,
                "ec": parsed.error_code, "em": parsed.error_message,
            },
        )
        sess.execute(
            text("UPDATE msg.message SET status=:st, updated_at=:ts WHERE id=:mid"),
            {"st": parsed.status, "ts": now, "mid": str(message_id)},
        )
        # T076: provider-driven unsubscribe → record consent.opt_out for this channel.
        if parsed.status == "unsubscribed":
            from pos_inventory.domain.consent.service import ConsentEventInput, record_event

            crow = sess.execute(
                text("SELECT customer_id, channel FROM msg.message WHERE id=:mid"),
                {"mid": str(message_id)},
            ).first()
            if crow is not None:
                record_event(
                    sess,
                    tenant_id=tenant_id,
                    ev=ConsentEventInput(
                        customer_id=crow[0],
                        channel=str(crow[1]),
                        purpose="marketing",
                        event_kind="unsubscribe",
                        source="provider",
                        note=f"provider={provider} event={parsed.provider_event_id}",
                    ),
                )
        sess.commit()
