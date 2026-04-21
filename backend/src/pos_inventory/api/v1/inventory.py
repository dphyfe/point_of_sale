"""Inventory balance lookups (FR-026)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.auth import Principal, get_principal
from pos_inventory.core.tenancy import tenant_session

router = APIRouter(prefix="/inventory", tags=["inventory"])


class BalanceRow(BaseModel):
    sku_id: UUID
    location_id: UUID
    on_hand: Decimal
    reserved: Decimal
    available: Decimal


@router.get("/balances", response_model=list[BalanceRow])
def list_balances(
    sku_id: UUID | None = None,
    location_id: UUID | None = None,
    sess: Session = Depends(tenant_session),
    _: Principal = Depends(get_principal),
) -> list[BalanceRow]:
    sql = "SELECT sku_id, location_id, on_hand, reserved, available FROM inv.balance WHERE 1=1"
    params: dict = {}
    if sku_id is not None:
        sql += " AND sku_id = :sid"
        params["sid"] = str(sku_id)
    if location_id is not None:
        sql += " AND location_id = :lid"
        params["lid"] = str(location_id)
    sql += " ORDER BY sku_id, location_id LIMIT 1000"
    rows = sess.execute(text(sql), params).all()
    return [
        BalanceRow(
            sku_id=r[0],
            location_id=r[1],
            on_hand=Decimal(r[2]),
            reserved=Decimal(r[3]),
            available=Decimal(r[4]),
        )
        for r in rows
    ]
