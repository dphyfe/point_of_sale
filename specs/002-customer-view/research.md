# Phase 0 Research — POS Customer View

The spec was detailed enough to leave no `[NEEDS CLARIFICATION]` items, so Phase 0 focuses on locking the technical-decision unknowns introduced by adding a customer/messaging slice to the existing inventory service. Each item resolves a single Technical-Context decision before Phase 1 design.

## R1 — Where customer-to-transaction linkage lives

**Decision**: Add a single nullable `customer_id UUID` column (FK → `cust.customer.id`, indexed) to each existing transaction table that can be associated with a customer (sales, returns, exchanges, service orders). No new join table. The customer history read path joins these tables on `customer_id` plus `tenant_id`.

**Rationale**: One column per table is the smallest possible change to the inventory schema, keeps the read path a simple indexed join, and never forces a customer to be present (guest sales remain valid). Aligns with FR-016 (history sourced from existing transactions) and SC-003 (no orphan or duplicate history rows).

**Alternatives considered**:
- A separate `customer_transaction` join table — rejected: adds a second source of truth that can drift from the underlying transactions; the spec's hard requirement is reconciliation with inventory data.
- A polymorphic `customer_link(entity_type, entity_id)` table — rejected: loses FK integrity per entity and complicates RLS.

## R2 — Multi-tenancy and isolation

**Decision**: Reuse the inventory feature's exact pattern: `tenant_id UUID NOT NULL` on every new table, `app.current_tenant` GUC set per request, RLS policies enabled as defense-in-depth. New schemas `cust`, `msg`, `consent` follow the same `pg_dump --schema=` ownership model (R8 of the inventory research).

**Rationale**: Operational consistency and zero new tenancy code. Catches any forgotten WHERE clauses at the data tier.

**Alternatives considered**:
- Schema-per-tenant — rejected for the same reasons as the inventory feature (migration churn).

## R3 — Search performance and normalization (FR-002 / FR-003 / SC-001)

**Decision**:
- Maintain **denormalized search columns** populated by a `BEFORE INSERT/UPDATE` trigger:
  - `phone_normalized` — E.164 form via the `phonenumbers` library; fall back to digits-only when E.164 parsing fails.
  - `email_normalized` — lowercase, trimmed.
  - `display_name_lower` — `LOWER(coalesce(first_name || ' ' || last_name, company_name))`.
  - `search_vector` — `tsvector` over `display_name_lower`, `email_normalized`, `phone_normalized`, plus loyalty IDs.
- Indexes:
  - `GIN(search_vector)` for full-text and prefix matching.
  - `btree(phone_normalized)` for substring `LIKE` against the digit form.
  - `btree(email_normalized)` for exact + prefix.
  - `btree(LOWER(loyalty_id))` for fast loyalty lookups.
- Receipt/ticket-ID search is satisfied by the existing inventory transaction tables, not a customer-side index — the API queries those directly and returns the `customer_id` they're attached to.

**Rationale**: Hits SC-001 (<5 s find on a 50k+ tenant) without external infra. Triggers keep search columns consistent with the canonical fields without code-path discipline. Substring matching on punctuation-stripped phone numbers is what associates actually need (the spec calls this out explicitly).

**Alternatives considered**:
- ILIKE over raw fields — rejected: cannot do substring phone search across formatted variants without scanning.
- External search (OpenSearch, Meilisearch) — rejected: extra infra not justified at the spec's scale; would also be a second source of truth.
- Stored generated columns vs trigger-maintained — chose trigger because `phonenumbers` parsing is not pure SQL.

## R4 — Customer merge atomicity (FR-014, SC-004)

**Decision**: A single transaction performs:
1. Insert a `cust.merge(survivor_id, merged_away_id, performed_by, occurred_at)` row.
2. `UPDATE` every table carrying `customer_id` (sales/returns/exchanges/service orders + customer-side messages, addresses, consent events, profile-change rows) `SET customer_id = survivor_id WHERE customer_id = merged_away_id AND tenant_id = :tid`.
3. `UPDATE cust.customer SET merged_into = survivor_id, state = 'merged' WHERE id = merged_away_id` (the row stays — this is the tombstone).
4. Insert one `cust.profile_change` audit entry summarizing the merge.

Resolution helper: any GET on a customer redirects via `merged_into` until it lands on a non-merged row, capped at depth 5 (cycle protection).

**Rationale**: Strong atomicity with no extra infra. Tombstone preserves deep links per the spec's edge case. Cap protects against accidentally created cycles.

**Alternatives considered**:
- Soft-link by inserting an alias row only — rejected: every read path would have to remember to follow it; high risk of drift.
- Hard-delete the merged-away row — rejected: breaks deep links and audit history.

## R5 — Concurrent profile edits (FR-015)

**Decision**: Optimistic concurrency via a monotonically-increasing `version int` column on `cust.customer`. PUT requests carry `If-Match: <version>`; the server rejects with `409 stale_version` and returns the current row when the versions disagree.

**Rationale**: Lightweight, no row-level locking on a hot UI path, and the conflict UX (re-show latest values, ask the user to retry) is exactly what the spec edge case requires. Not enough write contention to need pessimistic locking.

**Alternatives considered**:
- `SELECT ... FOR UPDATE` per edit — rejected: heavier than warranted; blocks the second user mid-edit.
- Last-write-wins — rejected: explicitly contradicts FR-015.

## R6 — Field-level audit log (FR-011)

**Decision**: A single append-only table `cust.profile_change(id, tenant_id, customer_id, actor_user_id, occurred_at, field, old_value text, new_value text)`. The customer service computes a diff between the previous DB row and the inbound update and writes one row per changed field in the same transaction as the update. Sensitive fields (e.g., tax ID) store a hash + last-4 instead of the literal value.

**Rationale**: Append-only mirrors the immutable-audit pattern already used by the inventory feature (R2 / FR-031 there). Per-field rows make "show me the history for field X" trivial. Hashing sensitive values keeps the log usable without becoming a second copy of the secret.

**Alternatives considered**:
- JSON-blob-per-edit (`changes jsonb`) — rejected: clumsy filters per field.
- Trigger-based logging — rejected: hides logic away from the application code that already has the actor identity.

## R7 — Consent enforcement (FR-030, FR-031, SC-005)

**Decision**: A `consent.event` append-only ledger keyed by `(customer_id, channel, purpose)`. The current state per `(customer_id, channel, purpose)` is materialized in `consent.state` (one row per combo, updated transactionally with each ledger insert). The `MessageTemplate` carries `purpose enum: transactional | marketing`. The send endpoint reads `consent.state` for the customer + template's channel + template's purpose and rejects with `403 consent_required` when not `opted_in`. Transactional sends are allowed unless an explicit hard opt-out exists for that purpose. The check is performed **inside the API handler** (not only in the worker) so the rejection is synchronous from the user's perspective.

**Rationale**: Two-table design (ledger + state) gives audit history (FR-031) and a fast lookup for the gate (FR-030, SC-005) without recomputing on every send. Synchronous gate makes SC-005 trivially testable.

**Alternatives considered**:
- Compute current consent on the fly from the ledger — rejected: extra latency on every send.
- Consent stored on the customer row directly — rejected: loses the per-event history required by FR-031.

## R8 — Outbound messaging delivery (FR-027, FR-029, FR-033, SC-006, SC-007)

**Decision**: Reuse the existing **transactional outbox** pattern (R6 of inventory research). Send flow:
1. API handler validates consent (R7), renders the template, persists `msg.message` (status = `queued`) and a corresponding `audit.outbox` row, all in one transaction.
2. The existing outbox worker (extended to handle `customer_message.send` events) reads the row, calls the configured `messaging_provider` adapter, updates `msg.message_status_event` with `sent` and the provider message ID.
3. The provider's asynchronous webhook callback hits `POST /v1/customer-messages/callbacks/{provider}` (no auth on callback path — instead, an HMAC over the payload using a per-provider shared secret). The handler writes one `msg.message_status_event` per status update.
4. Failed sends are visible on the timeline with a "retry" action available to authorized roles; retry re-enqueues an outbox row.

**Rationale**: Decoupling from the provider via the outbox is what guarantees SC-007 (POS continues to function during a provider outage). Per-event status history (vs overwriting a single status field) gives the trail FR-029/SC-006 ask for.

**Alternatives considered**:
- Synchronous provider call inside the request — rejected: a slow/down provider would block staff during checkout flows; explicitly contradicts SC-007.
- Polling for status — rejected: providers offer callbacks; polling is wasteful and slower.

## R9 — Region/store visibility scoping (FR-035)

**Decision**: A per-user attribute `visibility_scope: { all_stores | own_stores }`, plus a per-user `assigned_site_ids[]` set, both delivered in the JWT (no DB lookup needed in the hot path). Customer queries either return all customers (when `all_stores`) or restrict to customers who have **at least one** transaction at one of the user's sites — implemented as `EXISTS` subquery against the existing inventory transaction tables. The same `EXISTS` predicate is added to the GET-by-id authorization check.

**Rationale**: Reuses the inventory transactions as the canonical "where has this customer been seen" source — keeps the rule consistent and avoids a second store-membership table. JWT-driven scope keeps the request hot path free of extra DB hops.

**Alternatives considered**:
- A `customer_store_membership` join table — rejected: must be kept in sync with the actual transactions; second source of truth.
- Region scoping enforced only in the UI — rejected by FR-035 (must be server-side).

## R10 — Idempotency for `POST` writes

**Decision**:
- Customer create accepts an optional `client_request_id` UUID; the server stores it in `cust.customer.client_request_id` with a unique index per tenant. A duplicate POST returns `200 OK` with the existing customer instead of `201 Created`.
- Message send accepts an optional `client_request_id` with the same semantics on `msg.message`.

**Rationale**: Mirrors the inventory feature's `client_intake_id` pattern (R3 of inventory research). Critical for the in-checkout "create customer" path where a network blip could otherwise duplicate the customer and the sale.

**Alternatives considered**:
- Server-generated dedup keys — rejected: client cannot retry safely without knowing the key.

## R11 — Email/SMS validation

**Decision**: Use `email-validator` for syntactic email checks. Use `phonenumbers` to parse to E.164 (defaulting region to the tenant's `default_country` setting; falls back to `US`). Reject inputs that fail to parse with a 422.

**Rationale**: Battle-tested libraries; consistent with how phone search is normalized (R3).

**Alternatives considered**:
- Regex — rejected: notoriously inadequate for both formats.
- Skip validation, push to provider — rejected: provider rejection is async and a poor UX.

## R12 — Front-end data layer

**Decision**: TanStack Query for server-state caching (already in use by the inventory POS client). Zod schemas generated from this feature's OpenAPI for request/response validation. New `features/customers/api.ts` mirrors the existing module's `lib/api.ts` conventions.

**Rationale**: Zero new client concepts; matches "minimal — unit tests only" preference.

**Alternatives considered**:
- A separate Customer SPA — rejected: it's a tab inside the existing POS, not a separate product.

## Summary table

| ID | Topic | Decision |
|---|---|---|
| R1 | Customer ↔ transactions linkage | Single nullable `customer_id` FK on existing sales/return/exchange/service-order tables |
| R2 | Multi-tenancy | Reuse inventory pattern: `tenant_id` + RLS in new `cust`, `msg`, `consent` schemas |
| R3 | Search & normalization | Trigger-maintained `phone_normalized`, `email_normalized`, `display_name_lower`, `search_vector` + GIN/btree indexes |
| R4 | Merge atomicity | Single-transaction merge with tombstone (`merged_into`); GET resolves redirects up to depth 5 |
| R5 | Concurrent edits | Optimistic concurrency via `version int` + `If-Match`; 409 on stale |
| R6 | Field audit | Append-only `cust.profile_change(field, old, new, actor, ts)`; sensitive values hashed |
| R7 | Consent | `consent.event` ledger + `consent.state` projection; synchronous send-time gate |
| R8 | Outbound delivery | Transactional outbox + worker → provider; HMAC-verified callback writes status events |
| R9 | Visibility scoping | JWT-delivered `visibility_scope` + `assigned_site_ids`; `EXISTS` subquery against inventory transactions |
| R10 | Idempotency | `client_request_id` on customer create + message send |
| R11 | Email/SMS validation | `email-validator` + `phonenumbers` (E.164, tenant default region) |
| R12 | POS client data layer | Reuse TanStack Query + Zod-from-OpenAPI conventions |

All Phase-0 unknowns resolved. Proceed to Phase 1.
