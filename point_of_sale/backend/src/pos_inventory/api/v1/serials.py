from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from pos_inventory.api.schemas.serials import (
    Serial,
    SerialHistoryEntry,
    SerialWithHistory,
)
from pos_inventory.core.auth import Principal, get_principal
from pos_inventory.core.tenancy import tenant_session
from pos_inventory.domain.serials.lookup import get_serial_with_history

router = APIRouter(prefix="/serials", tags=["serials"])


@router.get("/{serial_value}", response_model=SerialWithHistory)
def get_serial(
    serial_value: str,
    sess: Session = Depends(tenant_session),
    principal: Principal = Depends(get_principal),
) -> SerialWithHistory:
    s, h = get_serial_with_history(sess, tenant_id=principal.tenant_id, serial_value=serial_value)
    return SerialWithHistory(
        serial=Serial(
            id=s.id,
            sku_id=s.sku_id,
            serial_value=s.serial_value,
            state=s.state,
            current_location_id=s.current_location_id,
            unit_cost=s.unit_cost,
            received_at=s.received_at,
        ),
        history=[
            SerialHistoryEntry(
                occurred_at=e.occurred_at,
                source_kind=e.source_kind,
                source_doc_id=e.source_doc_id,
                location_id=e.location_id,
                qty_delta=e.qty_delta,
                unit_cost=e.unit_cost,
            )
            for e in h
        ],
    )
