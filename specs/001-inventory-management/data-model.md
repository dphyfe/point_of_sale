# Data Model — POS Inventory Management

Schemas are PostgreSQL schemas; one per logical domain. Every business table carries `tenant_id UUID NOT NULL` and is row-filtered by RLS (R4). Timestamps are `timestamptz`. Money is `numeric(14,4)`. Quantities are `numeric(14,3)` to support fractional units (e.g., weight) where future SKU policy allows.

Validation rules and state transitions below trace directly to functional requirements (FR-xxx) and clarification answers (Q1–Q5).

---

## Schema `inv` — locations, products, serials, lots, balances, ledger, cost layers

### `inv.site`
- `id` UUID PK
- `tenant_id` UUID
- `code` text, unique per tenant
- `name` text

### `inv.location`
- `id` UUID PK
- `tenant_id` UUID
- `site_id` UUID → `inv.site.id`
- `code` text, unique per (tenant, site)
- `name` text
- `kind` enum: `front | backroom | warehouse | bin | virtual_in_transit`
- `parent_location_id` UUID nullable → `inv.location.id` (for bin within a location)

> One reserved per-tenant `virtual_in_transit` location holds in-transit qty for transfers (R2/FR-028).

### `inv.sku`
- `id` UUID PK
- `tenant_id` UUID
- `code` text, unique per tenant
- `name` text
- `category` text nullable
- `vendor_id` UUID nullable → `po.vendor.id`
- `serial_policy` enum: `non_serialized | serialized | lot_tracked` (FR-008)
- `default_unit_cost` numeric(14,4) nullable
- `price` numeric(14,4) (for sale; informational here — owned by POS sales feature)

**Validation**:
- Switching `serial_policy` from `non_serialized` to `serialized` while any `inv.balance.on_hand > 0` exists for the SKU is rejected unless an `Admin` confirms a backfill plan (matches spec edge case).

### `inv.serial`
- `id` UUID PK
- `tenant_id` UUID
- `sku_id` UUID → `inv.sku.id`
- `serial_value` text
- `state` enum: `in_stock | reserved | sold | returned | scrapped | rma_pending | rma_closed` (FR-012)
- `current_location_id` UUID nullable → `inv.location.id` (null when not at a physical location, e.g., sold; `virtual_in_transit` when on transfer)
- `unit_cost` numeric(14,4) (captured at receipt; serves R2 / FR-035 for serialized)
- `received_receipt_id` UUID → `po.receipt_line.id`

**Constraints**:
- `UNIQUE (tenant_id, sku_id, serial_value)` (R1, FR-009).
- `CHECK (sku_id has serial_policy = 'serialized')` enforced by trigger (FR-008 + FR-009).

**State transitions** (FR-011/FR-012/FR-018):

```text
in_stock → reserved → sold → returned → in_stock | scrapped | rma_pending → rma_closed
in_stock → rma_pending → rma_closed         (vendor RMA without prior sale)
in_stock → scrapped                         (damage at receive/transfer)
```

### `inv.lot`
- `id` UUID PK
- `tenant_id` UUID
- `sku_id` UUID → `inv.sku.id`
- `lot_code` text
- `expiry_date` date nullable (recorded; not enforced in v1 per Q5)
- `received_at` timestamptz (drives FIFO-by-receive-date for lots, FR-037)
- `received_receipt_line_id` UUID → `po.receipt_line.id`

**Constraints**:
- `UNIQUE (tenant_id, sku_id, lot_code)`.
- SKU must have `serial_policy = 'lot_tracked'`.

### `inv.balance` (projection)
- PK `(tenant_id, sku_id, location_id)`
- `on_hand` numeric(14,3)
- `reserved` numeric(14,3)
- `available` numeric(14,3)  *(generated: on_hand − reserved)*

> Maintained transactionally by the same write that inserts into `inv.ledger` (R2).

### `inv.ledger` (append-only, source of truth — FR-031)
- `id` UUID PK
- `tenant_id` UUID
- `occurred_at` timestamptz
- `actor_user_id` UUID
- `sku_id` UUID
- `location_id` UUID  (use `virtual_in_transit` for transfer in-flight rows)
- `qty_delta` numeric(14,3)  (signed)
- `unit_cost` numeric(14,4)  (post-FIFO consumption cost for outbound; receipt cost for inbound)
- `serial_id` UUID nullable
- `lot_id` UUID nullable
- `source_kind` enum: `po_receipt | sale | sale_offline_intake | customer_return | vendor_rma_ship | transfer_ship | transfer_receive | count_adjustment | manual_adjustment`
- `source_document_id` UUID
- `client_intake_id` UUID nullable  (R3 idempotency for offline sales)

**Constraints**:
- `UNIQUE (tenant_id, client_intake_id)` partial index `WHERE client_intake_id IS NOT NULL` (R3).
- No row may be updated or deleted; enforced by trigger (FR-031).

### `inv.cost_layer` (projection)
- `id` UUID PK
- `tenant_id` UUID
- `sku_id` UUID
- `location_id` UUID
- `received_at` timestamptz
- `qty_remaining` numeric(14,3)
- `unit_cost` numeric(14,4)
- `source_receipt_id` UUID

> Created on receipt; consumed FIFO by `received_at` on outbound (R1, FR-035). Not used for `serialized` SKUs (cost lives on `inv.serial`).

### `inv.adjustment`
- `id` UUID PK, `tenant_id`, `actor_user_id`, `reason_code` text, `notes` text, `posted_at`
- Backs `count_adjustment` and `manual_adjustment` ledger rows (FR-024, FR-031).

---

## Schema `po` — vendors, purchase orders, receipts

### `po.vendor`
- `id` UUID PK, `tenant_id`, `code` (unique per tenant), `name`, `terms_default` text, `contact_json` jsonb.

### `po.purchase_order`
- `id` UUID PK, `tenant_id`, `number` (unique per tenant), `vendor_id`
- `ship_to_location_id` UUID → `inv.location.id`
- `state` enum: `draft | submitted | approved | sent | receiving | closed | cancelled` (FR-002)
- `terms` text, `notes` text
- `created_by`, `created_at`, `approved_by`, `approved_at`, `closed_at` timestamps/users

**Transitions** (FR-002, FR-003, FR-036):

```text
draft → submitted → approved → sent → receiving → closed
draft | submitted | approved → cancelled       (Store Manager or Admin only)
```

### `po.purchase_order_line`
- `id` UUID PK, `tenant_id`, `purchase_order_id`
- `sku_id`, `ordered_qty`, `unit_cost`, `expected_date`
- Derived: `received_qty`, `backordered_qty` (= ordered − received, ≥ 0)

### `po.receipt`
- `id` UUID PK, `tenant_id`, `purchase_order_id`
- `received_by`, `received_at`, `receiving_location_id`

### `po.receipt_line`
- `id` UUID PK, `tenant_id`, `receipt_id`, `purchase_order_line_id`, `received_qty`, `unit_cost`
- For `serialized` SKUs: requires N rows in `po.receipt_serial` matching `received_qty` (FR-009).
- For `lot_tracked` SKUs: requires `lot_code` (and optional `expiry_date`) on the line (FR-037).

### `po.receipt_serial`
- `(receipt_line_id, serial_value)` — drives `inv.serial` insertion at post time.

**Validation rules**:
- Posting a receipt is only allowed when `purchase_order.state ∈ {approved, sent, receiving}` (FR-004).
- `received_qty ≤ ordered_qty * (1 + over_receive_tolerance)` per line (FR-005); over-tolerance writes a `receipt_line.tolerance_overage_qty` rather than failing.
- Posting a serialized line with a duplicate or already-known serial fails atomically (R1, FR-009).
- Posting any receipt closes the line if `received_qty + tolerance_overage = ordered_qty`; closes the PO when all lines are closed (FR-002).

---

## Schema `ret` — customer returns

### `ret.customer_return`
- `id` UUID PK, `tenant_id`, `number` (unique per tenant)
- `original_sale_id` UUID nullable (null = no-receipt return; gated by Q4 default policy)
- `cashier_user_id`, `manager_approver_user_id` nullable, `posted_at`
- `refund_method` enum: `original_tender | store_credit | cash_in_drawer` (no-receipt default forces `store_credit` per FR-014).

### `ret.customer_return_line`
- `id` UUID PK, `tenant_id`, `customer_return_id`
- `sku_id`, `qty`
- `serial_id` nullable (required for serialized SKUs — FR-011)
- `lot_id` nullable (required for lot-tracked SKUs — FR-037)
- `reason_code` text (required — FR-015)
- `disposition` enum: `return_to_stock | open_box | damage | vendor_rma` (required — FR-015)
- `target_location_id` UUID  (auto-resolved by disposition — FR-016)

**Posting**: Writes one `inv.ledger` row per line into the disposition's target location (or a "damage" pseudo-location for `damage`); updates serial state (FR-018) — `returned` for `return_to_stock | open_box`, `scrapped` for `damage`, `rma_pending` for `vendor_rma`.

---

## Schema `rma` — vendor RMAs

### `rma.vendor_rma`
- `id` UUID PK, `tenant_id`, `number`, `vendor_id`, `originating_purchase_order_id` nullable
- `state` enum: `open | shipped | closed` (FR-017)
- `created_by`, `shipped_by`, `closed_by` and timestamps

### `rma.vendor_rma_line`
- `id` UUID PK, `tenant_id`, `vendor_rma_id`, `sku_id`, `qty`, `unit_credit_value` numeric(14,4)
- `serial_id` nullable, `lot_id` nullable
- `customer_return_line_id` nullable (link back when the RMA was triggered by a customer return)

**Transitions**: `open → shipped → closed`. Shipping writes outbound `inv.ledger` rows from the holding location; closing updates serial states to `rma_closed` (FR-018) and records vendor credit value computed via R2/FR-035.

---

## Schema `cnt` — count sessions and variance

### `cnt.count_session`
- `id` UUID PK, `tenant_id`, `name`
- `scope_kind` enum: `full_store | by_location | by_category | by_vendor | by_sku_list` (FR-019)
- `scope_filter` jsonb (concrete values for the chosen scope)
- `hide_system_qty` bool (FR-022)
- `state` enum: `open | counting | review | approved | cancelled`
- `created_by`, `approved_by`, timestamps

### `cnt.count_session_snapshot` (R7)
- `(session_id, sku_id, location_id)` PK
- `system_qty_at_open` numeric(14,3)
- `system_value_at_open` numeric(14,4)  (computed via FIFO/serial cost — FR-035)

### `cnt.count_assignment`
- `(session_id, user_id, location_id)` triplets defining who counts what (FR-020).

### `cnt.count_entry`
- `id` UUID PK, `session_id`, `sku_id`, `location_id`, `counted_qty`, `counter_user_id`, `counted_at`, `serial_value` nullable, `lot_code` nullable.

**Approval** (FR-024): On `review → approved`, the system computes per-(sku, location):
```
variance_qty   = counted_qty − (system_qty_at_open + Δmovements_during_session)
variance_value = variance_qty × unit_value(FR-035)
```
For each non-zero `variance_qty`, an `inv.adjustment` is created and one `inv.ledger` row of `source_kind = count_adjustment` is written.

---

## Schema `xfr` — transfers

### `xfr.transfer`
- `id` UUID PK, `tenant_id`, `number`
- `source_location_id`, `destination_location_id`, `reason` text
- `state` enum: `draft | shipped | received | cancelled`
- `created_by`, `shipped_by`, `received_by`, timestamps

### `xfr.transfer_line`
- `id` UUID PK, `tenant_id`, `transfer_id`, `sku_id`, `qty`
- For serialized SKUs, must have N entries in `xfr.transfer_serial` (FR-029).

### `xfr.transfer_serial`
- `(transfer_line_id, serial_id)` explicit serial pin.

**Posting** (FR-028, FR-029):
- `ship`: writes outbound ledger from source, inbound ledger into the per-tenant `virtual_in_transit` location; updates each transferred serial's `current_location_id` to `virtual_in_transit`.
- `receive`: writes outbound ledger from `virtual_in_transit`, inbound ledger into destination; updates serials' `current_location_id` to destination.

A daily integrity check (SC-008) verifies for every serial: `state ∈ {sold, returned, scrapped, rma_closed}` OR exactly one ledger trace puts it at exactly one `current_location_id`.

---

## Schema `audit` — non-quantity audit entries

### `audit.audit_entry`
- `id` UUID PK, `tenant_id`, `actor_user_id`, `occurred_at`
- `target_kind` text  (e.g., `purchase_order`, `vendor_rma`, `count_session`, `transfer`, `customer_return`, `sku_policy_change`, `config_change`)
- `target_id` UUID
- `action` text  (e.g., `state_transition`, `cancel`, `approve`, `policy_change`, `config_update`)
- `before_json` jsonb
- `after_json` jsonb

> Append-only; no UPDATE or DELETE permission for application role (FR-031).

---

## Schema `outbox` — event emission (R6)

### `outbox.event`
- `id` UUID PK, `tenant_id`, `event_type` text, `occurred_at`, `payload` jsonb, `delivered_at` nullable.

> Inserted in the same transaction as the business write. Worker drains and POSTs to tenant webhook(s).

---

## Cross-cutting validation summary (traceability)

| Rule | Source |
|---|---|
| Receipt-line serial count must equal received qty | FR-009 |
| Sale line serial must be `in_stock` at the selling location | FR-010 |
| Return line serial must be in a returnable state and previously sold | FR-011 |
| Lot capture required at receive and at sale for `lot_tracked` | FR-037 |
| FIFO consumption on every outbound for non-serialized/lot-tracked | FR-035 |
| Per-tenant role membership checked at every state-transition endpoint | FR-036 |
| Outbox row written in same tx as PO create/approve/receipt | FR-007, R6 |
| `inventory_ledger` rows immutable | FR-031 |
| `client_intake_id` unique per tenant for offline sales | FR-034, R3 |
| Daily serial single-location integrity check | SC-008 |
