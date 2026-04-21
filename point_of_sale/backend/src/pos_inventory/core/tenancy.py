"""Tenancy: extract tenant_id from JWT and set Postgres GUC for RLS."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.auth import get_principal, Principal
from pos_inventory.core.db import get_session


def current_tenant_id(principal: Principal = Depends(get_principal)) -> UUID:
    return principal.tenant_id


def tenant_session(
    request: Request,
    sess: Session = Depends(get_session),
    tenant_id: UUID = Depends(current_tenant_id),
) -> Session:
    """Scope `sess` to the request's tenant by setting `app.current_tenant`."""
    sess.execute(text("SELECT set_config('app.current_tenant', :tid, true)"), {"tid": str(tenant_id)})
    request.state.tenant_id = tenant_id
    return sess
