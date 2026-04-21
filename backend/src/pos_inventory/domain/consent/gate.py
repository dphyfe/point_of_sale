"""Consent gate (T058).

Reads `consent.state` for `(customer, channel, purpose)` and applies
FR-030 default rule:

* `transactional` purposes default to ``allow`` when no row exists.
* `marketing` purposes default to ``block`` when not explicitly opted in.

Raises :class:`ConsentRequired` when the message is blocked. Service-layer
callers should treat this as 403.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.errors import BusinessRuleConflict


class ConsentRequired(BusinessRuleConflict):
    code = "consent_required"
    http_status = 403

    def __init__(self, *, channel: str, purpose: str) -> None:
        super().__init__(f"consent_required for {channel}/{purpose}")


def _load_state(sess: Session, *, customer_id: UUID, channel: str, purpose: str) -> str | None:
    row = sess.execute(
        text(
            """
            SELECT state FROM consent.state
             WHERE customer_id = :cid AND channel = :ch AND purpose = :pu
            """
        ),
        {"cid": str(customer_id), "ch": channel, "pu": purpose},
    ).first()
    return None if row is None else str(row[0])


def assert_allowed(sess: Session, *, customer_id: UUID, channel: str, purpose: str) -> None:
    state = _load_state(sess, customer_id=customer_id, channel=channel, purpose=purpose)
    if purpose == "transactional":
        if state == "opted_out":
            raise ConsentRequired(channel=channel, purpose=purpose)
        return
    # Marketing / promotional -> require explicit opt-in.
    if state != "opted_in":
        raise ConsentRequired(channel=channel, purpose=purpose)
