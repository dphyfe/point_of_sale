from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.auth import Principal, get_principal, requires_role
from pos_inventory.core.tenancy import tenant_session

router = APIRouter(prefix="/config", tags=["config"])


class TenantConfigOut(BaseModel):
    over_receive_tolerance_pct: Decimal
    no_receipt_returns_enabled: bool
    extras: dict


class TenantConfigPatch(BaseModel):
    over_receive_tolerance_pct: Decimal | None = Field(default=None, ge=0, le=100)
    no_receipt_returns_enabled: bool | None = None
    extras: dict | None = None


@router.get("", response_model=TenantConfigOut)
def get_config(
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> TenantConfigOut:
    row = sess.execute(
        text(
            """
            SELECT over_receive_tolerance_pct, no_receipt_returns_enabled, extras
              FROM inv.tenant_config WHERE tenant_id = :tid
            """
        ),
        {"tid": str(principal.tenant_id)},
    ).one_or_none()
    if row is None:
        return TenantConfigOut(
            over_receive_tolerance_pct=Decimal("0"),
            no_receipt_returns_enabled=True,
            extras={},
        )
    return TenantConfigOut(
        over_receive_tolerance_pct=Decimal(row[0]),
        no_receipt_returns_enabled=bool(row[1]),
        extras=row[2] or {},
    )


@router.patch(
    "",
    response_model=TenantConfigOut,
    dependencies=[Depends(requires_role("Admin"))],
)
def patch_config(
    body: TenantConfigPatch,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> TenantConfigOut:
    sess.execute(
        text(
            """
            INSERT INTO inv.tenant_config
                (tenant_id, over_receive_tolerance_pct, no_receipt_returns_enabled, extras, updated_at, updated_by)
            VALUES (:tid, :tol, :nr, :ex, :ts, :uid)
            ON CONFLICT (tenant_id) DO UPDATE SET
                over_receive_tolerance_pct = COALESCE(EXCLUDED.over_receive_tolerance_pct, inv.tenant_config.over_receive_tolerance_pct),
                no_receipt_returns_enabled = COALESCE(EXCLUDED.no_receipt_returns_enabled, inv.tenant_config.no_receipt_returns_enabled),
                extras = COALESCE(EXCLUDED.extras, inv.tenant_config.extras),
                updated_at = EXCLUDED.updated_at,
                updated_by = EXCLUDED.updated_by
            """
        ),
        {
            "tid": str(principal.tenant_id),
            "tol": body.over_receive_tolerance_pct if body.over_receive_tolerance_pct is not None else Decimal("0"),
            "nr": True if body.no_receipt_returns_enabled is None else body.no_receipt_returns_enabled,
            "ex": body.extras or {},
            "ts": datetime.now(timezone.utc),
            "uid": str(principal.user_id),
        },
    )
    return get_config(sess=sess, principal=principal)
