# Performance Smoke — Customer View (002)

This document describes the performance-smoke protocol for SC-001 (search
≤ 1 s p95) and SC-009 (history ≤ 1 s p95) on a single-region Postgres 16
instance with at least 4 vCPU and 16 GiB RAM.

## Seed sizing

Use [`scripts/seed_customers.py`](../../backend/src/pos_inventory/scripts/seed_customers.py)
to bring the test tenant to **50,000 customers**:

```pwsh
$env:POS_INVENTORY_AUTH_BYPASS = "true"
python -m pos_inventory.scripts.seed_customers --confirm --customer-count 50000 --with-consent-defaults
```

For the history-perf assertion, identify a "heavy" customer who owns at least
**1,000** transactions across `ret.customer_return`, `sales.sale_transaction`
(when present), and `svc.service_order`. The seed attaches new customers to a
random subset of unlinked returns; for a richer load, run the inventory seed
with `--reset` then this seed.

## Measurement protocol

Run each of the following 30 times from a warm pool (kernel cached) and capture
p50/p95/p99 latencies in milliseconds.

| Endpoint | Query | SC | Threshold |
|----------|-------|----|-----------|
| `GET /v1/customers` | `?q=smith&limit=25` | SC-001 | p95 ≤ 1000 ms |
| `GET /v1/customers` | `?q=512` (phone fragment) | SC-001 | p95 ≤ 1000 ms |
| `GET /v1/customers/{id}/history` | `?limit=25` | SC-009 | p95 ≤ 1000 ms |
| `GET /v1/customers/{id}/history` | `?kinds=sale&limit=25` | SC-009 | p95 ≤ 1000 ms |

A simple loop using ApacheBench or `hey` is sufficient; pin the same
`X-Dev-Tenant` header throughout.

## EXPLAIN ANALYZE expectations (R3)

The query planner should rely on these indexes (defined in migration
`0010_customer_view_init.py`):

* `cust.customer_search_vector_gin` — used for `q ILIKE %term%` searches
  expanded into a `tsquery`.
* `cust.customer_phone_normalized_idx` (btree) — partial match against the
  digits-only normalization for phone fragment searches.
* `cust.customer_email_normalized_idx` (btree) — partial match against
  `email_normalized`.
* `cust.customer_external_loyalty_id_idx` (unique partial) — exact
  loyalty-id lookups.
* `ret.customer_return_customer_id_idx` (and equivalents on optional
  history tables) — used by the history union for filtering by
  `customer_id` then ordering by `occurred_at` desc.

A run of:

```sql
EXPLAIN (ANALYZE, BUFFERS) SELECT id FROM cust.customer
 WHERE tenant_id = $1 AND search_vector @@ websearch_to_tsquery('english', 'smith')
 LIMIT 25;
```

should report a `Bitmap Heap Scan` on `customer` with the GIN index used in the
inner Bitmap Index Scan. If a sequential scan appears, vacuum/analyze the table
and re-check the planner stats.

## Pass/fail

A run passes when **all** of the four endpoints above land at p95 ≤ 1000 ms in
two consecutive runs. Capture the raw latency CSVs alongside this document for
each release that touches `cust.*`, `consent.*`, `msg.*`, or the search vectors.
