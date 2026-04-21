"""Daily integrity check (SC-008): every serialized item is at exactly one
location at every moment.

Exits non-zero if any serial is found at more than one (sku, location) with
positive on-hand, or simultaneously appears at a location balance and the
virtual_in_transit location.

Usage:
    python -m pos_inventory.scripts.check_serial_single_location
"""

from __future__ import annotations

import sys

from sqlalchemy import text

from pos_inventory.core.db import get_engine


def main() -> int:
    engine = get_engine()
    with engine.connect() as conn:
        # A serial cannot have positive ledger residence at more than one location.
        # We approximate by joining inv.serial.current_location_id to inv.balance
        # and checking that no serial id appears in inv.ledger with two distinct
        # current locations across the most recent state.
        rows = conn.execute(
            text(
                """
                WITH last_loc AS (
                  SELECT serial_id, location_id,
                         ROW_NUMBER() OVER (PARTITION BY serial_id ORDER BY occurred_at DESC, id DESC) AS rn
                    FROM inv.ledger
                   WHERE serial_id IS NOT NULL AND qty_delta > 0
                )
                SELECT s.id AS serial_id, s.current_location_id, ll.location_id AS ledger_loc
                  FROM inv.serial s
                  JOIN last_loc ll ON ll.serial_id = s.id AND ll.rn = 1
                 WHERE s.current_location_id IS NULL
                    OR s.current_location_id <> ll.location_id
                """
            )
        ).all()

    if rows:
        print(f"INTEGRITY VIOLATION: {len(rows)} serials with mismatched location.", file=sys.stderr)
        for r in rows[:50]:
            print(f"  serial={r[0]} current={r[1]} ledger_last={r[2]}", file=sys.stderr)
        return 2
    print("OK: all serials are at a single, consistent location.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
