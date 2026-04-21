from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pos_inventory.core.auth import Principal, get_principal
from pos_inventory.core.tenancy import tenant_session
from pos_inventory.domain.locations.service import list_locations, list_sites

router = APIRouter(tags=["locations"])


class SiteOut(BaseModel):
    id: UUID
    name: str
    code: str


class LocationOut(BaseModel):
    id: UUID
    site_id: UUID
    name: str
    kind: str


@router.get("/sites", response_model=list[SiteOut])
def get_sites(
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> list[SiteOut]:
    return [SiteOut(**s.__dict__) for s in list_sites(sess, tenant_id=principal.tenant_id)]


@router.get("/locations", response_model=list[LocationOut])
def get_locations(
    site_id: UUID | None = Query(default=None),
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> list[LocationOut]:
    return [LocationOut(**loc.__dict__) for loc in list_locations(sess, tenant_id=principal.tenant_id, site_id=site_id)]
