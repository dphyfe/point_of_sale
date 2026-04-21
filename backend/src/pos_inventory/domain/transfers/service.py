"""Transfer service: draft → shipped → received with virtual_in_transit pivot
(FR-027/028/029, SC-008).

Ship flow (per line):
  outbound from source → inbound to virtual_in_transit
  serialized: each serial moves to virtual_in_transit, state='in_transit'
Receive flow (per line):
  outbound from virtual_in_transit → inbound to destination
  serialized: each serial moves to destination, state='sellable'
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.audit import write_audit
from pos_inventory.core.errors import BusinessRuleConflict, NotFound, ValidationFailed
from pos_inventory.core.events import emit_event
from pos_inventory.domain.inventory.ledger import post_movement
from pos_inventory.domain.locations.service import get_or_create_in_transit


@dataclass(frozen=True)
class TransferLineInput:
    sku_id: UUID
    qty: Decimal
    serial_ids: list[UUID] | None = None  # required for serialized SKUs


@dataclass(frozen=True)
class TransferInput:
    source_location_id: UUID
    destination_location_id: UUID
    lines: list[TransferLineInput]


def create_transfer(sess: Session, *, tenant_id: UUID, actor_user_id: UUID, input: TransferInput) -> UUID:
    if not input.lines:
        raise ValidationFailed("at least one transfer line required")
    if input.source_location_id == input.destination_location_id:
        raise ValidationFailed("source and destination must differ")

    tid = uuid4()
    sess.execute(
        text(
            """
            INSERT INTO xfr.transfer
                (id, tenant_id, source_location_id, destination_location_id,
                 state, created_at, created_by)
            VALUES (:id, :tid, :src, :dst, 'draft', :ts, :uid)
            """
        ),
        {
            "id": str(tid),
            "tid": str(tenant_id),
            "src": str(input.source_location_id),
            "dst": str(input.destination_location_id),
            "ts": datetime.now(timezone.utc),
            "uid": str(actor_user_id),
        },
    )
    for line in input.lines:
        if line.qty <= 0:
            raise ValidationFailed("qty must be > 0")
        line_id = uuid4()
        sess.execute(
            text(
                """
                INSERT INTO xfr.transfer_line (id, tenant_id, transfer_id, sku_id, qty)
                VALUES (:id, :tid, :xid, :sku, :q)
                """
            ),
            {
                "id": str(line_id),
                "tid": str(tenant_id),
                "xid": str(tid),
                "sku": str(line.sku_id),
                "q": line.qty,
            },
        )
        if line.serial_ids:
            if Decimal(len(line.serial_ids)) != Decimal(line.qty):
                raise ValidationFailed("serialized line: number of serial_ids must equal qty")
            for sid in line.serial_ids:
                sess.execute(
                    text(
                        """
                        INSERT INTO xfr.transfer_serial
                            (id, tenant_id, transfer_line_id, serial_id)
                        VALUES (:id, :tid, :lid, :sid)
                        """
                    ),
                    {
                        "id": str(uuid4()),
                        "tid": str(tenant_id),
                        "lid": str(line_id),
                        "sid": str(sid),
                    },
                )

    write_audit(
        sess,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        target_kind="transfer",
        target_id=tid,
        action="created",
        after={"state": "draft", "lines": len(input.lines)},
    )
    emit_event(
        sess,
        tenant_id=tenant_id,
        event_type="transfer.created",
        payload={"transfer_id": str(tid)},
    )
    return tid


def _load_transfer(sess: Session, transfer_id: UUID) -> tuple[str, UUID, UUID]:
    row = sess.execute(
        text(
            """
            SELECT state, source_location_id, destination_location_id
              FROM xfr.transfer WHERE id = :id FOR UPDATE
            """
        ),
        {"id": str(transfer_id)},
    ).one_or_none()
    if row is None:
        raise NotFound(f"transfer {transfer_id}")
    return row[0], row[1], row[2]


def _line_rows(sess: Session, transfer_id: UUID) -> list[tuple[UUID, UUID, Decimal]]:
    return sess.execute(
        text("SELECT id, sku_id, qty FROM xfr.transfer_line WHERE transfer_id = :id"),
        {"id": str(transfer_id)},
    ).all()


def _line_serials(sess: Session, line_id: UUID) -> list[UUID]:
    rows = sess.execute(
        text("SELECT serial_id FROM xfr.transfer_serial WHERE transfer_line_id = :id"),
        {"id": str(line_id)},
    ).all()
    return [r[0] for r in rows]


def ship(sess: Session, *, tenant_id: UUID, actor_user_id: UUID, transfer_id: UUID) -> str:
    state, src, _dst = _load_transfer(sess, transfer_id)
    if state != "draft":
        raise BusinessRuleConflict(f"transfer must be draft to ship (was {state})")

    in_transit = get_or_create_in_transit(sess, tenant_id=tenant_id)
    now = datetime.now(timezone.utc)

    for line_id, sku_id, qty in _line_rows(sess, transfer_id):
        serials = _line_serials(sess, line_id)
        if serials:
            for sid in serials:
                # Outbound from source.
                post_movement(
                    sess,
                    tenant_id=tenant_id,
                    sku_id=sku_id,
                    location_id=src,
                    qty_delta=Decimal("-1"),
                    source_kind="transfer_ship",
                    source_doc_id=transfer_id,
                    serial_id=sid,
                    actor_user_id=actor_user_id,
                    occurred_at=now,
                )
                # Inbound to virtual_in_transit; serial state becomes in_transit.
                post_movement(
                    sess,
                    tenant_id=tenant_id,
                    sku_id=sku_id,
                    location_id=in_transit,
                    qty_delta=Decimal("1"),
                    source_kind="transfer_ship",
                    source_doc_id=transfer_id,
                    serial_id=sid,
                    actor_user_id=actor_user_id,
                    occurred_at=now,
                    serial_state_after="in_transit",
                )
        else:
            post_movement(
                sess,
                tenant_id=tenant_id,
                sku_id=sku_id,
                location_id=src,
                qty_delta=-Decimal(qty),
                source_kind="transfer_ship",
                source_doc_id=transfer_id,
                actor_user_id=actor_user_id,
                occurred_at=now,
            )
            post_movement(
                sess,
                tenant_id=tenant_id,
                sku_id=sku_id,
                location_id=in_transit,
                qty_delta=Decimal(qty),
                unit_cost=Decimal("0"),
                source_kind="transfer_ship",
                source_doc_id=transfer_id,
                actor_user_id=actor_user_id,
                occurred_at=now,
            )

    sess.execute(
        text("UPDATE xfr.transfer SET state = 'shipped', shipped_at = :ts WHERE id = :id"),
        {"ts": now, "id": str(transfer_id)},
    )
    write_audit(
        sess,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        target_kind="transfer",
        target_id=transfer_id,
        action="shipped",
        before={"state": "draft"},
        after={"state": "shipped"},
    )
    emit_event(
        sess,
        tenant_id=tenant_id,
        event_type="transfer.shipped",
        payload={"transfer_id": str(transfer_id)},
    )
    return "shipped"


def receive(sess: Session, *, tenant_id: UUID, actor_user_id: UUID, transfer_id: UUID) -> str:
    state, _src, dst = _load_transfer(sess, transfer_id)
    if state != "shipped":
        raise BusinessRuleConflict(f"transfer must be shipped to receive (was {state})")

    in_transit = get_or_create_in_transit(sess, tenant_id=tenant_id)
    now = datetime.now(timezone.utc)

    for line_id, sku_id, qty in _line_rows(sess, transfer_id):
        serials = _line_serials(sess, line_id)
        if serials:
            for sid in serials:
                post_movement(
                    sess,
                    tenant_id=tenant_id,
                    sku_id=sku_id,
                    location_id=in_transit,
                    qty_delta=Decimal("-1"),
                    source_kind="transfer_receive",
                    source_doc_id=transfer_id,
                    serial_id=sid,
                    actor_user_id=actor_user_id,
                    occurred_at=now,
                )
                post_movement(
                    sess,
                    tenant_id=tenant_id,
                    sku_id=sku_id,
                    location_id=dst,
                    qty_delta=Decimal("1"),
                    source_kind="transfer_receive",
                    source_doc_id=transfer_id,
                    serial_id=sid,
                    actor_user_id=actor_user_id,
                    occurred_at=now,
                    serial_state_after="sellable",
                )
        else:
            post_movement(
                sess,
                tenant_id=tenant_id,
                sku_id=sku_id,
                location_id=in_transit,
                qty_delta=-Decimal(qty),
                source_kind="transfer_receive",
                source_doc_id=transfer_id,
                actor_user_id=actor_user_id,
                occurred_at=now,
            )
            post_movement(
                sess,
                tenant_id=tenant_id,
                sku_id=sku_id,
                location_id=dst,
                qty_delta=Decimal(qty),
                unit_cost=Decimal("0"),
                source_kind="transfer_receive",
                source_doc_id=transfer_id,
                actor_user_id=actor_user_id,
                occurred_at=now,
            )

    sess.execute(
        text("UPDATE xfr.transfer SET state = 'received', received_at = :ts WHERE id = :id"),
        {"ts": now, "id": str(transfer_id)},
    )
    write_audit(
        sess,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        target_kind="transfer",
        target_id=transfer_id,
        action="received",
        before={"state": "shipped"},
        after={"state": "received"},
    )
    emit_event(
        sess,
        tenant_id=tenant_id,
        event_type="transfer.received",
        payload={"transfer_id": str(transfer_id)},
    )
    return "received"
