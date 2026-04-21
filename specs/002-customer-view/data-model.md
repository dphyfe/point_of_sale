# Data Model — POS Customer View

Schemas are PostgreSQL schemas. Three new schemas (`cust`, `msg`, `consent`) plus a small extension to existing inventory transaction tables. Every business table carries `tenant_id UUID NOT NULL` and is row-filtered by RLS (R2). Timestamps are `timestamptz`. Money is `numeric(14,4)` (matches inventory). Free-text is `text`.

Validation rules and state transitions below trace directly to functional requirements (FR-xxx) and Phase-0 research items (Rn).

---

## Schema `cust` — customers, addresses, audit, merges

### `cust.customer`
- `id` UUID PK
- `tenant_id` UUID
- `client_request_id` UUID nullable (R10 idempotency)
- `external_loyalty_id` text nullable
- `external_crm_id` text nullable
- `contact_type` enum: `individual | company`
- `first_name` text nullable
- `last_name` text nullable
- `company_name` text nullable
- `primary_phone` text nullable        — display form
- `secondary_phone` text nullable      — display form
- `email` text nullable                — display form
- `preferred_channel` enum: `email | sms | none` (default `email`)
- `language` text nullable             — BCP-47 (e.g., `en-US`)
- `tags` text[] not null default '{}'  — marketing segments / arbitrary tags
- `tax_id` text nullable               — restricted field (FR-010)
- `date_of_birth` date nullable        — restricted field (FR-010)
- `state` enum: `active | inactive | merged | anonymized` (default `active`)
- `merged_into` UUID nullable → `cust.customer.id`  — tombstone target (R4)
- `version` int not null default 1     — optimistic concurrency (R5)
- `created_at` timestamptz not null
- `created_by_user_id` UUID
- `updated_at` timestamptz not null
- `updated_by_user_id` UUID
- — derived/maintained by trigger (R3) —
- `phone_normalized` text nullable     — E.164 form of `primary_phone` (digits-only fallback)
- `email_normalized` text nullable     — `lower(trim(email))`
- `display_name_lower` text nullable   — `lower(coalesce(first_name||' '||last_name, company_name))`
- `search_vector` tsvector             — composed over the three above + loyalty IDs

**Constraints**:
- `UNIQUE (tenant_id, client_request_id) WHERE client_request_id IS NOT NULL` (R10).
- `UNIQUE (tenant_id, lower(email)) WHERE email IS NOT NULL` (FR-009 — email uniqueness within tenant).
- `CHECK ((contact_type='individual' AND (first_name IS NOT NULL OR last_name IS NOT NULL)) OR (contact_type='company' AND company_name IS NOT NULL))` — FR-007 minimal-required.
- `CHECK (primary_phone IS NOT NULL OR email IS NOT NULL)` — FR-007 at least one contact method.
- `CHECK ((state <> 'merged') OR (merged_into IS NOT NULL))` — tombstone integrity (R4).

**Indexes**:
- `GIN (search_vector)` (R3).
- `btree (tenant_id, phone_normalized)` (R3).
- `btree (tenant_id, email_normalized)` (R3).
- `btree (tenant_id, lower(external_loyalty_id))` (R3).
- `btree (tenant_id, state)` (filter active/inactive).

**Triggers**:
- `BEFORE INSERT OR UPDATE` — recompute `phone_normalized`, `email_normalized`, `display_name_lower`, `search_vector` from current row values.

**State transitions** (FR-012, FR-013, FR-014):

```text
active → inactive                (deactivate; not assignable to new sales)
active → merged                  (only via cust.merge in same tx; sets merged_into)
inactive → active                (reactivate)
active → anonymized              (DSAR delete — clears PII fields, preserves id + tenant_id)
inactive → anonymized
```

A `merged` row is terminal — never edited again.

---

### `cust.customer_address`
- `id` UUID PK
- `tenant_id` UUID
- `customer_id` UUID → `cust.customer.id` (ON DELETE RESTRICT)
- `kind` enum: `billing | shipping | service`
- `is_default_for_kind` boolean default false
- `line1` text not null
- `line2` text nullable
- `city` text nullable
- `region` text nullable           — state/province
- `postal_code` text nullable
- `country` text not null          — ISO-3166 alpha-2
- `created_at` timestamptz not null
- `updated_at` timestamptz not null

**Constraints**:
- `UNIQUE (tenant_id, customer_id, kind) WHERE is_default_for_kind` — at most one default per kind.

---

### `cust.profile_change` (append-only, FR-011, R6)
- `id` UUID PK
- `tenant_id` UUID
- `customer_id` UUID
- `actor_user_id` UUID
- `occurred_at` timestamptz not null
- `field` text not null            — e.g., `email`, `primary_phone`, `tags[]`, `merge`
- `old_value` text nullable        — sensitive fields stored as `sha256:<hex>:last4=<…>`
- `new_value` text nullable        — same
- `change_kind` enum: `update | merge | deactivate | reactivate | anonymize`

**Constraints**: append-only — no `UPDATE` or `DELETE` allowed; enforced by a trigger that raises on those ops (mirrors `inv.ledger` pattern).

**Indexes**: `btree (tenant_id, customer_id, occurred_at DESC)`.

---

### `cust.merge` (audit of merge actions, R4)
- `id` UUID PK
- `tenant_id` UUID
- `survivor_id` UUID → `cust.customer.id`
- `merged_away_id` UUID → `cust.customer.id`
- `performed_by_user_id` UUID
- `occurred_at` timestamptz not null
- `summary` text nullable          — optional human note

**Constraints**:
- `CHECK (survivor_id <> merged_away_id)`.
- `UNIQUE (tenant_id, merged_away_id)` — a customer can only be merged away once.

---

## Schema `consent` — per-channel per-purpose consent

### `consent.event` (append-only ledger, FR-031, R7)
- `id` UUID PK
- `tenant_id` UUID
- `customer_id` UUID
- `channel` enum: `email | sms`
- `purpose` enum: `transactional | marketing`
- `event_kind` enum: `opted_in | opted_out`
- `source` enum: `pos | online_portal | support | provider_unsubscribe | import`
- `actor_user_id` UUID nullable    — null when source is `provider_unsubscribe`
- `occurred_at` timestamptz not null
- `note` text nullable

**Constraints**: append-only (trigger-enforced, same pattern as `cust.profile_change`).

**Indexes**: `btree (tenant_id, customer_id, channel, purpose, occurred_at DESC)`.

### `consent.state` (projection, R7)
- PK `(tenant_id, customer_id, channel, purpose)`
- `state` enum: `opted_in | opted_out | unset` (default `unset`)
- `updated_at` timestamptz
- `last_event_id` UUID → `consent.event.id`

> Maintained transactionally with each `consent.event` insert.

**Default behavior at send-time** (FR-030):
- Marketing: send is allowed only when `state = opted_in`.
- Transactional: send is allowed when `state IN ('opted_in', 'unset')` and blocked when `state = opted_out`.

---

## Schema `msg` — templates, messages, status, outbox

### `msg.template`
- `id` UUID PK
- `tenant_id` UUID
- `code` text not null              — e.g., `pickup_ready`
- `name` text not null
- `channel` enum: `email | sms`
- `purpose` enum: `transactional | marketing`
- `subject_template` text nullable  — required for email; null for SMS
- `body_template` text not null     — supports `{{ merge_field }}` placeholders
- `enabled` boolean default true
- `created_at`, `updated_at` timestamptz

**Constraints**: `UNIQUE (tenant_id, code)`.

**Supported merge fields** (validated at template save):
- `customer.first_name`, `customer.last_name`, `customer.company_name`, `customer.preferred_channel`
- `transaction.ticket_id`, `transaction.total`, `transaction.store_name`, `transaction.last_4_payment`
- `pickup.location_name`
- `business.name`, `business.support_phone`

### `msg.message`
- `id` UUID PK
- `tenant_id` UUID
- `client_request_id` UUID nullable (R10 idempotency)
- `customer_id` UUID → `cust.customer.id`
- `template_id` UUID nullable → `msg.template.id` (null = free-text send)
- `channel` enum: `email | sms`
- `purpose` enum: `transactional | marketing`   — derived from template.purpose at send time
- `to_address` text not null         — snapshot of email/phone used at send (FR audit context)
- `subject` text nullable            — rendered snapshot
- `body` text not null               — rendered snapshot
- `related_transaction_id` UUID nullable — soft reference to a sales/return/etc. row
- `related_transaction_kind` text nullable — e.g., `sale`, `return`
- `status` enum: `queued | sent | delivered | bounced | failed | retrying` (default `queued`) — denormalized "latest status"
- `provider` text nullable
- `provider_message_id` text nullable
- `sent_by_user_id` UUID
- `created_at`, `updated_at` timestamptz

**Constraints**:
- `UNIQUE (tenant_id, client_request_id) WHERE client_request_id IS NOT NULL` (R10).
- `CHECK ((channel='email' AND subject IS NOT NULL) OR channel='sms')` — emails require subject.

**Indexes**:
- `btree (tenant_id, customer_id, created_at DESC)` — Messages tab timeline.
- `btree (tenant_id, status)` — failed-message dashboards.

### `msg.message_status_event` (append-only, FR-029, R8)
- `id` UUID PK
- `tenant_id` UUID
- `message_id` UUID → `msg.message.id`
- `status` enum: same set as `msg.message.status`
- `occurred_at` timestamptz not null
- `provider_event_id` text nullable
- `error_code` text nullable
- `error_message` text nullable

**Constraints**: append-only (trigger-enforced).

### `msg.outbox` (transactional outbox, R8)
- `id` UUID PK
- `tenant_id` UUID
- `event_kind` enum: `customer_message.send | customer_message.retry`
- `payload` jsonb not null           — `{ "message_id": "..." }`
- `created_at` timestamptz default now()
- `dispatched_at` timestamptz nullable
- `attempts` int default 0
- `last_error` text nullable

> Inserted in the same DB transaction as `msg.message` insert. The messaging worker dispatches and updates `dispatched_at` / `attempts` / `last_error`.

---

## Extension to existing inventory tables (R1)

For each existing transaction table that may be associated with a customer, add:

| Table | Added column | FK | Index |
|---|---|---|---|
| `sales.sale_transaction` *(existing or to-be-added by sales feature)* | `customer_id UUID NULL` | → `cust.customer.id` | `btree (tenant_id, customer_id, occurred_at DESC)` |
| `ret.customer_return` | `customer_id UUID NULL` | → `cust.customer.id` | `btree (tenant_id, customer_id, occurred_at DESC)` |
| `ret.exchange` | `customer_id UUID NULL` | → `cust.customer.id` | `btree (tenant_id, customer_id, occurred_at DESC)` |
| `svc.service_order` *(if/when present)* | `customer_id UUID NULL` | → `cust.customer.id` | `btree (tenant_id, customer_id, occurred_at DESC)` |

> Notes:
> - All four columns are **nullable** so guest transactions remain valid (spec edge case "guest checkout").
> - The customer-history read path is a `UNION ALL` over these four sources, ordered by `occurred_at DESC`, joined to `inv.location` / `inv.site` for store/register names and to inventory line tables for drill-down.
> - "Start return" from history simply forwards to the existing returns workflow with the source transaction id and pre-populated lines (no logic re-implemented in this feature).

---

## Cross-cutting

- **Audit table** — reuse the existing `audit.entry` table for non-quantity actions (e.g., `customer.deactivated`, `customer.merged`, `template.disabled`, `message.retried`). Field-level customer edits remain in `cust.profile_change` for trivial per-field queries.
- **Outbox worker** — reuse the existing `audit.outbox` worker; add handlers for the new `customer_message.*` event kinds. (Implementation detail: a single worker dispatches both inventory events and customer-messaging events.)
- **Anonymization (FR-038)** — anonymizing a customer clears `first_name`, `last_name`, `company_name`, `primary_phone`, `secondary_phone`, `email`, `tax_id`, `date_of_birth`, `phone_normalized`, `email_normalized`, `display_name_lower`, `search_vector`; preserves `id`, `tenant_id`, `state='anonymized'`. All historical transactions remain attached and reachable by id.
