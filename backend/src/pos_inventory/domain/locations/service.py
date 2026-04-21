"""Locations service: list sites/locations and get-or-create the per-tenant
`virtual_in_transit` location used by transfer flows."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class SiteRow:
    id: UUID
    name: str
    code: str


@dataclass(frozen=True)
class LocationRow:
    id: UUID
    site_id: UUID
    name: str
    kind: str  # store_floor | back_room | virtual_in_transit | ...


def list_sites(sess: Session, *, tenant_id: UUID) -> list[SiteRow]:
    rows = sess.execute(
        text("SELECT id, name, code FROM inv.site WHERE tenant_id = :tid ORDER BY name"),
        {"tid": str(tenant_id)},
    ).all()
    return [SiteRow(id=r[0], name=r[1], code=r[2]) for r in rows]


def list_locations(sess: Session, *, tenant_id: UUID, site_id: UUID | None = None) -> list[LocationRow]:
    if site_id is not None:
        rows = sess.execute(
            text(
                """
                SELECT id, site_id, name, kind FROM inv.location
                 WHERE tenant_id = :tid AND site_id = :sid
                 ORDER BY name
                """
            ),
            {"tid": str(tenant_id), "sid": str(site_id)},
        ).all()
    else:
        rows = sess.execute(
            text("SELECT id, site_id, name, kind FROM inv.location WHERE tenant_id = :tid ORDER BY name"),
            {"tid": str(tenant_id)},
        ).all()
    return [LocationRow(id=r[0], site_id=r[1], name=r[2], kind=r[3]) for r in rows]


def get_or_create_in_transit(sess: Session, *, tenant_id: UUID) -> UUID:
    row = sess.execute(
        text(
            """
            SELECT id FROM inv.location
             WHERE tenant_id = :tid AND kind = 'virtual_in_transit'
             LIMIT 1
            """
        ),
        {"tid": str(tenant_id)},
    ).one_or_none()
    if row is not None:
        return row[0]

    # Pick any site for this tenant to attach the virtual location to.
    site_row = sess.execute(
        text("SELECT id FROM inv.site WHERE tenant_id = :tid ORDER BY name LIMIT 1"),
        {"tid": str(tenant_id)},
    ).one_or_none()
    if site_row is None:
        raise RuntimeError("tenant has no sites; cannot create virtual_in_transit location")

    new_id = uuid4()
    sess.execute(
        text(
            """
            INSERT INTO inv.location (id, tenant_id, site_id, name, kind, restrict_to_home_location)
            VALUES (:id, :tid, :sid, 'virtual_in_transit', 'virtual_in_transit', false)
            """
        ),
        {"id": str(new_id), "tid": str(tenant_id), "sid": site_row[0]},
    )
    return new_id
