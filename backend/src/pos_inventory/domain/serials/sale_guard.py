"""Sale-side guard: validate that a serial is sellable from a given location.

Also enforces per-register `restrict_to_home_location` (FR-030).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from pos_inventory.core.errors import BusinessRuleConflict, NotFound


def validate_sale(
    sess: Session,
    *,
    tenant_id: UUID,
    serial_value: str,
    sku_id: UUID,
    location_id: UUID,
) -> UUID:
    """Return the serial_id if the (serial, sku, location) combo is sellable.

    Raises BusinessRuleConflict for any of: unknown serial, sku mismatch,
    state not in {sellable, reserved}, location mismatch when the destination
    location is a `restrict_to_home_location` register.
    """
    row = sess.execute(
        text(
            """
            SELECT s.id, s.sku_id, s.state, s.current_location_id, l.restrict_to_home_location
              FROM inv.serial s
              LEFT JOIN inv.location l ON l.id = :lid
             WHERE s.tenant_id = :tid AND s.serial_value = :sv
            """
        ),
        {"tid": str(tenant_id), "sv": serial_value, "lid": str(location_id)},
    ).one_or_none()
    if row is None:
        raise NotFound(f"serial {serial_value}")
    serial_id, s_sku, state, cur_loc, restrict = row
    if s_sku != sku_id:
        raise BusinessRuleConflict("serial does not belong to this SKU")
    if state not in {"sellable", "reserved"}:
        raise BusinessRuleConflict(f"serial state '{state}' is not sellable")
    if restrict and cur_loc != location_id:
        raise BusinessRuleConflict("serial not at register's home location (restricted)")
    return serial_id
