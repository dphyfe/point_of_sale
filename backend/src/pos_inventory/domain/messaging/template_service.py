"""Template service (T073) — minimal CRUD wrapping `msg.template`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.errors import BusinessRuleConflict, NotFound


@dataclass(frozen=True)
class TemplateData:
    code: str
    name: str
    channel: str
    purpose: str
    body_template: str
    subject_template: str | None = None
    enabled: bool = True


def list_templates(sess: Session, *, tenant_id: UUID, channel: str | None = None) -> list[dict]:
    sql = (
        "SELECT id, code, name, channel, purpose, subject_template, body_template, enabled, "
        "       created_at, updated_at "
        "  FROM msg.template WHERE tenant_id = :tid"
    )
    params: dict[str, object] = {"tid": str(tenant_id)}
    if channel:
        sql += " AND channel = :ch"
        params["ch"] = channel
    sql += " ORDER BY code"
    rows = sess.execute(text(sql), params).all()
    return [
        {
            "id": r[0], "code": r[1], "name": r[2], "channel": r[3], "purpose": r[4],
            "subject_template": r[5], "body_template": r[6], "enabled": r[7],
            "created_at": r[8], "updated_at": r[9],
        }
        for r in rows
    ]


def create_template(sess: Session, *, tenant_id: UUID, data: TemplateData) -> UUID:
    if data.channel == "email" and not data.subject_template:
        raise BusinessRuleConflict("email templates require subject_template")
    tid = uuid4()
    now = datetime.now(timezone.utc)
    sess.execute(
        text(
            """
            INSERT INTO msg.template
              (id, tenant_id, code, name, channel, purpose, subject_template, body_template,
               enabled, created_at, updated_at)
            VALUES (:id, :tid, :code, :nm, :ch, :pu, :st, :bt, :en, :ts, :ts)
            ON CONFLICT (tenant_id, code) DO NOTHING
            """
        ),
        {
            "id": str(tid), "tid": str(tenant_id), "code": data.code, "nm": data.name,
            "ch": data.channel, "pu": data.purpose, "st": data.subject_template,
            "bt": data.body_template, "en": data.enabled, "ts": now,
        },
    )
    row = sess.execute(
        text("SELECT id FROM msg.template WHERE tenant_id=:tid AND code=:code"),
        {"tid": str(tenant_id), "code": data.code},
    ).first()
    if row is None:
        raise NotFound("template insert failed")
    return UUID(str(row[0]))


def update_template(sess: Session, *, tenant_id: UUID, template_id: UUID, data: TemplateData) -> None:
    now = datetime.now(timezone.utc)
    res = sess.execute(
        text(
            """
            UPDATE msg.template
               SET name=:nm, channel=:ch, purpose=:pu, subject_template=:st,
                   body_template=:bt, enabled=:en, updated_at=:ts
             WHERE tenant_id=:tid AND id=:id
            """
        ),
        {
            "tid": str(tenant_id), "id": str(template_id), "nm": data.name, "ch": data.channel,
            "pu": data.purpose, "st": data.subject_template, "bt": data.body_template,
            "en": data.enabled, "ts": now,
        },
    )
    if res.rowcount == 0:
        raise NotFound(f"template {template_id}")
