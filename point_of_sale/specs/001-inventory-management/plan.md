# Implementation Plan: POS Inventory Management

**Branch**: `001-inventory-management` | **Date**: 2026-04-20 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `specs/001-inventory-management/spec.md`

## Summary

Deliver an inventory subsystem for the POS that supports purchase order create-and-receive (with serial enforcement on receive), serialized + lot-tracked + non-serialized SKUs, customer returns and vendor RMAs, count sessions with variance-driven adjustments, and multi-location stock with explicit transfers. The system is delivered as a multi-tenant cloud HTTP service backed by PostgreSQL with a React POS web client. Inventory mutations (receipts, sales, returns, transfers, adjustments) write atomically to the inventory ledger and produce both a per-(SKU, location) balance projection and a FIFO cost-layer projection within the same transaction. The POS client follows an online-first model with the offline behavior decided in clarifications: serialized sales are blocked while offline; non-serialized sales queue locally and reconcile on reconnect via an idempotent intake endpoint.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript 5.x (POS web client)  
**Primary Dependencies**: FastAPI + Pydantic v2 (HTTP/serialization), SQLAlchemy 2.x + Alembic (ORM/migrations), psycopg 3 (driver), uvicorn (ASGI), React 18 + Vite (POS client), TanStack Query (client data layer), Zod (client validation)  
**Storage**: PostgreSQL 16 (single primary, logical schema per concern: `inv`, `po`, `ret`, `cnt`, `xfr`, `audit`); per-tenant row isolation via `tenant_id` column on every inventory-affecting table  
**Testing**: pytest + pytest-asyncio for backend unit tests (per clarified preference: minimal — unit only, e2e deferred); Vitest for POS client unit tests; OpenAPI schema is the contract artifact, not contract tests  
**Target Platform**: Linux containers behind a load balancer (cloud); POS client runs in modern browsers on store-side hardware  
**Project Type**: Web application (backend service + React POS client)  
**Performance Goals**: Inventory lookup p95 < 2 s for cashier UI (SC-006); receipt/sale/return/transfer/adjustment write p95 < 500 ms; count variance posting (≤ 200 lines) completes < 60 s end-to-end (SC-005); event emission within 5 s of source event (SC-006)  
**Constraints**: Strong serial uniqueness across the tenant (no double-sell, FR-010 / SC-008); FIFO cost layers must be consumed deterministically under concurrency (FR-035); offline POS must not double-decrement on reconnect (FR-034); audit entries are immutable (FR-031); RBAC against the canonical role set (FR-036) is enforced server-side on every state transition  
**Scale/Scope**: Target deployment up to ~50 stores per tenant, ~500k active SKUs per tenant, ~200k serials per tenant in stock, ~5k inventory mutations/day per store at peak

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The repository constitution (`.specify/memory/constitution.md`) is the unmodified placeholder template — no concrete principles have been ratified for this project. The gate therefore has no enforceable rules to evaluate and **passes trivially**. No violations to record in Complexity Tracking.

If/when a real constitution is ratified, re-run `/speckit.analyze` to validate this plan against it.

## Project Structure

### Documentation (this feature)

```text
specs/001-inventory-management/
├── plan.md              # This file
├── spec.md              # Feature specification (already exists)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── openapi.yaml     # Phase 1 output — HTTP contract for the inventory service
├── checklists/
│   └── requirements.md  # From /speckit.specify
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
backend/
├── pyproject.toml
├── alembic.ini
├── alembic/
│   └── versions/                      # one migration per logical schema slice
└── src/
    └── pos_inventory/
        ├── main.py                    # FastAPI app factory, routers wired here
        ├── core/
        │   ├── config.py              # settings (env-driven)
        │   ├── db.py                  # SQLAlchemy engine + session
        │   ├── tenancy.py             # tenant_id resolution + scoping
        │   ├── auth.py                # role check dependencies (FR-036)
        │   ├── events.py              # event emission (FR-007)
        │   └── audit.py               # immutable audit-entry writer (FR-031)
        ├── domain/
        │   ├── inventory/             # balances, FIFO cost layers (FR-026, FR-035)
        │   ├── serials/               # serial lifecycle (FR-008–FR-012)
        │   ├── lots/                  # lot capture + FIFO by receive date (FR-037)
        │   ├── purchase_orders/       # PO state machine + receiving (FR-001–FR-007)
        │   ├── returns/               # customer returns + dispositions (FR-013–FR-016, FR-018)
        │   ├── rmas/                  # vendor RMAs (FR-017, FR-018)
        │   ├── counts/                # count sessions + variance (FR-019–FR-024)
        │   ├── transfers/             # transfers + in-transit (FR-027–FR-029)
        │   └── locations/             # site/location/bin hierarchy (FR-025)
        ├── api/
        │   ├── v1/
        │   │   ├── purchase_orders.py
        │   │   ├── receipts.py
        │   │   ├── serials.py
        │   │   ├── returns.py
        │   │   ├── rmas.py
        │   │   ├── counts.py
        │   │   ├── transfers.py
        │   │   ├── locations.py
        │   │   ├── inventory.py       # balances + lookup-by-serial/lot
        │   │   └── pos_intake.py      # offline reconciliation endpoint (FR-034)
        │   └── schemas/               # Pydantic models (request/response)
        └── persistence/
            ├── models/                # SQLAlchemy ORM models
            └── repositories/          # query helpers (per aggregate)

backend/tests/
└── unit/
    ├── domain/
    │   ├── inventory/
    │   ├── serials/
    │   ├── purchase_orders/
    │   ├── returns/
    │   ├── counts/
    │   └── transfers/
    └── api/                           # request-validation/role-gating unit tests

frontend/pos/
├── package.json
├── vite.config.ts
└── src/
    ├── app/                           # routes, layout
    ├── features/
    │   ├── purchase-orders/
    │   ├── receiving/                 # serial/lot capture UI
    │   ├── sales/                     # serial selection at sale (FR-010)
    │   ├── returns/
    │   ├── counts/                    # counting UI w/ optional system-qty hide (FR-022)
    │   ├── transfers/
    │   └── inventory-lookup/
    ├── lib/
    │   ├── api.ts                     # generated/typed client
    │   ├── offline-queue.ts           # local queue for non-serialized sales (FR-034)
    │   └── auth.ts
    └── tests/                         # Vitest unit tests
```

**Structure Decision**: Web-application layout — a single backend service (`backend/`) and one POS web client (`frontend/pos/`). Backend is internally organized into `domain/` (pure inventory logic and state machines), `api/` (FastAPI routers + Pydantic schemas), and `persistence/` (SQLAlchemy models + per-aggregate repositories). PostgreSQL schemas mirror the domain folders to keep migrations and ownership clear. The POS client is feature-folder organized to match the user stories in the spec.

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
