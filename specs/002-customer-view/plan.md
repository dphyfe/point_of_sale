# Implementation Plan: POS Customer View

**Branch**: `002-customer-view` | **Date**: 2026-04-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/002-customer-view/spec.md`

## Summary

Deliver a staff-facing Customer workspace that sits alongside the existing POS Inventory + Sales features. It centralizes a per-tenant Customer directory with fast multi-key search (name, phone, email, loyalty ID, ticket ID), profile create/edit with field-level audit, role-based field visibility, deactivation, and an admin-gated merge that preserves history under a tombstone redirect. Purchase history is **assembled by reference** from existing inventory transactions (POs/receipts already exist; sales/returns/exchange transactions are extended with an optional `customer_id` link) so totals, serials, and locations stay reconciled with inventory by construction. Outbound email/SMS uses an outbox-pattern integration with an abstract `messaging_provider` adapter, enforces per-channel + per-purpose consent (marketing vs transactional), and records consent history and asynchronous delivery status. The feature ships as new modules in the existing FastAPI backend (new `cust`, `msg`, `consent` Postgres schemas + a small extension to the existing sales/return tables) and a new feature folder in the existing React POS client.

## Technical Context

**Language/Version**: Python 3.13 (backend, matches existing service), TypeScript 5.x (POS web client)
**Primary Dependencies**: FastAPI + Pydantic v2, SQLAlchemy 2.x + Alembic, psycopg 3, uvicorn (already in use); React 18 + Vite, TanStack Query, Zod (already in use); `phonenumbers` (E.164 normalization for search & validation), `email-validator` (RFC 5322 syntax check). The "messaging provider" is an abstract adapter — concrete implementations (e.g., AWS SES + SNS, Twilio + SendGrid) are pluggable and **out of scope** for this plan.
**Storage**: PostgreSQL 16. New schemas `cust` (customers, addresses, profile-change log, merges), `msg` (templates, messages, status history, outbox), `consent` (per-channel/purpose consent events). New nullable column `customer_id UUID` on existing sales/return/exchange/service-order tables (with FK + index). Per-tenant isolation via `tenant_id NOT NULL` on every new table + the existing RLS pattern (`app.current_tenant`).
**Testing**: pytest + pytest-asyncio for backend unit tests (matches inventory feature's "minimal — unit only" preference). Vitest for POS client unit tests. OpenAPI is the contract artifact.
**Target Platform**: Same as inventory feature — Linux containers behind a load balancer; POS client in modern browsers on store-side hardware.
**Project Type**: Web application (extends existing backend service + existing React POS client).
**Performance Goals**: Customer search p95 < 5 s on a 50k-customer tenant returning the first page (SC-001); profile open p95 < 1 s; first-page purchase-history load p95 < 2 s for customers with 1,000+ transactions (SC-009); message send acknowledged by API in < 500 ms with provider hand-off via outbox worker (does not block POS sales — SC-007).
**Constraints**: Marketing-tagged sends MUST be blocked at the API layer when consent is missing (SC-005, FR-030). All profile edits, merges, deactivations, sends, and consent changes MUST land in an immutable audit/consent log (SC-008, FR-037). Merging MUST be atomic with respect to transaction reattachment and tombstone insertion (FR-014). Provider failures MUST never block POS core flows (SC-007, FR-033). Region/store visibility scoping (FR-035) MUST be enforced server-side, not just in the UI.
**Scale/Scope**: Up to ~50k customers per tenant initially (target: 500k headroom); up to ~5 outbound messages per customer per month average; up to ~10k profile edits/day per tenant at peak; same ~50 stores/tenant deployment ceiling as inventory.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The repository constitution (`.specify/memory/constitution.md`) is the unmodified placeholder template — no concrete principles have been ratified for this project. The gate therefore has no enforceable rules to evaluate and **passes trivially**. No violations to record in Complexity Tracking.

If/when a real constitution is ratified, re-run `/speckit.analyze` to validate this plan against it.

## Project Structure

### Documentation (this feature)

```text
specs/002-customer-view/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── openapi.yaml     # Phase 1 output — HTTP contract for the customer service
├── checklists/
│   └── requirements.md  # From /speckit.specify
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
backend/
├── alembic/
│   └── versions/
│       ├── 0011_customers.py                  # cust schema: customer, customer_address
│       ├── 0012_customer_audit_merge.py       # cust.profile_change, cust.merge tombstone
│       ├── 0013_consent.py                    # consent schema
│       ├── 0014_messaging.py                  # msg schema: template, message, message_status, outbox
│       └── 0015_link_customer_to_sales.py     # add nullable customer_id FK + index to existing sales/return tables
└── src/
    └── pos_inventory/
        ├── domain/
        │   ├── customers/                     # profile, search normalization, deactivate, merge (FR-001..015)
        │   ├── customer_history/              # read-side composer over existing inventory tables (FR-016..023)
        │   ├── consent/                       # per-channel/purpose consent ledger (FR-030..032)
        │   └── messaging/                     # template render, send, status callbacks, outbox worker (FR-024..029, FR-033)
        ├── api/
        │   ├── v1/
        │   │   ├── customers.py               # list/search/create/get/update/deactivate/merge
        │   │   ├── customer_addresses.py
        │   │   ├── customer_history.py        # paginated history + drill-down + start-return shim → existing returns API
        │   │   ├── customer_messages.py       # compose, send, list, retry; provider callback subroute
        │   │   ├── message_templates.py       # admin CRUD on templates
        │   │   └── customer_consent.py        # consent read + explicit set
        │   └── schemas/
        │       ├── customers.py
        │       ├── customer_history.py
        │       ├── customer_messages.py
        │       └── consent.py
        ├── persistence/
        │   ├── models/
        │   │   ├── customer.py
        │   │   ├── customer_address.py
        │   │   ├── customer_change.py
        │   │   ├── customer_merge.py
        │   │   ├── consent_event.py
        │   │   ├── message_template.py
        │   │   └── customer_message.py        # + message_status_event
        │   └── repositories/
        │       ├── customer_repo.py           # search uses normalized indexes (R3)
        │       └── customer_history_repo.py   # joins existing sales/return tables (read-only)
        ├── workers/
        │   └── messaging_worker.py            # outbox dispatch + provider callback handling (extends existing outbox_worker pattern)
        └── scripts/
            └── seed_customers.py              # idempotent additive seed (mirrors PO seed pattern)

backend/tests/
└── unit/
    ├── domain/
    │   ├── customers/
    │   │   ├── test_search_normalization.py
    │   │   ├── test_profile_audit.py
    │   │   ├── test_merge.py
    │   │   └── test_concurrent_edit.py
    │   ├── customer_history/
    │   │   └── test_history_composition.py
    │   ├── consent/
    │   │   └── test_consent_enforcement.py
    │   └── messaging/
    │       ├── test_template_render.py
    │       ├── test_outbox_dispatch.py
    │       └── test_provider_callbacks.py
    └── api/
        ├── test_customers_rbac.py
        └── test_messaging_rbac.py

frontend/pos/src/
├── features/
│   └── customers/
│       ├── CustomerList.tsx                   # search box, filters, configurable columns (US1)
│       ├── CustomerProfile.tsx                # tabs: Overview / History / Messages / Consent / Audit (US2/US3)
│       ├── CustomerCreateInline.tsx           # in-checkout quick create (US3)
│       ├── HistoryTab.tsx                     # paginated history + drill-down; "Start return" → existing returns flow
│       ├── MessagesTab.tsx                    # compose with template/free-text + timeline (US4)
│       ├── ConsentTab.tsx                     # opt-in toggles + history (US5)
│       └── api.ts                             # typed client for /v1/customers, /v1/customer-messages, /v1/message-templates
└── tests/                                     # Vitest unit tests for the above
```

**Structure Decision**: Web-application layout extending the existing service. The customer feature is a **set of new domain modules** inside the existing `pos_inventory` Python package (we do not split into a second service — the feature reuses the same DB, the same auth/RBAC dependency, the same outbox + worker pattern, the same RLS scaffolding). New PostgreSQL schemas (`cust`, `msg`, `consent`) keep ownership clean and let `pg_dump --schema=` work for ops. Sales/return tables get a single nullable `customer_id` link in a small migration, so customer history reads from the canonical inventory data instead of duplicating it. The POS client gets a new `features/customers/` folder; the existing returns flow is invoked as a downstream action from `HistoryTab`, not re-implemented.

## Complexity Tracking

> No constitution gate violations to justify (constitution is unratified placeholder). Table intentionally empty.
# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]
**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: [e.g., Python 3.11, Swift 5.9, Rust 1.75 or NEEDS CLARIFICATION]  
**Primary Dependencies**: [e.g., FastAPI, UIKit, LLVM or NEEDS CLARIFICATION]  
**Storage**: [if applicable, e.g., PostgreSQL, CoreData, files or N/A]  
**Testing**: [e.g., pytest, XCTest, cargo test or NEEDS CLARIFICATION]  
**Target Platform**: [e.g., Linux server, iOS 15+, WASM or NEEDS CLARIFICATION]
**Project Type**: [e.g., library/cli/web-service/mobile-app/compiler/desktop-app or NEEDS CLARIFICATION]  
**Performance Goals**: [domain-specific, e.g., 1000 req/s, 10k lines/sec, 60 fps or NEEDS CLARIFICATION]  
**Constraints**: [domain-specific, e.g., <200ms p95, <100MB memory, offline-capable or NEEDS CLARIFICATION]  
**Scale/Scope**: [domain-specific, e.g., 10k users, 1M LOC, 50 screens or NEEDS CLARIFICATION]

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

[Gates determined based on constitution file]

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
# [REMOVE IF UNUSED] Option 1: Single project (DEFAULT)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# [REMOVE IF UNUSED] Option 2: Web application (when "frontend" + "backend" detected)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# [REMOVE IF UNUSED] Option 3: Mobile + API (when "iOS/Android" detected)
api/
└── [same as backend above]

ios/ or android/
└── [platform-specific structure: feature modules, UI flows, platform tests]
```

**Structure Decision**: [Document the selected structure and reference the real
directories captured above]

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
