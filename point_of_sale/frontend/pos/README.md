# pos client (frontend)

React 18 + Vite 5 + TypeScript 5 POS client. Talks to `pos_inventory`
backend over `/v1`. Designed for in-store use with **offline-tolerant
non-serialized sales** and **online-required serialized sales**.

## Setup

```pwsh
cd frontend/pos
npm install
```

## Run

```pwsh
npm run dev
```

Vite serves on `http://localhost:5173` and proxies `/v1` to the backend.
Set `VITE_API_BASE` if the backend runs elsewhere.

## Tests

```pwsh
npm run test
```

Vitest + Testing Library + jsdom, with `fake-indexeddb` to exercise the
offline queue.

## Offline behavior

The offline queue (`src/lib/offline-queue.ts`):

1. Persists pending POS sale envelopes in IndexedDB (`pos_offline.pos_intake`).
2. Tracks `pos_last_online` in `localStorage`; `startOnlineHeartbeat()`
   pings `/healthz` every 15 s and updates the marker.
3. On transition to online, calls `drain()` which POSTs queued envelopes
   to `/v1/pos-intake/sales`.
4. Each envelope carries a `client_intake_id`. The backend uses a UNIQUE
   partial index on `inv.ledger.client_intake_id` so retried envelopes
   are idempotent (FR-026, FR-034).

Important rule (FR-012/030): **serialized sales are not enqueued offline**.
`useSale.submitSale` throws when offline + serialized so the cashier knows
to retry once connectivity returns.

## Project layout

- `src/app/` — top-level routes and shell.
- `src/features/` — one folder per user story (purchase-orders, receiving,
  sales, returns, counts, transfers, inventory-lookup).
- `src/lib/` — `api.ts`, `auth.ts`, `offline-queue.ts`.
- `src/tests/` and `src/features/**/__tests__/` — Vitest suites.
