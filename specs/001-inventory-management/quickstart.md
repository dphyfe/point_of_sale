# Quickstart — POS Inventory Management

This walks the happy path for the five user stories using the API contract in `contracts/openapi.yaml`. All requests carry `Authorization: Bearer <jwt>` whose claims include `tenant_id` and the role(s) listed.

Conventions:
- Replace `{api}` with the deployed base URL (e.g., `https://api.example.com/v1`).
- Replace UUIDs and codes with values from your tenant's seed data.

## 0. Seed (one-time, Admin)

Create a site and two locations:

```http
POST {api}/sites          # Admin
{ "code": "store-01", "name": "Store 01" }

POST {api}/locations      # Admin
{ "site_id": "<site-id>", "code": "BACKROOM", "name": "Backroom",  "kind": "backroom" }
POST {api}/locations
{ "site_id": "<site-id>", "code": "FRONT",    "name": "Front",     "kind": "front"    }
```

Three SKUs covering each policy:

```http
# non-serialized
POST {api}/skus { "code": "USB-C-1M", "name": "USB-C Cable 1m", "serial_policy": "non_serialized" }
# serialized
POST {api}/skus { "code": "PHONE-A1", "name": "Phone A1",       "serial_policy": "serialized" }
# lot-tracked
POST {api}/skus { "code": "BAT-AA-12", "name": "AA Battery 12-pk", "serial_policy": "lot_tracked" }
```

A vendor:

```http
POST {api}/vendors { "code": "VEND-001", "name": "Acme Distributors" }
```

## 1. Story 1 — Create and Receive a Purchase Order (Purchasing → Receiver)

Create:

```http
POST {api}/purchase-orders        # Purchasing
{
  "vendor_id": "<vendor-id>",
  "ship_to_location_id": "<backroom-id>",
  "lines": [
    { "sku_id": "<usb-c-id>", "ordered_qty": "100", "unit_cost": "1.20" },
    { "sku_id": "<phone-id>", "ordered_qty": "3",   "unit_cost": "450.00" },
    { "sku_id": "<bat-id>",   "ordered_qty": "50",  "unit_cost": "2.00" }
  ]
}
```

Submit → approve → send:

```http
POST {api}/purchase-orders/{id}/submit   # Purchasing
POST {api}/purchase-orders/{id}/approve  # Store Manager or Admin
POST {api}/purchase-orders/{id}/send     # Purchasing
```

Receive a partial shipment (note: serials required for the phone, lot required for the batteries):

```http
POST {api}/receipts                       # Receiver or Inventory Clerk
{
  "purchase_order_id": "<po-id>",
  "receiving_location_id": "<backroom-id>",
  "lines": [
    { "purchase_order_line_id": "<pol-usb>",   "received_qty": "60",  "unit_cost": "1.20" },
    { "purchase_order_line_id": "<pol-phone>", "received_qty": "2",   "unit_cost": "450.00",
      "serials": ["SN-AAA-001", "SN-AAA-002"] },
    { "purchase_order_line_id": "<pol-bat>",   "received_qty": "50",  "unit_cost": "2.00",
      "lot_code": "L-2026-04-A", "expiry_date": "2028-04-01" }
  ]
}
```

Verify:

```http
GET {api}/inventory/balances?location_id=<backroom-id>
GET {api}/purchase-orders/{po-id}    # state should be "receiving"; phone backordered_qty=1
```

## 2. Story 2 — Serial enforcement at sale and return

Sell one phone (handled by the surrounding POS sales feature; the inventory side validates the serial). Look it up after sale:

```http
GET {api}/serials/SN-AAA-001
# → state: "sold", history shows in_stock → reserved → sold
```

Try to sell the same serial again — POS sales call refuses (409). Then process a customer return for that exact serial:

```http
POST {api}/returns                            # Cashier (with-receipt)
{
  "original_sale_id": "<sale-id>",
  "lines": [
    { "sku_id": "<phone-id>", "qty": "1",
      "serial_value": "SN-AAA-001",
      "reason_code": "defective",
      "disposition": "vendor_rma" }
  ]
}
```

The serial is now `rma_pending`.

## 3. Story 3 — Vendor RMA the defective phone

```http
POST {api}/vendor-rmas                         # Inventory Clerk or Store Manager
{
  "vendor_id": "<vendor-id>",
  "originating_purchase_order_id": "<po-id>",
  "lines": [{ "sku_id": "<phone-id>", "qty": "1",
              "serial_value": "SN-AAA-001",
              "customer_return_line_id": "<return-line-id>" }]
}
POST {api}/vendor-rmas/{id}/ship               # serial -> tracked as shipped on RMA
POST {api}/vendor-rmas/{id}/close              # serial -> rma_closed
```

## 4. Story 4 — Cycle count + reconciliation

Create a session scoped to one location and one category, then submit entries:

```http
POST {api}/count-sessions                      # Store Manager
{ "name": "Cycle 2026-04-20 cables", "scope_kind": "by_location",
  "scope_filter": { "location_id": "<backroom-id>", "category": "cables" },
  "hide_system_qty": true }

POST {api}/count-sessions/{id}/entries         # any assigned user
[ { "sku_id": "<usb-c-id>", "location_id": "<backroom-id>", "counted_qty": "58" } ]
```

Review variance and post adjustments:

```http
GET  {api}/count-sessions/{id}/variance
POST {api}/count-sessions/{id}/approve         # Store Manager
```

Two USB-C cables short → one `count_adjustment` ledger row at FIFO cost; on-hand drops to 58.

## 5. Story 5 — Transfer to the front + serialized move

```http
POST {api}/transfers                           # Inventory Clerk or Store Manager
{
  "source_location_id": "<backroom-id>",
  "destination_location_id": "<front-id>",
  "reason": "shelf replenishment",
  "lines": [
    { "sku_id": "<usb-c-id>", "qty": "20" },
    { "sku_id": "<phone-id>", "qty": "1", "serials": ["SN-AAA-002"] }
  ]
}
POST {api}/transfers/{id}/ship                 # stock → virtual_in_transit
POST {api}/transfers/{id}/receive              # stock → front; serial current_location_id = front
```

Verify the serial moved exactly once:

```http
GET {api}/serials/SN-AAA-002
# → current_location_id = <front-id>; history shows ship + receive movements
```

## 6. Story 1 add-on — Offline POS reconciliation (FR-034)

While the POS is offline, the client enqueues envelopes locally. On reconnect:

```http
POST {api}/pos-intake/sales
[
  { "client_intake_id": "8e1c9f0a-...-1",
    "register_id": "<register-id>", "location_id": "<front-id>",
    "cashier_user_id": "<user-id>",
    "occurred_at": "2026-04-20T14:21:08Z",
    "lines": [ { "sku_id": "<usb-c-id>", "qty": "1" } ] }
]
```

Replaying the same envelope returns `409 already_processed` — safe to retry.

## What "done" looks like

- `GET /inventory/balances` shows the expected on-hand at every location after each step.
- `GET /serials/{value}` for any touched serial shows a single current location (or `null` for sold/scrapped/rma_closed) and a complete history.
- The `outbox.event` table contains rows for `purchase_order.created`, `purchase_order.approved`, and `receipt.posted` (R6, FR-007).
- `audit.audit_entry` contains state-transition rows for every approve/cancel/close/policy change touched above (FR-031).
