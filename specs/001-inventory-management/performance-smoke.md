# Performance Smoke Plan (SC-006)

Goal: verify p95 latency targets hold for the inventory list and receipt
ingest paths under a representative dataset.

## Targets
- `GET /v1/inventory/balances?sku_id=...` p95 < **2 s**
- `POST /v1/receipts` (10-line receipt) p95 < **500 ms**

## Dataset
- 10,000 SKUs (`inv.sku`)
- 200,000 serials (`inv.serial`) distributed across SKUs/locations
- 5 sites × 4 locations
- 100 vendors
- ~50,000 historical ledger rows for warm balances

## Method
1. Use `tools/perf_seed.py` (to be authored) to bulk-insert via
   `COPY` for SKUs/serials and parameterized inserts for ledger.
2. Use `wrk` or `k6` against a localhost backend with the dev JWT bypass:
   ```sh
   k6 run --vus 20 --duration 60s scripts/k6_balances.js
   k6 run --vus 10 --duration 60s scripts/k6_receipts.js
   ```
3. Record p50/p95/p99 and number of errors.

## Acceptance
- p95 below targets across two consecutive runs.
- Zero 5xx; <1 % 4xx (idempotency conflicts permitted on receipt rerun).

## Optimization Hooks (if targets miss)
- Verify indexes: `(tenant_id, sku_id, location_id)` on `inv.balance`,
  `(tenant_id, sku_id, location_id, occurred_at)` on `inv.ledger`,
  `(tenant_id, serial_value)` on `inv.serial`.
- Connection pool size and `statement_timeout`.
- Consider materialized view for top-of-list balance queries if needed.

## Status
Pending execution — record results inline once run.
