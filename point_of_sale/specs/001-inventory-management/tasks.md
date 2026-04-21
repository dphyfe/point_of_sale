# Tasks: POS Inventory Management

**Input**: Design documents from `specs/001-inventory-management/`
**Prerequisites**: plan.md (✓), spec.md (✓), research.md (✓), data-model.md (✓), contracts/openapi.yaml (✓), quickstart.md (✓)

**Tests**: Per the plan's testing decision ("minimal — unit tests only, defer e2e"), no contract tests or integration test tasks are generated. Each user story phase ends with a small set of unit-test tasks for the domain logic introduced in that story.

**Organization**: Tasks are grouped by user story so each story can be implemented, tested, and demoed independently. Story priorities mirror spec.md (US1, US2 are P1; US3, US4, US5 are P2).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US5); omitted for Setup, Foundational, and Polish phases
- File paths are absolute relative to the repo root and follow the structure in `plan.md`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure for the FastAPI backend and the React POS client.

- [ ] T001 Create top-level project layout per `specs/001-inventory-management/plan.md` Project Structure: create `backend/`, `backend/src/pos_inventory/`, `backend/src/pos_inventory/{core,domain,api,api/v1,api/schemas,persistence,persistence/models,persistence/repositories}/__init__.py`, `backend/alembic/versions/`, `backend/tests/unit/`, `frontend/pos/src/{app,features,lib,tests}/` with empty `.gitkeep` placeholders
- [ ] T002 Initialize Python project at `backend/pyproject.toml` (Python 3.12) with dependencies: `fastapi`, `pydantic>=2`, `sqlalchemy>=2`, `alembic`, `psycopg[binary]`, `uvicorn[standard]`, `python-jose[cryptography]` (JWT), `pyyaml`, dev: `pytest`, `pytest-asyncio`, `ruff`, `mypy`
- [ ] T003 [P] Initialize `frontend/pos/package.json` with React 18 + Vite + TypeScript 5 + `@tanstack/react-query` + `react-router-dom` + `zod`; dev: `vitest`, `@testing-library/react`, `eslint`, `prettier`. Include `vite.config.ts` and `tsconfig.json`
- [ ] T004 [P] Configure `backend/ruff.toml`, `backend/mypy.ini`, and root `.editorconfig`
- [ ] T005 [P] Configure `frontend/pos/eslint.config.js` and `frontend/pos/.prettierrc`
- [ ] T006 [P] Initialize Alembic at `backend/alembic.ini` and `backend/alembic/env.py` wired to `pos_inventory.core.db` engine

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Cross-cutting infrastructure that every user story depends on (DB, tenancy, RBAC, audit, outbox, ledger primitives, API skeleton, POS app shell).

**⚠️ CRITICAL**: No user story phase may start until this phase is complete.

- [ ] T007 Implement settings loader in `backend/src/pos_inventory/core/config.py` (env-driven: DB DSN, JWT public key, webhook target placeholder)
- [ ] T008 Implement SQLAlchemy 2.x async engine + session in `backend/src/pos_inventory/core/db.py`; export `get_session` FastAPI dependency
- [ ] T009 Implement tenancy resolution in `backend/src/pos_inventory/core/tenancy.py`: `current_tenant_id()` dependency that reads `tenant_id` from the verified JWT and sets the per-request `app.current_tenant` Postgres GUC (per research.md R4)
- [ ] T010 Implement JWT verification + `requires_role(*roles)` dependency in `backend/src/pos_inventory/core/auth.py` against the canonical role set Cashier|Receiver|Inventory Clerk|Store Manager|Purchasing|Admin (FR-036, R5)
- [ ] T011 Implement immutable audit writer in `backend/src/pos_inventory/core/audit.py`: `write_audit(target_kind, target_id, action, before, after)` that inserts into `audit.audit_entry` in the current transaction (FR-031)
- [ ] T012 Implement transactional outbox helper in `backend/src/pos_inventory/core/events.py`: `emit_event(event_type, payload)` that inserts into `outbox.event` in the current transaction (FR-007, R6)
- [ ] T013 [P] Implement FastAPI app factory in `backend/src/pos_inventory/main.py`: CORS, exception handlers (mapping domain errors to 400/403/404/409), router registration stubs
- [ ] T014 [P] Implement common error types in `backend/src/pos_inventory/core/errors.py` (`DomainError`, `RoleForbidden`, `IdempotencyConflict`, `BusinessRuleConflict`, `NotFound`)
- [ ] T015 Alembic migration `backend/alembic/versions/0001_init_schemas.py`: create Postgres schemas `inv`, `po`, `ret`, `rma`, `cnt`, `xfr`, `audit`, `outbox`; enable RLS template helper function
- [ ] T016 [P] Alembic migration `backend/alembic/versions/0002_locations_and_skus.py`: tables `inv.site`, `inv.location` (incl. one seeded `virtual_in_transit` per tenant via separate seed script), `inv.sku`, `po.vendor` per `data-model.md`; enable RLS using `tenant_id`
- [ ] T017 [P] Alembic migration `backend/alembic/versions/0003_inventory_ledger_balance_costlayer.py`: `inv.serial`, `inv.lot`, `inv.balance` (with generated `available`), `inv.ledger` (append-only, with deny-update/delete trigger), `inv.cost_layer`, `inv.adjustment`; UNIQUE indexes for serial uniqueness and `client_intake_id`
- [ ] T018 [P] Alembic migration `backend/alembic/versions/0004_audit_outbox.py`: `audit.audit_entry` (append-only), `outbox.event`
- [ ] T019 SQLAlchemy ORM models for the foundational schemas in `backend/src/pos_inventory/persistence/models/{site.py,location.py,sku.py,vendor.py,serial.py,lot.py,balance.py,ledger.py,cost_layer.py,adjustment.py,audit_entry.py,outbox_event.py}`
- [ ] T020 Implement the inventory ledger writer in `backend/src/pos_inventory/domain/inventory/ledger.py`: `post_movement(sku, location, qty_delta, source_kind, source_doc_id, *, serial=None, lot=None, unit_cost=None, client_intake_id=None)` — single-transaction routine that (a) `SELECT ... FOR UPDATE`s the affected serial / cost-layer / balance rows, (b) consumes FIFO cost layers for non-serialized/lot-tracked outbound and computes outbound `unit_cost`, (c) updates `inv.balance`, (d) inserts the `inv.ledger` row, (e) updates serial state/location for serialized lines (R1, R2, FR-033, FR-035)
- [ ] T021 [P] Pydantic base schemas (UUID, Money, Quantity, error envelope) in `backend/src/pos_inventory/api/schemas/common.py` matching `contracts/openapi.yaml` `#/components/schemas`
- [ ] T022 [P] POS client app shell in `frontend/pos/src/app/{App.tsx,routes.tsx,layout.tsx}` with React Router and a top-nav for the five feature areas
- [ ] T023 [P] POS client typed API helper in `frontend/pos/src/lib/api.ts`: typed `fetch` wrapper that injects `Authorization: Bearer` and a `X-Tenant-Id` header sourced from a stored token; throws typed errors for 4xx
- [ ] T024 [P] POS client offline queue scaffold in `frontend/pos/src/lib/offline-queue.ts`: IndexedDB store `pos_intake`, methods `enqueue(envelope)`, `drain()`, `markOnlineHeartbeat()`, `isOnline()` (FR-034, R3)
- [ ] T025 [P] POS client auth helper in `frontend/pos/src/lib/auth.ts`: token storage, role check helper `hasRole(...)` mirroring backend canonical roles
- [ ] T026 [P] Backend unit tests for `core/auth.py` role-gating in `backend/tests/unit/api/test_auth_roles.py`
- [ ] T027 [P] Backend unit tests for `domain/inventory/ledger.py` happy-path inbound + outbound (non-serialized FIFO, serialized) in `backend/tests/unit/domain/inventory/test_ledger.py`
- [ ] T028 [P] Backend unit tests for `core/audit.py` and `core/events.py` writers in `backend/tests/unit/api/test_audit_outbox.py`

**Checkpoint**: Foundation ready — all five user stories may now begin in parallel.

---

## Phase 3: User Story 1 — Create and Receive Purchase Orders (Priority: P1) 🎯 MVP

**Goal**: Authorized users can create a PO, walk it through `draft → submitted → approved → sent → receiving → closed`, and post (partial) receipts that immediately update on-hand at a chosen location, with serial enforcement on serialized lines and lot capture on lot-tracked lines, and emit events on creation/approval/receipt.

**Independent Test**: Run the Story 1 walkthrough in `quickstart.md` (sections "Seed" + "Story 1") end-to-end against a fresh DB and observe (a) on-hand at the receiving location matches received qty, (b) the phone PO line is `backordered_qty=1` with PO state `receiving`, (c) the USB-C line is fully received within tolerance and closed, (d) `outbox.event` contains `purchase_order.created`, `purchase_order.approved`, and `receipt.posted` rows, and (e) the receive call is rejected when serials given for the phone line don't equal the received qty.

### Implementation for User Story 1

- [ ] T029 [P] [US1] ORM models for POs in `backend/src/pos_inventory/persistence/models/{purchase_order.py,purchase_order_line.py,receipt.py,receipt_line.py,receipt_serial.py}`
- [ ] T030 [P] [US1] Alembic migration `backend/alembic/versions/0005_purchase_orders.py`: `po.purchase_order`, `po.purchase_order_line`, `po.receipt`, `po.receipt_line`, `po.receipt_serial` per `data-model.md`
- [ ] T031 [US1] PO state machine module in `backend/src/pos_inventory/domain/purchase_orders/state.py` enforcing `draft|submitted|approved|sent|receiving|closed|cancelled` transitions and the FR-002/FR-003 role pins
- [ ] T032 [US1] PO service in `backend/src/pos_inventory/domain/purchase_orders/service.py`: `create_po`, `submit`, `approve`, `send`, `cancel`; each transition writes audit entry (T011) and emits the matching outbox event for create/approve (T012) (FR-001, FR-002, FR-003, FR-007)
- [ ] T033 [P] [US1] Pydantic schemas in `backend/src/pos_inventory/api/schemas/purchase_orders.py` matching the `PurchaseOrderInput`, `PurchaseOrder`, and `PurchaseOrderLineInput` models in `contracts/openapi.yaml`
- [ ] T034 [US1] FastAPI router `backend/src/pos_inventory/api/v1/purchase_orders.py`: POST `/purchase-orders`, GET `/purchase-orders`, GET `/purchase-orders/{id}`, POST `/purchase-orders/{id}/{submit,approve,send,cancel}` with `requires_role` per FR-036 mapping
- [ ] T035 [US1] Receiving service in `backend/src/pos_inventory/domain/purchase_orders/receiving.py`: `post_receipt(po_id, location_id, lines)` which (a) validates PO state ∈ {approved, sent, receiving} (FR-004), (b) enforces over-receive tolerance with overage recorded on the line (FR-005), (c) requires N distinct previously-unknown serials for serialized lines (FR-009), (d) requires `lot_code` and creates `inv.lot` for lot-tracked lines (FR-037), (e) calls `ledger.post_movement` per line with `source_kind=po_receipt` (FR-006), (f) updates `received_qty`/`backordered_qty` and closes lines/PO when full (FR-002), (g) emits `receipt.posted` (FR-007)
- [ ] T036 [P] [US1] Pydantic schemas in `backend/src/pos_inventory/api/schemas/receipts.py` for `ReceiptInput`, `ReceiptLineInput`, `Receipt`
- [ ] T037 [US1] FastAPI router `backend/src/pos_inventory/api/v1/receipts.py`: POST `/receipts` gated by `requires_role("Receiver","Inventory Clerk")` returning 400/403/409 per contract
- [ ] T038 [US1] Wire `purchase_orders` and `receipts` routers in `backend/src/pos_inventory/main.py`
- [ ] T039 [P] [US1] POS client feature `frontend/pos/src/features/purchase-orders/` with `PoListPage.tsx`, `PoDetailPage.tsx`, `PoCreatePage.tsx`, `usePurchaseOrders.ts` (TanStack Query) hitting `/purchase-orders`
- [ ] T040 [P] [US1] POS client feature `frontend/pos/src/features/receiving/` with `ReceivePage.tsx` driven by a selected PO; per-line inputs for received qty, location, **serial scan list** (count must match received qty before submit), and lot/expiry inputs for lot-tracked SKUs; uses `useReceipt.ts` mutation
- [ ] T041 [P] [US1] Backend unit tests for the PO state machine in `backend/tests/unit/domain/purchase_orders/test_state.py` covering every legal and illegal transition and role gating
- [ ] T042 [P] [US1] Backend unit tests for receiving in `backend/tests/unit/domain/purchase_orders/test_receiving.py`: serialized count mismatch rejected (FR-009), lot missing rejected (FR-037), over-receive tolerance overage recorded (FR-005), backordered_qty math, PO auto-close on full receipt
- [ ] T043 [P] [US1] POS client unit tests in `frontend/pos/src/features/receiving/__tests__/serial-scan.test.tsx` for the scan-count-equals-qty submit guard

**Checkpoint**: User Story 1 (MVP) is fully functional — POs can be created, approved, and received end-to-end with serial and lot enforcement.

---

## Phase 4: User Story 2 — Serial Number Enforcement (Priority: P1)

**Goal**: SKUs can be configured `serialized`; serials are unique per tenant, attached to sale lines, prevented from being sold twice, validated on returns, and queryable with full lifecycle history. Adds the offline behavior (FR-034) for serialized vs non-serialized sales.

**Independent Test**: With a serialized SKU and 3 receipts, attempt the four failure modes — duplicate serial on receipt, serial sold twice across two registers, return of an unsold serial, sell of a serialized SKU while the register is offline — and verify each is rejected with the right error. Then run the lookup-by-serial endpoint on a serial that has been received, sold, returned, and RMA-closed and verify the full state history is returned.

### Implementation for User Story 2

- [ ] T044 [US2] Serial lifecycle service in `backend/src/pos_inventory/domain/serials/service.py`: `reserve(serial)`, `sell(serial)`, `return_(serial, disposition)`, `mark_rma_pending`, `mark_rma_closed`, `mark_scrapped`; every call uses `SELECT ... FOR UPDATE` on the serial row (R1) and validates the source state per the FR-012 transition diagram
- [ ] T045 [US2] Serial lookup service in `backend/src/pos_inventory/domain/serials/lookup.py`: `get_serial_with_history(serial_value)` joining `inv.serial` with the per-serial slice of `inv.ledger` to produce a `SerialHistoryEntry` list (FR-012)
- [ ] T046 [P] [US2] Pydantic schemas in `backend/src/pos_inventory/api/schemas/serials.py` for `Serial` and `SerialHistoryEntry`
- [ ] T047 [US2] FastAPI router `backend/src/pos_inventory/api/v1/serials.py`: GET `/serials/{serial_value}` returning `{serial, history}`; wire into `main.py`
- [ ] T048 [US2] Sale-side serial validation hook in `backend/src/pos_inventory/domain/serials/sale_guard.py`: `validate_sale(serial_value, sku_id, location_id)` — required for the sale path inside `pos-intake` (T053) and any direct sale endpoint owned by the surrounding POS sales feature
- [ ] T049 [P] [US2] Inventory balances + lookup endpoints in `backend/src/pos_inventory/api/v1/inventory.py`: GET `/inventory/balances` (per FR-026); wire into `main.py`
- [ ] T050 [US2] Backend unit tests in `backend/tests/unit/domain/serials/test_service.py` covering every legal and illegal lifecycle transition and the no-double-sell race (two threads attempting `sell` on the same serial — exactly one wins) (FR-010, FR-033)
- [ ] T051 [P] [US2] Backend unit tests in `backend/tests/unit/domain/serials/test_lookup.py` for full-history reconstruction across receipt → sale → return → RMA close
- [ ] T052 [P] [US2] POS client feature `frontend/pos/src/features/sales/SerialPicker.tsx`: dropdown/scan field that fetches in-stock serials at the register's home location and binds the selected serial to the sale line (FR-010)
- [ ] T053 [US2] Implement `pos-intake` endpoint in `backend/src/pos_inventory/api/v1/pos_intake.py`: POST `/pos-intake/sales` accepting an array of `PosSaleIntake` envelopes; per envelope, `client_intake_id` is the idempotency key (UNIQUE on `inv.ledger`), and the implementation must reject any envelope that contains a serialized SKU line with a clear error (offline path is non-serialized only) (FR-034, R3); on duplicate `client_intake_id` return 409 with code `already_processed`. Wire into `main.py`
- [ ] T054 [P] [US2] POS client offline-queue integration in `frontend/pos/src/features/sales/useSale.ts`: when `offline-queue.isOnline()` is false, queue non-serialized lines and **block** serialized lines with a UI message; on reconnect, drain queue via `POST /pos-intake/sales` and treat 409 `already_processed` as success (FR-034)
- [ ] T055 [P] [US2] POS client unit tests in `frontend/pos/src/features/sales/__tests__/offline-queue-behavior.test.ts`: serialized line blocked while offline; non-serialized line enqueued and drained idempotently
- [ ] T056 [P] [US2] POS client `frontend/pos/src/features/inventory-lookup/SerialLookupPage.tsx`: search box → calls `GET /serials/{value}` → renders state, current location, and full history

**Checkpoint**: User Story 2 fully functional — serial enforcement holds across receive, sale (online and offline), return, and lookup.

---

## Phase 5: User Story 3 — Returns & RMAs (Priority: P2)

**Goal**: Customer returns (with and without receipt) post inventory adjustments to the right location/quality state per disposition; vendor RMAs can be created from returned items, linked to the originating PO and serials, and tracked through `open → shipped → closed`; serial lifecycle states update accordingly.

**Independent Test**: From the Story 1 + 2 baseline, perform a with-receipt return of a serialized phone with disposition `vendor_rma` and verify (a) the phone leaves sellable on-hand, (b) the serial state advances to `rma_pending`, (c) a no-receipt return for a serial that was never sold by this business is rejected (Q4 default), (d) the manager-only path is enforced for no-receipt returns, (e) a vendor RMA created from the return progresses through ship → closed and ends with the serial at `rma_closed`.

### Implementation for User Story 3

- [ ] T057 [P] [US3] ORM models in `backend/src/pos_inventory/persistence/models/{customer_return.py,customer_return_line.py,vendor_rma.py,vendor_rma_line.py}`
- [ ] T058 [P] [US3] Alembic migration `backend/alembic/versions/0006_returns_and_rmas.py`: `ret.customer_return`, `ret.customer_return_line`, `rma.vendor_rma`, `rma.vendor_rma_line`
- [ ] T059 [US3] Returns service in `backend/src/pos_inventory/domain/returns/service.py`: `post_return(input)` enforcing (a) reason_code + disposition required per line (FR-015), (b) with-receipt path links to original sale (FR-013), (c) **no-receipt default policy** (Store Manager approval present, refund forced to `store_credit`, prior-sale serial lookup for serialized) (FR-014, Q4), (d) per-line `target_location_id` resolved from disposition (FR-016), (e) calls `ledger.post_movement` per line, (f) serialized lines call `serials.return_(...)` to update lifecycle state (FR-018)
- [ ] T060 [P] [US3] Pydantic schemas in `backend/src/pos_inventory/api/schemas/returns.py` for `CustomerReturnInput`, `CustomerReturnLineInput`
- [ ] T061 [US3] FastAPI router `backend/src/pos_inventory/api/v1/returns.py`: POST `/returns` (Cashier; Store Manager required for no-receipt path); wire into `main.py`
- [ ] T062 [US3] Vendor RMA service in `backend/src/pos_inventory/domain/rmas/service.py`: `create_rma`, `ship_rma` (writes outbound ledger from holding location, updates serials to remain `rma_pending`), `close_rma` (advances serials to `rma_closed` and records vendor credit value computed via FIFO/serial cost) (FR-017, FR-018, FR-035)
- [ ] T063 [P] [US3] Pydantic schemas in `backend/src/pos_inventory/api/schemas/rmas.py` for `VendorRmaInput`
- [ ] T064 [US3] FastAPI router `backend/src/pos_inventory/api/v1/rmas.py`: POST `/vendor-rmas`, POST `/vendor-rmas/{id}/ship`, POST `/vendor-rmas/{id}/close`; wire into `main.py`
- [ ] T065 [P] [US3] POS client feature `frontend/pos/src/features/returns/` with `ReturnPage.tsx` (with-receipt path pre-fills from sale id; no-receipt path requires manager-approval action and forces store-credit refund), per-line `ReasonAndDispositionPicker.tsx`
- [ ] T066 [P] [US3] POS client feature `frontend/pos/src/features/returns/VendorRmaPage.tsx` to create/ship/close vendor RMAs from returned items
- [ ] T067 [P] [US3] Backend unit tests in `backend/tests/unit/domain/returns/test_service.py`: with-receipt happy path; no-receipt default policy enforced (manager approval, store-credit only, prior-sale serial lookup); per-disposition target_location resolution; serial state updated to `returned`/`scrapped`/`rma_pending` correctly
- [ ] T068 [P] [US3] Backend unit tests in `backend/tests/unit/domain/rmas/test_service.py`: open → shipped → closed transitions; serial advances to `rma_closed` on close; credit value uses FIFO/serial cost (FR-035)

**Checkpoint**: User Story 3 fully functional — customer returns (both paths) and vendor RMAs operate with correct inventory and serial-lifecycle effects.

---

## Phase 6: User Story 4 — Inventory Counts & Reconciliation (Priority: P2)

**Goal**: Managers create scoped count sessions, assign counters, capture counted quantities (with optional system-qty hide), review a per-line variance report against the at-open snapshot plus mid-session movements, and on approval generate adjustment ledger rows with full audit context.

**Independent Test**: Run the Story 4 walkthrough in `quickstart.md`. Verify (a) the variance report computes `counted − (system_at_open + Δmovements_during_session)` for a SKU that received a sale mid-session, (b) approving the session writes one `inv.adjustment` and one `inv.ledger` row of `source_kind=count_adjustment` per non-zero variance, (c) value variance uses FIFO/serial unit cost (FR-035), (d) on-hand after approval matches counted quantity, (e) the `hide_system_qty` flag prevents the counted value from being returned by the entries-fetch endpoint.

### Implementation for User Story 4

- [ ] T069 [P] [US4] ORM models in `backend/src/pos_inventory/persistence/models/{count_session.py,count_session_snapshot.py,count_assignment.py,count_entry.py}`
- [ ] T070 [P] [US4] Alembic migration `backend/alembic/versions/0007_count_sessions.py`: `cnt.count_session`, `cnt.count_session_snapshot`, `cnt.count_assignment`, `cnt.count_entry`
- [ ] T071 [US4] Count session service in `backend/src/pos_inventory/domain/counts/service.py`: `create_session(scope, hide_system_qty)` resolves the in-scope `(sku, location)` pairs and writes the at-open snapshot rows (R7); `assign(session_id, user_id, location_id)`; `submit_entries(session_id, entries)` (FR-019–FR-022)
- [ ] T072 [US4] Variance computation in `backend/src/pos_inventory/domain/counts/variance.py`: per `(sku, location)` returns `system_at_open`, `Δmovements_during_session` (computed from `inv.ledger` rows in `[session.created_at, now]` filtered to scope), `counted_qty`, `variance_qty`, `variance_value` (FIFO/serial cost) (FR-023, FR-035)
- [ ] T073 [US4] Approval routine in `backend/src/pos_inventory/domain/counts/approve.py`: for each non-zero variance, create an `inv.adjustment` (with reason and counter user/timestamp) and call `ledger.post_movement(source_kind=count_adjustment)` (FR-024, FR-031)
- [ ] T074 [P] [US4] Pydantic schemas in `backend/src/pos_inventory/api/schemas/counts.py` for `CountSessionInput`, `CountEntryInput`
- [ ] T075 [US4] FastAPI router `backend/src/pos_inventory/api/v1/counts.py`: POST `/count-sessions`, POST `/count-sessions/{id}/entries`, GET `/count-sessions/{id}/variance`, POST `/count-sessions/{id}/approve` (Store Manager); wire into `main.py`
- [ ] T076 [P] [US4] POS client feature `frontend/pos/src/features/counts/CountSessionListPage.tsx` and `CountSessionCreatePage.tsx`
- [ ] T077 [P] [US4] POS client feature `frontend/pos/src/features/counts/CountingUI.tsx`: barcode scan input that resolves SKU, increments counted qty, and **does not display system qty when `hide_system_qty` is true** (FR-022)
- [ ] T078 [P] [US4] POS client feature `frontend/pos/src/features/counts/VarianceReviewPage.tsx`: per-line variance view with drill-down to counter user, and an Approve button gated by Store Manager role
- [ ] T079 [P] [US4] Backend unit tests in `backend/tests/unit/domain/counts/test_variance.py`: variance reflects mid-session sale (the spec edge case); value variance uses FIFO unit cost
- [ ] T080 [P] [US4] Backend unit tests in `backend/tests/unit/domain/counts/test_approve.py`: one adjustment per non-zero variance; on-hand equals counted post-approval (SC-004); audit entry written

**Checkpoint**: User Story 4 fully functional — cycle and full counts post correct adjustments with full audit and value variance.

---

## Phase 7: User Story 5 — Multiple Locations & Transfers (Priority: P2)

**Goal**: A site/location/bin hierarchy is queryable; balances are tracked per `(SKU, location)`; transfers move stock with `source ship → virtual_in_transit → destination receive`; serialized lines pin specific serials; POS can be configured per location to restrict selling to home-location stock.

**Independent Test**: Run the Story 5 walkthrough in `quickstart.md`. Verify (a) shipping a transfer moves stock from source on-hand to `virtual_in_transit`, (b) receiving moves it from `virtual_in_transit` to destination on-hand, (c) the serialized line's serial is at exactly one location at every moment (daily integrity check returns zero violations — SC-008), (d) a POS register at the front location with the per-location restriction enabled refuses to sell a SKU not stocked at front.

### Implementation for User Story 5

- [ ] T081 [P] [US5] ORM models in `backend/src/pos_inventory/persistence/models/{transfer.py,transfer_line.py,transfer_serial.py}`
- [ ] T082 [P] [US5] Alembic migration `backend/alembic/versions/0008_transfers.py`: `xfr.transfer`, `xfr.transfer_line`, `xfr.transfer_serial`; seed/per-tenant create-on-first-write of the `virtual_in_transit` location row in `inv.location`
- [ ] T083 [US5] Locations service in `backend/src/pos_inventory/domain/locations/service.py`: `list_sites`, `list_locations(site_id?)`, `get_or_create_in_transit(tenant_id)`
- [ ] T084 [P] [US5] FastAPI routers `backend/src/pos_inventory/api/v1/locations.py` (GET `/sites`, GET `/locations`) — wire into `main.py`
- [ ] T085 [US5] Transfer service in `backend/src/pos_inventory/domain/transfers/service.py`: `create_transfer`, `ship` (per line: outbound ledger from source + inbound ledger into `virtual_in_transit`; for serialized lines, `xfr.transfer_serial` rows must equal qty and each serial gets `current_location_id = virtual_in_transit`), `receive` (per line: outbound from `virtual_in_transit`, inbound into destination; serialized serials' `current_location_id` updated to destination) (FR-027, FR-028, FR-029)
- [ ] T086 [P] [US5] Pydantic schemas in `backend/src/pos_inventory/api/schemas/transfers.py` for `TransferInput`
- [ ] T087 [US5] FastAPI router `backend/src/pos_inventory/api/v1/transfers.py`: POST `/transfers`, POST `/transfers/{id}/ship`, POST `/transfers/{id}/receive`; wire into `main.py`
- [ ] T088 [US5] Per-register/location selling restriction in `backend/src/pos_inventory/domain/serials/sale_guard.py` and `domain/inventory/sale_guard.py`: when the configured POS register has `restrict_to_home_location=true`, reject sales of SKUs/serials not present at the register's home location (FR-030)
- [ ] T089 [P] [US5] POS client feature `frontend/pos/src/features/transfers/` with `TransferListPage.tsx`, `TransferCreatePage.tsx`, `TransferShipPage.tsx` (per-line serial picker for serialized SKUs), `TransferReceivePage.tsx`
- [ ] T090 [P] [US5] POS client feature `frontend/pos/src/features/inventory-lookup/InventoryByLocationPage.tsx` showing on-hand/reserved/available per location for a SKU
- [ ] T091 [P] [US5] Backend unit tests in `backend/tests/unit/domain/transfers/test_service.py`: ship moves to in_transit, receive lands at destination, serialized serial at exactly one location at each step, ship/receive role gating
- [ ] T092 [P] [US5] Backend unit tests in `backend/tests/unit/domain/serials/test_sale_guard.py`: per-location selling restriction blocks the cross-location sale (FR-030)

**Checkpoint**: User Story 5 fully functional — locations queryable, transfers move stock with serial pinning, per-location selling restriction enforced.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Improvements and integrity guarantees that span multiple stories.

- [ ] T093 [P] Daily integrity-check script `backend/src/pos_inventory/scripts/check_serial_single_location.py` returning a non-zero exit if any serial is at more than one location or simultaneously at a location and `virtual_in_transit` (SC-008)
- [ ] T094 [P] Outbox worker process `backend/src/pos_inventory/workers/outbox_worker.py` that polls `outbox.event` and POSTs `{event_id, event_type, tenant_id, occurred_at, payload}` to the configured tenant webhook with at-least-once retry
- [ ] T095 [P] Configuration endpoints in `backend/src/pos_inventory/api/v1/config.py` (Admin): over-receive tolerance per SKU/category, per-location selling restriction per register, no-receipt return enable flag per store; persists to a `config` table (add a small Alembic migration `0009_config.py` if not yet present)
- [ ] T096 [P] OpenAPI generation: ensure `app.openapi()` output matches `specs/001-inventory-management/contracts/openapi.yaml`; add a CI check script `backend/scripts/check_openapi.py` that fails on drift
- [ ] T097 [P] POS client offline heartbeat in `frontend/pos/src/lib/offline-queue.ts`: poll `/healthz` every 15 s and update `markOnlineHeartbeat()`; trigger `drain()` on transition to online (FR-034)
- [ ] T098 [P] Run the `quickstart.md` walkthrough end-to-end against a fresh Alembic-migrated DB and record the run in `specs/001-inventory-management/quickstart-validation.md`
- [ ] T099 [P] Performance smoke: load 10k SKUs and 200k serials into a dev DB and assert `GET /inventory/balances?sku_id=...` p95 < 2 s and `POST /receipts` (10-line) p95 < 500 ms (SC-006)
- [ ] T100 [P] README at `backend/README.md` covering env vars, `alembic upgrade head`, `uvicorn pos_inventory.main:app`, and how to run unit tests; README at `frontend/pos/README.md` covering `npm run dev` and the offline-queue behavior

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; T003/T004/T005/T006 may run in parallel after T001/T002.
- **Foundational (Phase 2)**: Depends on Setup. Within Phase 2: T007 → T008 → T009/T010/T011/T012 (parallel after T008); T015 → T016/T017/T018 (parallel after T015); T019 depends on T016–T018; T020 depends on T019. T021–T028 may run in parallel once their dependencies land.
- **User Stories (Phase 3–7)**: All depend on Foundational. Once Phase 2 is done, US1–US5 can run in parallel by different developers; the only cross-story coupling is that US3 imports the serial lifecycle from US2 (`serials.return_`) and US5 imports the same module — schedule US2 first if running sequentially.
- **Polish (Phase 8)**: Depends on the user stories you intend to ship.

### Within Each User Story

- Models/migrations (the [P] tasks at the top) can run in parallel.
- Domain services depend on models being in place.
- API routers depend on schemas + services.
- Frontend feature tasks depend only on the API contract (`contracts/openapi.yaml`) and may run in parallel with backend implementation, mocking the API client until the backend lands.
- Unit-test tasks depend only on the modules they test.

### Parallel Opportunities

- All `[P]` tasks within a phase target distinct files and can run concurrently.
- All user stories beyond US1 can be parallelized once Phase 2 + US2 (serial lifecycle module) have landed.

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1: Setup
2. Phase 2: Foundational (CRITICAL — blocks every story)
3. Phase 3: User Story 1
4. **Stop and validate** with the Story 1 walkthrough in `quickstart.md`
5. Demo / deploy

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. + US1 → MVP (PO create/receive)
3. + US2 → serialized SKUs are sellable end-to-end (this is the second P1 — should be paired with US1 in production rollout)
4. + US3 → returns and vendor RMAs
5. + US4 → counts and reconciliation
6. + US5 → multi-location and transfers
7. Polish phase

### Parallel Team Strategy

- Pair A: Setup + Foundational, then US1
- Pair B: After Foundational lands, US2 (serial lifecycle is needed by US3 and US5)
- Pair C: After US2 module lands, US3 (returns/RMAs)
- Pair D: After Foundational lands, US4 (counts) — independent of US2/US3
- Pair E: After US2 module lands, US5 (transfers)

---

## Notes

- `[P]` = different files, no incomplete dependencies.
- `[Story]` label maps each task to its user story for traceability.
- Tests are unit-only by clarified preference; e2e is deferred. Re-run `/speckit.tasks` if that preference changes.
- Commit after each task or logical group.
- Stop at any checkpoint to validate a story independently.
- Avoid: vague tasks, edits to the same file from two parallel tasks, cross-story coupling beyond the deliberately shared serial-lifecycle module.
