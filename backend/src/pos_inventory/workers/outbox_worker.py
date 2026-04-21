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

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.config import get_settings
from pos_inventory.core.db import get_engine

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


def run_forever() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    webhook_url = getattr(settings, "outbox_webhook_url", None) or "http://localhost:9999/webhook"
    engine = get_engine()
    log.info("outbox worker starting; target=%s", webhook_url)
    with httpx.Client() as client:
        while True:
            try:
                with Session(engine) as sess:
                    n = _process_batch(sess, client, webhook_url)
                    if n:
                        log.info("delivered %d events", n)
            except Exception as exc:  # noqa: BLE001
                log.exception("worker loop error: %s", exc)
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    run_forever()
