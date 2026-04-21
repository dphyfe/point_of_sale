"""Outbox worker: at-least-once delivery of `outbox.event` rows to the
configured tenant webhook (FR-007).

Polls in a loop, claims a batch via SELECT ... FOR UPDATE SKIP LOCKED, POSTs
each event, and either marks `delivered_at` on success or increments
`attempt_count` + sets `next_attempt_at` on failure (exponential backoff).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.config import get_settings
from pos_inventory.core.db import get_engine
from pos_inventory.domain.messaging.provider import MessagingProvider, get_provider

log = logging.getLogger("outbox_worker")

BATCH = 50
POLL_SECONDS = 2


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(300, 5 * (2 ** min(attempts, 6))))


def _process_batch(sess: Session, client: httpx.Client, webhook_url: str) -> int:
    rows = sess.execute(
        text(
            """
            SELECT id, tenant_id, event_type, occurred_at, payload, attempt_count
              FROM outbox.event
             WHERE delivered_at IS NULL
               AND (next_attempt_at IS NULL OR next_attempt_at <= NOW())
             ORDER BY occurred_at
             FOR UPDATE SKIP LOCKED
             LIMIT :n
            """
        ),
        {"n": BATCH},
    ).all()

    n_ok = 0
    for ev_id, tenant_id, ev_type, occurred_at, payload, attempts in rows:
        body = {
            "event_id": str(ev_id),
            "tenant_id": str(tenant_id),
            "event_type": ev_type,
            "occurred_at": occurred_at.isoformat() if occurred_at else None,
            "payload": payload,
        }
        try:
            r = client.post(webhook_url, json=body, timeout=10.0)
            r.raise_for_status()
            sess.execute(
                text("UPDATE outbox.event SET delivered_at = NOW() WHERE id = :id"),
                {"id": str(ev_id)},
            )
            n_ok += 1
        except Exception as exc:  # noqa: BLE001
            next_at = datetime.now(timezone.utc) + _backoff(attempts or 0)
            sess.execute(
                text(
                    """
                    UPDATE outbox.event
                       SET attempt_count = COALESCE(attempt_count, 0) + 1,
                           last_error = :err,
                           next_attempt_at = :nxt
                     WHERE id = :id
                    """
                ),
                {"err": str(exc)[:500], "nxt": next_at, "id": str(ev_id)},
            )
            log.warning("outbox delivery failed id=%s err=%s", ev_id, exc)

    sess.commit()
    return n_ok


def _process_msg_outbox(sess: Session, provider: MessagingProvider) -> int:
    """Drain ``msg.outbox`` rows for ``customer_message.send`` /
    ``customer_message.retry`` events (T063). Calls the configured
    :class:`MessagingProvider` and writes a status event row. Tenant scoping is
    enforced by setting `app.current_tenant` per-row before any state mutation.
    """
    rows = sess.execute(
        text(
            """
            SELECT id, tenant_id, event_kind, payload, attempts
              FROM msg.outbox
             WHERE dispatched_at IS NULL
               AND event_kind IN ('customer_message.send', 'customer_message.retry')
             ORDER BY created_at
             FOR UPDATE SKIP LOCKED
             LIMIT :n
            """
        ),
        {"n": BATCH},
    ).all()

    n_ok = 0
    for ob_id, tenant_id, _kind, payload, attempts in rows:
        try:
            sess.execute(
                text("SELECT set_config('app.current_tenant', :tid, true)"),
                {"tid": str(tenant_id)},
            )
            message_id = (payload or {}).get("message_id")
            if not message_id:
                raise ValueError("missing message_id")
            row = sess.execute(
                text(
                    """
                    SELECT channel, to_address, subject, body
                      FROM msg.message WHERE id = :mid AND tenant_id = :tid
                    """
                ),
                {"mid": message_id, "tid": str(tenant_id)},
            ).first()
            if row is None:
                raise ValueError(f"message {message_id} missing")
            result = provider.send(channel=row[0], to_address=row[1], subject=row[2], body=row[3])
            now = datetime.now(timezone.utc)
            new_status = "sent" if result.accepted else "failed"
            sess.execute(
                text(
                    """
                    UPDATE msg.message
                       SET status = :st, provider = :prov, provider_message_id = :pmid, updated_at = :ts
                     WHERE id = :mid
                    """
                ),
                {
                    "st": new_status,
                    "prov": provider.name,
                    "pmid": result.provider_message_id,
                    "ts": now,
                    "mid": message_id,
                },
            )
            sess.execute(
                text(
                    """
                    INSERT INTO msg.message_status_event
                        (id, tenant_id, message_id, status, occurred_at, error_message)
                    VALUES (:id, :tid, :mid, :st, :ts, :err)
                    """
                ),
                {
                    "id": str(uuid4()),
                    "tid": str(tenant_id),
                    "mid": message_id,
                    "st": new_status,
                    "ts": now,
                    "err": result.error,
                },
            )
            sess.execute(
                text(
                    "UPDATE msg.outbox SET dispatched_at=:ts, attempts=:a WHERE id=:id"
                ),
                {"ts": now, "a": (attempts or 0) + 1, "id": str(ob_id)},
            )
            n_ok += 1
        except Exception as exc:  # noqa: BLE001
            sess.execute(
                text(
                    """
                    UPDATE msg.outbox
                       SET attempts = COALESCE(attempts,0)+1,
                           last_error = :err
                     WHERE id = :id
                    """
                ),
                {"err": str(exc)[:500], "id": str(ob_id)},
            )
            log.warning("msg.outbox dispatch failed id=%s err=%s", ob_id, exc)
    sess.commit()
    return n_ok


def run_forever() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    webhook_url = getattr(settings, "outbox_webhook_url", None) or "http://localhost:9999/webhook"
    engine = get_engine()
    log.info("outbox worker starting; target=%s", webhook_url)
    provider = get_provider()
    with httpx.Client() as client:
        while True:
            try:
                with Session(engine) as sess:
                    n = _process_batch(sess, client, webhook_url)
                    if n:
                        log.info("delivered %d events", n)
                    m = _process_msg_outbox(sess, provider)
                    if m:
                        log.info("dispatched %d customer messages", m)
            except Exception as exc:  # noqa: BLE001
                log.exception("worker loop error: %s", exc)
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    run_forever()
