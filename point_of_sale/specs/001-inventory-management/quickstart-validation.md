# Quickstart Validation Log

This file records execution of `quickstart.md` against a freshly migrated
database. Update on each release. Status values: `pending`, `pass`, `fail`.

## Environment
- Branch: `001-inventory-management`
- DB: `postgresql+psycopg://postgres:postgres@localhost:5432/pos_inventory`
- Backend: `uvicorn pos_inventory.main:app`
- Frontend: `npm run dev` in `frontend/pos`

## Step Status

| # | Step | Status | Notes |
|---|------|--------|-------|
| 1 | Bootstrap (`pip install -e .[dev]`, `npm install`) | pending | Run during release validation. |
| 2 | `alembic upgrade head` | pending | Verifies all 9 migrations apply on a fresh DB. |
| 3 | Seed minimal tenant (site, location, sku, vendor) | pending | Manual or via seed script. |
| 4 | US1 — Create PO → Approve → Receive | pending | Verify ledger row + cost layer + serial creation. |
| 5 | US2 — Sell serialized item | pending | Verify serial state moves `sellable→sold`, ledger debit. |
| 6 | US3 — Customer return (no-receipt, manager approval) | pending | Verify refund forced to `store_credit`. |
| 7 | US3 — Vendor RMA open→ship→close | pending | Verify credit_total uses serial cost. |
| 8 | US4 — Count session (blind), submit, approve | pending | Verify one adjustment per non-zero variance. |
| 9 | US5 — Transfer ship→receive (serialized) | pending | Verify serial visits virtual_in_transit then destination. |
| 10 | Run `python -m pos_inventory.scripts.check_serial_single_location` | pending | Expect exit 0. |
| 11 | `pytest backend/tests/unit -q` | pending | All unit tests pass. |
| 12 | `npm run test` in frontend/pos | pending | Frontend unit tests pass. |

## Sign-off
- Date: _pending_
- Operator: _pending_
- Result: _pending_
