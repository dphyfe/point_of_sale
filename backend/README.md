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
# 1. Start Postgres 16 (uses docker-compose at the repo root).
docker compose up -d db

# 2. Install backend deps + run migrations.
cd backend
pip install -e .[dev]
alembic upgrade head
```

Copy `.env.example` to `.env` and tweak as needed (the default DSN matches the
docker-compose service).

## Run

```pwsh
# Dev mode: bypass JWT, accept X-Dev-* headers from the frontend.
$env:POS_INVENTORY_AUTH_BYPASS = "true"
uvicorn pos_inventory.main:app --reload --port 8000
```

## Seed dev/staging inventory

```pwsh
# Local dev (uses POS_INVENTORY_AUTH_BYPASS=true as the safety gate).
python -m pos_inventory.scripts.seed_dev --confirm

# Re-runs are safe (idempotent ON CONFLICT DO NOTHING). To wipe and re-seed:
python -m pos_inventory.scripts.seed_dev --confirm --reset

# Cloud / one-off task (must explicitly opt in):
$env:POS_INVENTORY_ALLOW_SEED = "true"
python -m pos_inventory.scripts.seed_dev --confirm `
    --tenant-id 00000000-0000-0000-0000-000000000001 `
    --sku-count 500
```

Creates 1 site (`STORE-01`), 3 locations (`BACKROOM`, `FRONT`, `IN-TRANSIT`),
and `--sku-count` SKUs (default 500) with realistic merchandising fields
(`upc`, `department`, `brand`, `price`) and stocked `BACKROOM` balances posted
through the real ledger writer.

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
