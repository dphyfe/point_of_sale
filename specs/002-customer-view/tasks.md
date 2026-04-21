# Tasks: POS Customer View

**Input**: Design documents from `specs/002-customer-view/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/openapi.yaml, quickstart.md

**Tests**: Per the plan's "minimal — unit only" testing preference (carried over from the inventory feature), each user story includes a small set of focused unit-test tasks alongside implementation. No contract or integration test tasks are generated unless explicitly requested.

**Organization**: Tasks are grouped by user story. User Stories 1, 2, and 3 are all P1 and form the MVP. US4 is P2, US5 is P3.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the new module skeleton and pin the new dependencies before any schema or feature work.

- [X] T001 Create empty package directories with `__init__.py` files: `backend/src/pos_inventory/domain/customers/__init__.py`, `backend/src/pos_inventory/domain/customer_history/__init__.py`, `backend/src/pos_inventory/domain/consent/__init__.py`, `backend/src/pos_inventory/domain/messaging/__init__.py`
- [X] T002 Create empty test package directories with `__init__.py` files: `backend/tests/unit/domain/customers/__init__.py`, `backend/tests/unit/domain/customer_history/__init__.py`, `backend/tests/unit/domain/consent/__init__.py`, `backend/tests/unit/domain/messaging/__init__.py`
- [X] T003 [P] Add runtime dependencies `phonenumbers` and `email-validator` to `backend/pyproject.toml` `[project].dependencies` and re-lock
- [X] T004 [P] Create empty frontend feature folder `frontend/pos/src/features/customers/` with a placeholder `index.ts` so Vite picks it up

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database schemas, RLS, the `customer_id` link to existing inventory transaction tables, and the shared validation/normalization helpers. Nothing in any user story can be built until this phase is green.

⚠️ **CRITICAL**: All US phases depend on this phase.

### Migrations (run in order; no [P])

- [X] T005 Alembic migration `0011_customers.py` creating schema `cust`, tables `cust.customer` (with `version`, `state`, `merged_into`, normalized search columns + GIN/btree indexes per data-model.md R3) and `cust.customer_address`, plus the BEFORE INSERT/UPDATE trigger that recomputes `phone_normalized`/`email_normalized`/`display_name_lower`/`search_vector`, and RLS policies bound to `app.current_tenant`
- [X] T006 Alembic migration `0012_customer_audit_merge.py` creating `cust.profile_change` (append-only, trigger-enforced no UPDATE/DELETE) and `cust.merge` with the `UNIQUE (tenant_id, merged_away_id)` constraint, plus RLS
- [X] T007 Alembic migration `0013_consent.py` creating schema `consent` with `consent.event` (append-only) and `consent.state` projection (composite PK `(tenant_id, customer_id, channel, purpose)`), plus RLS
- [X] T008 Alembic migration `0014_messaging.py` creating schema `msg` with `msg.template`, `msg.message`, `msg.message_status_event` (append-only), and `msg.outbox`, plus the indexes listed in data-model.md and RLS policies
- [X] T009 Alembic migration `0015_link_customer_to_sales.py` adding nullable `customer_id UUID` FK + `btree (tenant_id, customer_id, occurred_at DESC)` index to each existing inventory transaction table that exists today (`ret.customer_return`, `ret.exchange`; guard with `IF EXISTS` for `sales.sale_transaction` and `svc.service_order` so the migration is forward-compatible with later features)
- [X] T010 Add a regression test row to `backend/tests/unit/test_alembic_revisions.py`'s revision id length assertion to cover the new `0011`–`0015` files (re-run the existing length regex test)

### Shared persistence + service scaffolding

- [X] T011 SQLAlchemy ORM models in `backend/src/pos_inventory/persistence/models/customer.py`, `.../customer_address.py`, `.../customer_change.py`, `.../customer_merge.py`, `.../consent_event.py`, `.../consent_state.py`, `.../message_template.py`, `.../customer_message.py`, `.../message_status_event.py`, `.../msg_outbox.py` — each carrying `tenant_id` and matching the columns in data-model.md
- [X] T012 Add the `customer_id` FK relationship to existing return/exchange ORM models in `backend/src/pos_inventory/persistence/models/` (matching what migration T009 added)
- [X] T013 [P] Phone normalization helper `backend/src/pos_inventory/domain/customers/normalization.py` with `to_e164(raw, default_region)` (R3, R11) and a `digits_only(raw)` fallback
- [X] T014 [P] Email validation helper in `backend/src/pos_inventory/domain/customers/normalization.py` (`normalize_email(raw)` + `validate_email_or_raise()`) using `email-validator`
- [X] T015 [P] Optimistic-concurrency helper `backend/src/pos_inventory/domain/customers/concurrency.py` exposing `check_if_match(current_version, header_value)` raising the standard 409 error code `stale_version` (R5)
- [X] T016 [P] Sensitive-value hashing helper `backend/src/pos_inventory/domain/customers/redaction.py` (`hash_with_last4(value)` for tax_id / DOB audit logging — R6)
- [X] T017 RBAC role registration in `backend/src/pos_inventory/core/auth.py`: extend the canonical role set with `Customer Service` and `Marketing` so `requires_role(...)` accepts them. Run the existing 001 inventory unit tests after the change and confirm zero regressions; document the canonical set as open/extensible in `backend/README.md`.
- [X] T018 Visibility-scope dependency `backend/src/pos_inventory/core/visibility.py` reading `visibility_scope` and `assigned_site_ids` claims from the JWT (R9) and returning a SQLAlchemy filter factory used by customer + history repositories
- [X] T019 Register the new API routers as empty stubs in `backend/src/pos_inventory/api/v1/__init__.py`: `customers`, `customer_addresses`, `customer_history`, `customer_messages`, `message_templates`, `customer_consent` (no endpoints yet — just so `main.py` imports cleanly)
- [X] T020 Pydantic v2 schema files for the new API surface: `backend/src/pos_inventory/api/schemas/customers.py`, `.../customer_history.py`, `.../customer_messages.py`, `.../consent.py` — mirroring the components in `specs/002-customer-view/contracts/openapi.yaml`

**Checkpoint**: Foundation ready — all US phases below can now be implemented in parallel.

---

## Phase 3: User Story 1 — Find a customer fast (Priority: P1) 🎯 MVP

**Goal**: Search and list customers by name/phone/email/loyalty/ticket-id with filters, paginated, ≤ 2 s on a 50k-customer tenant.

**Independent Test**: Seed 50k customers; `GET /v1/customers?q=<fragment>` for each input type returns the expected customer in the first page in under 5 s; filters AND-combine; result count is shown.

### Implementation for User Story 1

- [X] T021 [US1] Repository `backend/src/pos_inventory/persistence/repositories/customer_repo.py` with `search()` using `search_vector @@ websearch_to_tsquery`, `phone_normalized LIKE :digits || '%'`, `email_normalized LIKE :q || '%'`, and `lower(external_loyalty_id) = :q`, AND-combined with the column filters from FR-004 and the visibility-scope filter from T018
- [ ] T022 [US1] Ticket-id resolution branch in `customer_repo.py`: when `q` matches the ticket-id pattern, look up the existing inventory transaction tables (`ret.customer_return`, `ret.exchange`, sales when present) and return the attached customer (FR-003)
- [X] T023 [US1] Service `backend/src/pos_inventory/domain/customers/service.py` exposing `search_customers(filters, page, page_size, scope)` — composes the repo call, computes `display_name`, attaches the projected summary fields (`last_purchase_at`, `last_store_visited`, `lifetime_spend`, `visit_count`, `average_order_value`)
- [X] T024 [US1] API endpoint `GET /v1/customers` in `backend/src/pos_inventory/api/v1/customers.py` — wires the service, validates query params, returns the paginated `Customer` list per `contracts/openapi.yaml`
- [X] T025 [US1] API endpoint `GET /v1/customers/{customer_id}` in `backend/src/pos_inventory/api/v1/customers.py` — returns 200 normally, 307 with `Location` header to the survivor when `state='merged'`, 404 otherwise (R4)
- [X] T026 [P] [US1] Unit test `backend/tests/unit/domain/customers/test_search_normalization.py` covering: punctuation-tolerant phone substring, lowercase email match, prefix name match, loyalty-id exact match, ticket-id resolution, AND-combination of `tag` + `city`, and that the visibility-scope filter excludes off-store customers
- [ ] T027 [P] [US1] Frontend `frontend/pos/src/features/customers/api.ts` typed client for `GET /v1/customers` and `GET /v1/customers/{id}` (Zod schemas matching `Customer`)
- [X] T028 [US1] Frontend `frontend/pos/src/features/customers/CustomerList.tsx` — search box, configurable columns, filter rail, pagination, displays result count (FR-001/-005/-006)

**Checkpoint**: User Story 1 fully usable — staff can find a customer and open their profile.

---

## Phase 4: User Story 2 — View a customer's full purchase history (Priority: P1)

**Goal**: From a customer profile, list every sale/return/exchange (sourced from the existing inventory tables), drill down to line items including serials, start a return, and show summary metrics — all reconciling exactly with the inventory data.

**Independent Test**: Pick a customer with sales + returns + exchanges; `GET /v1/customers/{id}/history` lists them reverse-chronologically; drill-down shows correct line items + serial numbers; start-return invokes the existing returns endpoint with pre-populated lines; SUM of history.total equals SUM of underlying sales.total.

### Implementation for User Story 2

- [X] T029 [P] [US2] Read-side repository `backend/src/pos_inventory/persistence/repositories/customer_history_repo.py` with `list_history(customer_id, filters, page, page_size, scope)` — `UNION ALL` over `ret.customer_return`, `ret.exchange`, sales-table-when-present, joined to `inv.location` and `inv.site` for store/register names, ordered `occurred_at DESC` (FR-016/-017)
- [X] T030 [P] [US2] `get_transaction_detail(customer_id, kind, transaction_id, scope)` in the same repo — returns the row plus its line items joined to `inv.sku`, serial numbers from `inv.serial`, and any `related_po_id`/`related_rma_id` (FR-018)
- [X] T031 [P] [US2] `get_summary_metrics(customer_id)` in the same repo — `lifetime_spend`, `visit_count`, `average_order_value`, `last_purchase_at`, `last_store_visited`; consumed by US1's `Customer` projection too (FR-022)
- [X] T032 [US2] Service `backend/src/pos_inventory/domain/customer_history/service.py` composing the three repo functions and applying the visibility-scope filter from T018
- [X] T033 [US2] API endpoint `GET /v1/customers/{customer_id}/history` in `backend/src/pos_inventory/api/v1/customer_history.py` (FR-021/-023)
- [X] T034 [US2] API endpoint `GET /v1/customers/{customer_id}/history/{transaction_kind}/{transaction_id}` in the same router (drill-down — FR-018)
- [X] T035 [US2] Wire summary-metrics call into `domain/customers/service.py` so `GET /v1/customers/{id}` and search results include `last_purchase_at`, `lifetime_spend`, `visit_count`, `average_order_value`, `last_store_visited`
- [ ] T036 [US2] Endpoint shim `POST /v1/customers/{customer_id}/messages` (templated `receipt_copy` send) is **deferred to US4**; for US2 implement only the FE "Email receipt" affordance that calls the existing receipt-print endpoint and records the message via US4 once shipped — leave a TODO marker referencing US4
- [X] T037 [P] [US2] Unit test `backend/tests/unit/domain/customer_history/test_history_composition.py` — seed one sale, one return, one exchange for a customer; assert reverse-chronological order, correct totals, drill-down line items match underlying rows, and that `SUM(history.total) == SUM(underlying.total)` (SC-003 reconciliation)
- [X] T038 [P] [US2] Frontend `frontend/pos/src/features/customers/HistoryTab.tsx` — paginated list, filters (date range, store, kind, min total, sku), drill-down panel; "Start return" button forwards to existing `frontend/pos/src/features/returns/...` flow with `source_transaction_id` (FR-019)
- [X] T039 [P] [US2] Frontend `frontend/pos/src/features/customers/CustomerProfile.tsx` shell with tabs (Overview / History / Messages / Consent / Audit) and a summary panel showing the metrics from T031
- [X] T039a [P] [US2] In `HistoryTab.tsx`, add a "Reprint receipt" affordance per row that calls the existing receipt-print endpoint owned by the inventory feature (FR-020 reprint half). Email-receipt half remains deferred to US4 / T072.

**Checkpoint**: User Story 2 fully usable independently of US3 — history can be viewed even before the create/edit flow exists.

---

## Phase 5: User Story 3 — Create and maintain customer profiles safely (Priority: P1)

**Goal**: Create at checkout (idempotent), edit with optimistic concurrency, field-level audit, role-gated sensitive fields, deactivate, anonymize (DSAR), and manager-only atomic merge with tombstone redirect.

**Independent Test**: Create a customer via `POST /v1/customers` with a `client_request_id`; replay returns the same row with `200`. Edit the email with the wrong `If-Match` → `409 stale_version`. Edit it with the right one → audit row written. Deactivate → search shows inactive flag. Merge two customers → all transactions land under the survivor; `GET` on the merged-away returns `307` to the survivor.

### Implementation for User Story 3

- [X] T040 [US3] `create_customer()` in `backend/src/pos_inventory/domain/customers/service.py` — validates with T013/T014, applies `client_request_id` idempotency (R10) by `INSERT ... ON CONFLICT (tenant_id, client_request_id) DO NOTHING RETURNING ...` then re-SELECT, returns the row, writes a single `cust.profile_change` row of kind `update` recording the create
- [X] T041 [US3] `update_customer()` in the same service — diffs the previous DB row vs the inbound update, calls T015 to enforce `If-Match`, writes one `cust.profile_change` row per changed field (sensitive fields hashed via T016), bumps `version`, persists in one transaction (R5/R6/FR-011)
- [X] T042 [US3] Field-level RBAC enforcement in `update_customer()`: reject changes to `tax_id` / `date_of_birth` from non-Manager+ roles with `403 forbidden` (FR-010, FR-036); the response from `GET` masks `tax_id` to last 4 for non-Manager+ roles
- [X] T043 [US3] `deactivate_customer()` / `reactivate_customer()` in service — flips state, writes one `cust.profile_change` of kind `deactivate`/`reactivate`, prevents new-sale attachment by an enforcement check that lives in the existing sales-create path is **not in scope** (sales feature owns that check; document the contract in code comment)
- [X] T044 [US3] `anonymize_customer()` — clears PII columns + `phone_normalized`/`email_normalized`/`display_name_lower`/`search_vector`, sets `state='anonymized'`, writes one `cust.profile_change` of kind `anonymize`, preserves all FK references (FR-013, FR-038)
- [X] T045 [US3] `merge_customers(survivor_id, merged_away_id, performed_by, summary)` in service — single transaction performing all four steps in R4 (insert `cust.merge`, rewrite `customer_id` on every linked table from T011/T012, set `merged_into` + `state='merged'`, append one summarizing `cust.profile_change`); rejects self-merge and double-merge
- [X] T046 [US3] Helper `resolve_customer_id(id, max_depth=5)` in `customer_repo.py` to follow `merged_into` chains (R4)
- [X] T047 [US3] API endpoints `POST /v1/customers`, `PUT /v1/customers/{id}` (with `If-Match`), `POST /v1/customers/{id}/deactivate`, `POST /v1/customers/{id}/reactivate`, `POST /v1/customers/{id}/anonymize`, `POST /v1/customers/{id}/merge`, `GET /v1/customers/{id}/audit` in `backend/src/pos_inventory/api/v1/customers.py` per `contracts/openapi.yaml`
- [X] T048 Address router `backend/src/pos_inventory/api/v1/customer_addresses.py` implementing `GET / POST` on `/v1/customers/{id}/addresses` and `PUT / DELETE` on `/v1/customers/{id}/addresses/{address_id}`, enforcing the "at most one default per kind" constraint (data-model.md). Each create/update/delete writes one row to the existing `audit.entry` table (kind `customer.address.{created|updated|deleted}`) per FR-011/FR-037 — not to `cust.profile_change`.
- [X] T049 [P] [US3] Unit test `backend/tests/unit/domain/customers/test_profile_audit.py` — every changed field produces exactly one `cust.profile_change` row; sensitive fields are hashed; create writes a `change_kind='update'` row
- [X] T050 [P] [US3] Unit test `backend/tests/unit/domain/customers/test_concurrent_edit.py` — wrong `If-Match` returns `409 stale_version`; correct `If-Match` succeeds and bumps `version`
- [X] T051 [P] [US3] Unit test `backend/tests/unit/domain/customers/test_merge.py` — survivor receives all transactions from merged-away row; merged-away row has `merged_into=survivor_id` and `state='merged'`; resolve helper follows up to depth 5; self-merge and second-merge attempts return `409`; verifies linked-table updates against ret/exchange (and a stub for the sales table)
- [X] T052 [P] [US3] Unit test `backend/tests/unit/api/test_customers_rbac.py` — Cashier cannot write `tax_id`/`date_of_birth`; Manager can; `GET` masks `tax_id` for non-Manager
- [X] T053 [P] [US3] Frontend `frontend/pos/src/features/customers/CustomerCreateInline.tsx` — minimal create dialog used at checkout, generates a UUID `client_request_id`, attaches the new customer to the in-progress sale on success (FR-007, SC-010)
- [X] T054 [P] [US3] Frontend `frontend/pos/src/features/customers/CustomerProfile.tsx` Overview tab edit form — sends `If-Match`, surfaces `409 stale_version` with a "reload latest values" prompt, hides/masks restricted fields when the user lacks Manager role
- [X] T055 [P] [US3] Frontend Audit tab in `CustomerProfile.tsx` consuming `GET /v1/customers/{id}/audit`
- [X] T056 [US3] Idempotent additive seed `backend/src/pos_inventory/scripts/seed_customers.py` mirroring the PO seed pattern: `--customer-count` (target-total), `--customer-add` (additive), Faker-driven names/phones/emails, attaches a random subset to existing return/exchange rows, optional `--with-consent-defaults`; updates `backend/README.md` "Seeding production-like data" subsection

**Checkpoint**: All P1 stories (US1+US2+US3) functional → MVP complete.

---

## Phase 6: User Story 4 — Send one-off messages (Priority: P2)

**Goal**: Send templated or free-text email/SMS from a customer profile, render merge fields, enforce per-channel/per-purpose consent synchronously, persist via the outbox so provider outages do not block POS, and update status from provider callbacks.

**Independent Test**: With a customer opted in to SMS-transactional, `POST /v1/customers/{id}/messages` with `template_code=pickup_ready` returns `201 status=queued`; without consent for marketing, the marketing template returns `403 consent_required`; with the provider intentionally unreachable, sales/returns endpoints continue to succeed (SC-007).

### Implementation for User Story 4

- [X] T057 [P] [US4] Template rendering helper `backend/src/pos_inventory/domain/messaging/render.py` — supports the allow-listed merge fields from data-model.md (`customer.*`, `transaction.*`, `pickup.*`, `business.*`), HTML-escapes for email and plain-escapes for SMS, accepts `merge_overrides`
- [X] T058 [P] [US4] Consent-gate function `backend/src/pos_inventory/domain/consent/gate.py` reading `consent.state` for `(customer_id, channel, purpose)` and applying the FR-030 default rule (R7); raises `consent_required` (403)
- [X] T059 [US4] Service `backend/src/pos_inventory/domain/messaging/service.py` — `send_message()` runs in one transaction: validate input → load template (or accept free-text) → resolve `purpose` → call T058 → render via T057 → insert `msg.message` (status=`queued`) → insert `msg.outbox` row (event_kind=`customer_message.send`) → return the message; idempotent on `client_request_id` (R10)
- [X] T060 [US4] Service `retry_message(message_id, performed_by)` — only allowed when status ∈ {`failed`,`bounced`}; inserts a new `msg.outbox` row of kind `customer_message.retry` and appends a `retrying` `msg.message_status_event`
- [X] T061 [US4] Provider adapter port `backend/src/pos_inventory/domain/messaging/provider.py` — abstract `MessagingProvider.send(channel, to, subject, body) -> ProviderSendResult` plus a `NullProvider` default that pretends success but is gated by an env var so dev mode doesn't actually send
- [X] T062 [US4] HMAC verification helper `backend/src/pos_inventory/domain/messaging/callbacks.py` (`verify(body_bytes, signature_header, shared_secret)`) and a `parse(provider, payload)` function that maps provider-specific shapes to `MessageStatusEvent` rows
- [X] T063 [US4] Outbox dispatcher extension in `backend/src/pos_inventory/workers/outbox_worker.py` (or a new `messaging_worker.py`) — handles `customer_message.send` and `customer_message.retry` event kinds: calls the provider, on success appends a `sent` `msg.message_status_event` and updates `msg.message.status`/`provider`/`provider_message_id`; on failure appends a `failed` event and increments `attempts`
- [X] T064 [US4] API router `backend/src/pos_inventory/api/v1/customer_messages.py` implementing `POST /v1/customers/{id}/messages`, `GET /v1/customers/{id}/messages`, and `POST /v1/customer-messages/{message_id}/retry`
- [X] T065 [US4] Callback API endpoint `POST /v1/customer-messages/callbacks/{provider}` in the same router — `security: []` in OpenAPI, validates `X-POS-Signature` via T062, appends one or more `msg.message_status_event` rows; returns 401 on bad signature
- [X] T066 [P] [US4] Unit test `backend/tests/unit/domain/messaging/test_template_render.py` — known merge fields render, unknown fields raise, HTML email escapes `<script>`, SMS render does not introduce HTML entities
- [X] T067 [P] [US4] Unit test `backend/tests/unit/domain/consent/test_consent_enforcement.py` — marketing send blocked when state is `unset` or `opted_out`; transactional send allowed when state is `unset`; transactional send blocked when explicitly `opted_out`
- [X] T068 [P] [US4] Unit test `backend/tests/unit/domain/messaging/test_outbox_dispatch.py` — successful send appends `sent` event and sets `provider_message_id`; provider exception appends `failed` event and increments `attempts`; idempotent replay on `client_request_id` returns the same `msg.message`
- [X] T069 [P] [US4] Unit test `backend/tests/unit/domain/messaging/test_provider_callbacks.py` — bad HMAC → 401; good HMAC with `delivered` payload appends a `delivered` event and updates `msg.message.status`
- [X] T070 [P] [US4] Unit test `backend/tests/unit/api/test_messaging_rbac.py` — only `Cashier`, `Customer Service`, `Manager`, `Admin` roles can `POST /messages`; only `Manager`, `Admin` can retry (FR-033)
- [X] T071 [P] [US4] Frontend `frontend/pos/src/features/customers/MessagesTab.tsx` — compose with template picker + free-text mode, SMS character/segment counter (FR-026), preview, send, timeline filtered by channel/template (FR-028), retry button on failed rows
- [X] T072 [P] [US4] Replace the US2 TODO from T036: implement the "Email receipt" affordance in `HistoryTab.tsx` to call `POST /v1/customers/{id}/messages` with `template_code=receipt_copy` and `related_transaction_id`/`related_transaction_kind`

**Checkpoint**: US4 functional independently — staff can send messages and see status updates.

---

## Phase 7: User Story 5 — Manage templates and consent (Priority: P3)

**Goal**: Marketing/Admin manage templates (create/update/soft-disable) and per-channel/per-purpose consent (record opt-in/opt-out events sourced from POS, support, or provider unsubscribe webhooks).

**Independent Test**: As Admin, create a marketing SMS template and confirm it appears in the picker; flip a customer's marketing-SMS consent to `opted_out` via `POST /v1/customers/{id}/consent`; attempt to send the marketing template → `403`; flip back to `opted_in` → send succeeds.

### Implementation for User Story 5

- [X] T073 [P] [US5] Service `backend/src/pos_inventory/domain/messaging/template_service.py` — `create_template`, `update_template`, `disable_template` (soft-disable: sets `enabled=false`, never hard-deletes); validates that referenced merge-field tokens are within the allow-list defined in data-model.md; uniqueness check on `(tenant_id, code)`
- [X] T074 [P] [US5] API router `backend/src/pos_inventory/api/v1/message_templates.py` — `GET /v1/message-templates`, `POST /v1/message-templates`, `PUT /v1/message-templates/{id}`, `DELETE /v1/message-templates/{id}`; restricted to `Marketing` and `Admin` roles
- [X] T075 [US5] Service `backend/src/pos_inventory/domain/consent/service.py` — `record_event(customer_id, channel, purpose, event_kind, source, actor_user_id, note)` writes one `consent.event` and upserts the `consent.state` row in the same transaction; `get_matrix_and_history(customer_id)` returns the structure required by `GET /v1/customers/{id}/consent`
- [X] T076 [US5] Provider-unsubscribe path: when T065's callback parser detects an `unsubscribe` event, it calls T075 with `source='provider_unsubscribe'`, `actor_user_id=NULL`, `event_kind='opted_out'` and appends an audit entry (FR-032)
- [X] T077 [US5] API router `backend/src/pos_inventory/api/v1/customer_consent.py` — `GET /v1/customers/{id}/consent`, `POST /v1/customers/{id}/consent`
- [X] T078 [P] [US5] Frontend `frontend/pos/src/features/customers/ConsentTab.tsx` — current matrix, per-channel/per-purpose toggle that records an event with `source='pos'`, history list
- [X] T079 [P] [US5] Frontend `frontend/pos/src/features/customers/TemplatesAdmin.tsx` (admin-only route) — list, create, edit, soft-disable; warns when an inline merge field is not in the allow-list

**Checkpoint**: All user stories functional. Feature is ready for polish.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T080 [P] Performance smoke: write `specs/002-customer-view/performance-smoke.md` describing the seed sizing (50k customers, ≥1k transactions on a chosen customer) and the SC-001/SC-009 measurement protocol; add the EXPLAIN ANALYZE expectations for the GIN/btree indexes from R3
- [X] T081 [P] Quickstart validation: write `specs/002-customer-view/quickstart-validation.md` mapping each numbered step in `quickstart.md` to a curl/HTTPie sequence and the assertion (status, key body fields)
- [X] T082 [P] Add an `openapi.yaml` lint check to `backend/scripts/check_openapi.py` so the new contract file is validated alongside the inventory contract on CI
- [X] T083 [P] Frontend wiring: register the new customers route in `frontend/pos/src/app/App.tsx` and the navigation entry in `frontend/pos/src/app/layout.tsx`
- [X] T084 Run `backend/scripts/check_openapi.py` and resolve any drift between `contracts/openapi.yaml` and the implemented FastAPI routes
- [X] T085 Run quickstart end-to-end against a fresh `Local App` launch and capture results in the validation doc from T081

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: no dependencies — can start immediately.
- **Phase 2 (Foundational)**: depends on Phase 1; **blocks every US**.
- **Phase 3 (US1)** / **Phase 4 (US2)** / **Phase 5 (US3)**: all depend only on Phase 2; can run in parallel by different developers. US1+US2+US3 = MVP.
- **Phase 6 (US4)**: depends on Phase 2; uses US3's customer + US1's lookup but does not require them to be code-complete (the messaging tables stand on their own — just needs a `customer_id` to send to).
- **Phase 7 (US5)**: depends on Phase 2; the consent tab integrates with US4's send-time gate but US5 is independently shippable (the gate is already in place from Phase 6 / consent.state defaults; US5 simply lets staff change the state).
- **Phase 8 (Polish)**: depends on the user stories that will be measured/exercised.

### Within Each User Story

- Repository → service → API endpoint → unit test → frontend.
- US3 idempotent seed (T056) can be written in parallel with the API tasks since it only depends on the ORM models from Phase 2.
- US4 callback handler (T065) depends on T062 + T063.

### Parallel Opportunities

- **Phase 1**: T003 + T004 in parallel (different files).
- **Phase 2**: helpers T013–T016 in parallel; ORM models T011 can run in parallel with T013–T016 once migrations T005–T009 are merged.
- **Phase 3 (US1)**: T026 (test) + T027 (FE client) + T028 (FE list) all in parallel after T021–T025.
- **Phase 4 (US2)**: T029, T030, T031 in parallel; T037, T038, T039 in parallel.
- **Phase 5 (US3)**: T049–T055 are all independent and can run in parallel after T040–T048.
- **Phase 6 (US4)**: T057, T058, T061, T062 all in parallel; T066–T072 all in parallel.
- **Phase 7 (US5)**: T073, T078, T079 in parallel; T075–T077 sequential within consent.
- **Phase 8**: T080–T083 all in parallel.

---

## Parallel Example: User Story 3

```bash
# After T040–T048 land, run these in parallel:
Task: "Unit test profile audit in backend/tests/unit/domain/customers/test_profile_audit.py"
Task: "Unit test concurrent edit in backend/tests/unit/domain/customers/test_concurrent_edit.py"
Task: "Unit test merge in backend/tests/unit/domain/customers/test_merge.py"
Task: "Unit test field-level RBAC in backend/tests/unit/api/test_customers_rbac.py"
Task: "Frontend CustomerCreateInline.tsx in frontend/pos/src/features/customers/"
Task: "Frontend CustomerProfile.tsx Overview edit form"
Task: "Frontend Audit tab in CustomerProfile.tsx"
```

---

## Implementation Strategy

### MVP First (US1 + US2 + US3 — all P1)

1. Phase 1 → Phase 2.
2. Phase 3 (US1), Phase 4 (US2), Phase 5 (US3) — parallel if staffed; otherwise US1 → US2 → US3.
3. Validate independently against the spec's acceptance scenarios + SC-001/-002/-003/-004/-009/-010.
4. Demo: associates can find, view history of, create, edit, and merge customers; messaging UI is hidden behind a feature flag until US4 ships.

### Incremental Delivery

1. MVP (P1 stories) → demo.
2. Phase 6 (US4) → demo: messaging works, including provider-outage smoke (SC-007).
3. Phase 7 (US5) → demo: marketing/admin can manage templates and consent; SC-005 verified end-to-end.
4. Phase 8 polish → final sign-off (SC-001/-009 perf, SC-008 audit completeness).

### Parallel Team Strategy

- Dev A: US1 (FE-heavy)
- Dev B: US2 (read-side composer over inventory tables)
- Dev C: US3 (write-side: create/edit/merge + audit)
- Dev D (joins after Phase 2): US4 (messaging + outbox)
- Dev E (joins after Phase 6): US5 (templates + consent UI)

---

## Traceability

| Phase | User Story | Functional Requirements covered | Success Criteria covered |
|---|---|---|---|
| 3 | US1 | FR-001..006, FR-035 | SC-001 |
| 4 | US2 | FR-016..023 | SC-002, SC-003, SC-009 |
| 5 | US3 | FR-007..015, FR-034, FR-036..038 | SC-004, SC-008, SC-010 |
| 6 | US4 | FR-024..029, FR-033 | SC-006, SC-007 |
| 7 | US5 | FR-030..032 | SC-005 |
| 8 | — | — | SC-001, SC-009 (perf validation), SC-008 (audit sweep) |

---

## Notes

- All tasks follow the strict checklist format: `- [ ] T### [P?] [Story?] description with file path`.
- US1, US2, US3 are all priority P1 and together form the MVP.
- Tests are intentionally minimal (unit only) to match the project's documented testing preference; no contract or integration tests are generated.
- Sales-table linkage in T009 is guarded with `IF EXISTS` so this feature does not block on a sales table that may be introduced by a future feature.
- `seed_customers.py` (T056) follows the same idempotent additive pattern as the existing PO seed and integrates with the existing `Local App` launch task once added to the seed step.
