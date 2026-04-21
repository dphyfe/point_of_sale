# pos_inventory backend

Multi-tenant POS inventory service: FastAPI + SQLAlchemy 2 (sync, psycopg3)
+ PostgreSQL 16 with row-level security.

## Required env vars

All settings use the prefix `POS_INVENTORY_`.

| Var | Default | Purpose |
|-----|---------|---------|
| `POS_INVENTORY_DB_DSN` | `postgresql+psycopg://postgres:postgres@localhost:5432/pos_inventory` | SQLAlchemy DSN. |
| `POS_INVENTORY_JWT_PUBLIC_KEY` | unset | RS256 public key for verifying API JWTs. |
| `POS_INVENTORY_JWT_AUDIENCE` | `pos-inventory` | Expected audience claim. |
| `POS_INVENTORY_AUTH_BYPASS` | `false` | When `true`, accept `X-Dev-Tenant`, `X-Dev-User`, `X-Dev-Roles` headers (dev only). |
| `POS_INVENTORY_OUTBOX_WEBHOOK_URL` | unset | Tenant webhook endpoint for the outbox worker. |
| `POS_INVENTORY_OVER_RECEIVE_TOLERANCE_PCT_DEFAULT` | `0` | Default tolerance when `inv.tenant_config` is unset. |

## Setup

```pwsh
cd backend
pip install -e .[dev]
alembic upgrade head
```

## Run

```pwsh
uvicorn pos_inventory.main:app --reload --port 8000
```

## Background workers

```pwsh
python -m pos_inventory.workers.outbox_worker
```

## Daily integrity job

```pwsh
python -m pos_inventory.scripts.check_serial_single_location
```

Exits non-zero if any serial is at more than one location (SC-008).

## Tests

```pwsh
cd backend
pytest -q
```

Tests are unit-only and use in-memory fakes (no live DB required).

## Migrations

Migrations live in `alembic/versions/`. Numbered `0001`–`0009` cover the
foundational schemas, inventory ledger, US1–US5 entities, and tenant config.
Each table that holds tenant data has RLS forced and a `tenant_isolation`
policy keyed off the `app.current_tenant` GUC, which the API sets per
request via `pos_inventory.core.tenancy.tenant_session`.

## OpenAPI drift check

```pwsh
python scripts/check_openapi.py
```

Compares the generated spec against `specs/001-inventory-management/contracts/openapi.yaml`.
