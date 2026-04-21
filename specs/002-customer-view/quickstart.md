# Quickstart — POS Customer View

This walks the happy path for the five user stories using the API contract in `contracts/openapi.yaml`. All requests carry `Authorization: Bearer <jwt>` whose claims include `tenant_id`, `roles[]`, `visibility_scope`, and `assigned_site_ids[]`.

Conventions:
- Replace `{api}` with the deployed base URL (e.g., `https://api.example.com/v1`).
- Replace UUIDs with values from your tenant's seed data.

## 0. Seed (one-time, Admin)

A few message templates so US4 has something to send:

```http
POST {api}/message-templates                 # Marketing or Admin
{ "code": "pickup_ready", "name": "Pickup ready",
  "channel": "sms", "purpose": "transactional",
  "body_template": "Hi {{customer.first_name}}, your order {{transaction.ticket_id}} is ready for pickup at {{pickup.location_name}}." }

POST {api}/message-templates
{ "code": "marketing_spring",  "name": "Spring promo",
  "channel": "email", "purpose": "marketing",
  "subject_template": "Spring deals for you, {{customer.first_name}}",
  "body_template": "..." }
```

## 1. Story 1 — Find a customer fast (Cashier / Customer Service)

Search by partial last name, by phone fragment (any punctuation), and by ticket id:

```http
GET {api}/customers?q=smit&page=1&page_size=25
GET {api}/customers?q=(512)%20555-12&page_size=10
GET {api}/customers?q=TKT-000123       # resolves the customer attached to that sale
```

Apply filters (city + last purchase in last 30 days):

```http
GET {api}/customers?city=Austin&last_purchase_from=2026-03-22
```

Open a profile:

```http
GET {api}/customers/{customer_id}      # 307 redirect if merged → follow Location
```

## 2. Story 2 — View a customer's full purchase history (Cashier / Support / Returns)

List history (paginated, reverse-chronological, sourced from existing inventory transaction tables):

```http
GET {api}/customers/{customer_id}/history?page=1&page_size=25
```

Filter to washers bought at Store-01 in the last year:

```http
GET {api}/customers/{customer_id}/history
  ?store_id={store_01}&from=2025-04-21&sku_id={washer_sku_id}
```

Drill into a sale (line items, serial numbers, fulfillment location):

```http
GET {api}/customers/{customer_id}/history/sale/{transaction_id}
```

Start a return from this sale (forwards to existing returns workflow):

```http
POST {api}/returns                     # existing inventory-feature endpoint
{ "source_transaction_id": "{transaction_id}", "lines": [ ... ] }
```

Email a copy of the receipt (records a transactional message in the timeline):

```http
POST {api}/customers/{customer_id}/messages
{ "channel": "email", "template_code": "receipt_copy",
  "related_transaction_id": "{transaction_id}", "related_transaction_kind": "sale",
  "client_request_id": "<uuid>" }
```

## 3. Story 3 — Create and maintain customer profiles (Cashier / Customer Service / Manager)

Create a customer at checkout (idempotent on `client_request_id`):

```http
POST {api}/customers
{ "client_request_id": "<uuid>",
  "contact_type": "individual",
  "first_name": "Jamie", "last_name": "Rivera",
  "primary_phone": "(512) 555-0142",
  "preferred_channel": "sms",
  "tags": ["new"] }
```

Edit (optimistic concurrency via `If-Match`):

```http
PUT {api}/customers/{customer_id}
If-Match: 1
{ "contact_type": "individual",
  "first_name": "Jamie", "last_name": "Rivera",
  "email": "jamie@example.com",
  "primary_phone": "(512) 555-0142" }
# 409 stale_version if another user already saved.
```

Read field-level audit (Manager+):

```http
GET {api}/customers/{customer_id}/audit
```

Deactivate (cannot be attached to new sales; history preserved):

```http
POST {api}/customers/{customer_id}/deactivate
```

Merge a duplicate (Manager+; atomic, tombstones the merged-away):

```http
POST {api}/customers/{survivor_id}/merge
{ "merged_away_id": "{duplicate_id}", "summary": "Same person, two profiles" }
# Subsequent GET on duplicate_id → 307 to survivor_id
```

## 4. Story 4 — Send one-off messages (Cashier / Customer Service)

Templated transactional SMS (consent gate is synchronous):

```http
POST {api}/customers/{customer_id}/messages
{ "client_request_id": "<uuid>",
  "channel": "sms",
  "template_code": "pickup_ready",
  "related_transaction_id": "{sale_id}",
  "related_transaction_kind": "sale",
  "merge_overrides": { "pickup.location_name": "Front counter" } }
# 201 with status="queued"; outbox worker hands off to provider.
```

Free-text email (transactional purpose):

```http
POST {api}/customers/{customer_id}/messages
{ "channel": "email",
  "subject": "Quick follow-up",
  "body": "Hi Jamie — wanted to confirm your appointment tomorrow at 3pm." }
```

Marketing email blocked when not opted in:

```http
POST {api}/customers/{customer_id}/messages
{ "channel": "email", "template_code": "marketing_spring" }
# → 403 { "code": "consent_required" }
```

Read the timeline filtered to SMS:

```http
GET {api}/customers/{customer_id}/messages?channel=sms
```

Retry a failed send:

```http
POST {api}/customer-messages/{message_id}/retry
# → 202 Re-queued
```

(Provider asynchronously calls back to `/v1/customer-messages/callbacks/{provider}` with HMAC; status events are appended.)

## 5. Story 5 — Manage templates and consent (Marketing / Admin)

Disable a template (soft-disable):

```http
DELETE {api}/message-templates/{template_id}
```

Record a consent event from the POS (e.g., associate captured opt-in at register):

```http
POST {api}/customers/{customer_id}/consent
{ "channel": "sms", "purpose": "marketing",
  "event_kind": "opted_in", "source": "pos",
  "note": "Verbal confirmation at register" }
```

Read current consent matrix + history:

```http
GET {api}/customers/{customer_id}/consent
# Response includes:
# {
#   "current": { "email_marketing": "opted_in", "sms_marketing": "opted_out", ... },
#   "history": [ ... ConsentEvent[] ordered desc ... ]
# }
```

## 6. Smoke checklist (per Success Criteria)

- **SC-001** Customer search returns first page in < 5 s on the seeded 50k customer dataset for any of: name fragment, phone fragment, email fragment, loyalty id, ticket id.
- **SC-002** Returns clerk can start a return on a historical sale in ≤ 3 clicks (`History → row → Start return`).
- **SC-003** History totals reconcile with the underlying inventory transactions: `SELECT SUM(total) FROM history(customer_x) MUST EQUAL SELECT SUM(total) FROM existing_sales WHERE customer_id = x AND status='completed'`.
- **SC-004** After merge: `GET duplicate_id → 307 → survivor_id` and `history(survivor)` ⊇ history(duplicate) ∪ history(survivor).
- **SC-005** A marketing send to an un-opted-in customer returns `403 consent_required` and produces no `msg.message` row.
- **SC-006** Each `Message` accumulates a `status_history` ending in `delivered | bounced | failed` within the provider's expected callback window.
- **SC-007** With the messaging provider intentionally unreachable, `POST /sales` (existing inventory endpoint) latency is unchanged and returns 200; `POST /customers/{id}/messages` still returns 201 with `status=queued`.
- **SC-008** Every action above produces a row in either `cust.profile_change`, `cust.merge`, `consent.event`, `msg.message_status_event`, or the existing `audit.entry` table.
- **SC-009** First page of `/history` for a customer with 1,000+ transactions returns in < 2 s.
- **SC-010** "Create at checkout" path (POST /customers + attach to in-progress sale) completes in < 30 s for a trained associate.
