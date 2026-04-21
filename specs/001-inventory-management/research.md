# Phase 0 Research — POS Inventory Management

All five spec clarifications already resolved the high-impact unknowns (offline POS, costing, RBAC, no-receipt returns, lot scope). Phase 0 therefore focuses on locking in the technical-decision unknowns that the chosen stack introduces. Each item below resolves a single Technical-Context decision needed before Phase 1 design.

## R1 — Concurrency model for serial uniqueness and FIFO consumption

**Decision**: Use PostgreSQL row-level locking via `SELECT ... FOR UPDATE` on the serial row (for sale/transfer/return) and on the eligible cost-layer rows (for FIFO consumption), inside a single transaction that also writes the inventory ledger entry. Serial uniqueness is additionally enforced by a `UNIQUE (tenant_id, sku_id, serial_value)` index so duplicates fail at the DB even if a code path skips the lock.

**Rationale**: Satisfies FR-010 (no double-sell), FR-029 (a serial is at one place at one time), FR-033 (no negative on-hand from a race), and FR-035 (deterministic FIFO consumption) without introducing an external lock service. PostgreSQL's MVCC + `FOR UPDATE` is well-understood, transactional, and free.

**Alternatives considered**:
- Optimistic concurrency with version columns — rejected: livelock under heavy contention on hot SKUs (e.g., a popular phone) at sale time.
- Distributed lock (Redis/Redlock) — rejected: extra infra, weaker guarantees than the DB it's protecting; not justified at our scale (≤50 stores/tenant).
- Advisory locks on (tenant, sku, location) — rejected: coarser than needed and harder to reason about than per-row `FOR UPDATE`.

## R2 — Inventory ledger vs balance projection

**Decision**: Append-only `inventory_ledger` table is the source of truth for every quantity-affecting movement (receipt, sale, return, RMA ship, transfer ship/receive, count adjustment, manual adjustment). Two derived projections are maintained transactionally with each ledger insert: `inventory_balance(tenant_id, sku_id, location_id, on_hand, reserved, available)` and `inventory_cost_layer(tenant_id, sku_id, location_id, received_at, qty_remaining, unit_cost)`. The audit trail (FR-031) reads from the ledger plus the per-document `audit_entry` table for non-quantity actions (state transitions, role-gated approvals).

**Rationale**: Satisfies FR-031 (immutable audit), FR-035 (FIFO needs ordered layers, not just balances), and SC-006 (cashier read p95 < 2 s — projections are pre-aggregated). One write transaction = one ledger row + projection updates keeps balances always consistent with ledger by construction.

**Alternatives considered**:
- Balance-only model (no ledger) — rejected: cannot satisfy FR-031 without reconstructing history from per-document tables, which is brittle.
- Event-sourcing with projections rebuilt async from a queue — rejected: introduces eventual-consistency windows that conflict with FR-033 (no double-sell) and the SC-006 5 s reflection target on the same hardware.

## R3 — Offline POS reconciliation (FR-034)

**Decision**: POS client maintains an IndexedDB-backed queue of `pos_sale_intake` envelopes for non-serialized lines created while offline. Each envelope carries a client-generated UUID (`client_intake_id`), the register id, the cashier user id, the location id, the sale lines, and the local timestamp. On reconnect, the client POSTs envelopes to `POST /v1/pos-intake/sales`; the server treats `client_intake_id` as an idempotency key and rejects duplicates with `409 already_processed`. Serialized SKUs are never enqueued; the client UI blocks adding them while `navigator.onLine === false` or the last server heartbeat is older than 30 s.

**Rationale**: Direct implementation of the Q1 clarification. Idempotency key prevents the double-decrement edge case already noted in spec Edge Cases. IndexedDB chosen over LocalStorage for size and structured-record support.

**Alternatives considered**:
- Server-side dedup by `(register_id, sequence_number)` — rejected: requires the client to hand out monotonically-increasing sequences across browser refreshes, which is fragile.
- Block all sales while offline — rejected by Q1.

## R4 — Multi-tenancy isolation

**Decision**: Single shared schema with `tenant_id UUID NOT NULL` on every business table; enforced at the API layer via a FastAPI dependency that resolves `tenant_id` from the bearer token and adds a SQLAlchemy `before_compile` filter. PostgreSQL row-level security (RLS) is enabled as defense-in-depth, with a session-local `app.current_tenant` GUC set per request.

**Rationale**: Operational simplicity (one DB, one migration set) for a deployment ceiling of ~50 stores/tenant and a modest tenant count. RLS catches any code path that forgets to filter, addressing FR-032 (RBAC) at the data tier as well as the API tier.

**Alternatives considered**:
- Schema-per-tenant — rejected: migration churn scales linearly with tenants; harder to add cross-tenant analytics later.
- Database-per-tenant — rejected: significant ops overhead; not warranted at target scale.

## R5 — Authentication and role enforcement (FR-036)

**Decision**: The inventory service consumes JWT bearer tokens minted by the broader POS auth service (assumption already documented in spec). Tokens carry `sub` (user id), `tenant_id`, and `roles[]` constrained to the canonical set `Cashier | Receiver | Inventory Clerk | Store Manager | Purchasing | Admin`. A `requires_role(*roles)` FastAPI dependency wraps every state-transition endpoint per the FR-036 mapping.

**Rationale**: Directly enforces FR-036 server-side; matches the spec's stated assumption that auth lives in the surrounding POS system. Stateless JWT keeps the inventory service horizontally scalable.

**Alternatives considered**:
- Session cookies — rejected: complicates horizontal scaling and adds CSRF surface for the offline-queue endpoint.
- Custom permission strings instead of named roles — rejected by Q3 (fixed canonical roles).

## R6 — Event emission (FR-007)

**Decision**: Outbox-pattern. Every domain transaction that needs to emit an event (PO created, PO approved, PO receipt posted; extensible to returns/transfers later) writes a row to an `outbox` table in the same transaction as the business write. A separate worker process reads `outbox` and publishes to the configured sink (initially: HTTP webhook target configured per tenant; pluggable for a future message broker). Events carry `event_id`, `event_type`, `tenant_id`, `occurred_at`, and a JSON `payload`.

**Rationale**: Guarantees at-least-once delivery without needing a 2-phase commit between Postgres and a broker. Lets us ship without a broker dependency for v1.

**Alternatives considered**:
- Direct HTTP publish inside the request transaction — rejected: a slow/down webhook would block user-facing writes and violate SC-006.
- Pure CDC from the ledger — rejected: ledger rows do not carry the higher-level "PO approved" semantics cleanly.

## R7 — Count session: hide-system-quantity and concurrent sales

**Decision**: When a count session is created, snapshot `inventory_balance` rows for the session scope into `count_session_snapshot(session_id, sku_id, location_id, system_qty_at_open)`. The variance report is computed as `counted_qty − system_qty_at_open + (any movements posted during the session window)`, so late sales during counting are reflected (matches the spec Edge Case). The "hide system quantity" option (FR-022) is a per-session boolean that simply gates whether the counting UI fetches the snapshot value.

**Rationale**: Clean semantics for the spec's noted edge case (mid-count sale) without locking sales (which would block revenue). Snapshot is per-session so two overlapping sessions on the same SKU produce internally-consistent variances each.

**Alternatives considered**:
- Lock affected SKUs from sale during count — rejected: blocks revenue; not viable for cycle counts in a busy store.
- Compute variance against live balance at close — rejected: produces phantom variances when sales happen mid-count.

## R8 — Migrations and schema layout

**Decision**: Alembic with one migration file per logical schema slice introduced (locations → sku/serial/lot policy → inventory_ledger + projections → POs → returns → RMAs → counts → transfers → outbox → audit). Each business table lives in a Postgres schema named after its domain folder (`inv`, `po`, `ret`, `rma`, `cnt`, `xfr`, `audit`, `outbox`).

**Rationale**: Clear ownership; selective `pg_dump --schema=` works for ops; matches the `domain/` folder layout in the plan structure.

**Alternatives considered**:
- All tables in `public` — rejected: harder to grep ownership; schema-per-domain is cheap in Postgres.

## R9 — POS client data layer

**Decision**: TanStack Query for server-state caching; Zod schemas generated from the OpenAPI contract for request/response validation; a thin `api.ts` typed client wraps fetch with auth/tenant headers. Routing via React Router. No global Redux store — feature folders own local state.

**Rationale**: Matches "minimal — unit tests only" preference; fewer moving parts means fewer things to test. TanStack Query's `mutate` hooks compose cleanly with the offline queue from R3.

**Alternatives considered**:
- Redux Toolkit Query — rejected: heavier, more boilerplate than needed for this scope.
- Hand-rolled fetch + useState — rejected: would re-implement caching and request dedup that TanStack Query gives for free.

## Summary table

| ID | Topic | Decision |
|---|---|---|
| R1 | Concurrency for serials/FIFO | `SELECT ... FOR UPDATE` + `UNIQUE` index on serial |
| R2 | Inventory ledger vs balance | Append-only ledger + transactional balance & cost-layer projections |
| R3 | Offline POS reconciliation | IndexedDB queue + idempotent `pos-intake` endpoint keyed by `client_intake_id` |
| R4 | Multi-tenancy | Shared schema, `tenant_id` column, Postgres RLS as defense-in-depth |
| R5 | AuthN/Z | JWT from POS auth, `requires_role(...)` per FR-036 mapping |
| R6 | Event emission | Transactional outbox + worker → webhook |
| R7 | Count semantics | Per-session snapshot of system qty at open; live movements roll into variance |
| R8 | Migrations & schemas | Alembic, one schema per domain folder |
| R9 | POS client data layer | TanStack Query + Zod from OpenAPI |

All Phase-0 unknowns resolved. Proceed to Phase 1.
