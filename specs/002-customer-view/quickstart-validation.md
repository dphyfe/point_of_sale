# Quickstart Validation — Customer View (002)

This document maps each numbered step in [`quickstart.md`](quickstart.md) to a
concrete `curl`/`HTTPie` invocation and the exact assertions a maintainer should
verify by eye or with `jq`. All commands assume:

* `BASE=http://localhost:8000/v1`
* `POS_INVENTORY_AUTH_BYPASS=true` is set on the backend.
* `H="-H X-Dev-Tenant:00000000-0000-0000-0000-000000000001 -H X-Dev-User:00000000-0000-0000-0000-000000000099 -H X-Dev-Roles:Admin,Marketing,Store_Manager,Cashier,Customer_Service"`

> The role list is a superset that exercises every endpoint; production clients
> only carry the roles their JWT grants.

## Step 0 — Seed templates

```sh
http POST $BASE/message-templates $H \
  code=pickup_ready name="Pickup ready" channel=sms purpose=transactional \
  body_template='Hi {{customer.first_name}}, ready at {{pickup.location}}.'

http POST $BASE/message-templates $H \
  code=receipt_copy name="Receipt copy" channel=email purpose=transactional \
  subject_template='Your receipt for {{transaction.id}}' \
  body_template='Thanks {{customer.first_name}} — your total was {{transaction.total}}.'
```

**Assert**: each request returns 201 with a stable `id`.

## Step 1 — Search (US1)

```sh
http GET "$BASE/customers?q=smith&limit=10" $H
```

**Assert**: `200`; body has `items[]` length ≤ 10 and `total >= len(items)`.
Each item exposes `id`, `display_name`, `state`.

## Step 2 — Profile + history (US2)

```sh
CID=$(http GET "$BASE/customers?q=smith&limit=1" $H | jq -r '.items[0].id')
http GET "$BASE/customers/$CID" $H
http GET "$BASE/customers/$CID/history?limit=25" $H
http GET "$BASE/customers/$CID/history/return/<txn_id>" $H
```

**Assert**: profile body includes `lifetime_spend`, `visit_count`,
`average_order_value`, `last_purchase_at`. History body items are reverse
chronological by `occurred_at` and include `kind`, `id`, `total|refund_total`.

## Step 3 — Edit + concurrency (US3)

```sh
VER=$(http GET "$BASE/customers/$CID" $H | jq -r '.version')
http PUT "$BASE/customers/$CID" $H If-Match:$VER \
  contact_type=individual primary_phone=5125551234

# Replay with stale If-Match — should 409.
http --check-status PUT "$BASE/customers/$CID" $H If-Match:$VER contact_type=individual
```

**Assert**: first request returns `200` with `version` incremented; second
returns `409` with `code=stale_version`.

## Step 4 — Audit + merge (US3)

```sh
http GET "$BASE/customers/$CID/audit" $H
http POST "$BASE/customers/$CID/merge" $H \
  survivor_id=$CID merged_away_id=<dup_id> performed_by=<user> summary='dedup demo'
```

**Assert**: audit list includes the `merged_into` change-kind row; subsequent
`GET /customers/<dup_id>` redirects (or returns merged state) to the survivor.

## Step 5 — Send + retry message (US4)

```sh
http POST "$BASE/customers/$CID/messages" $H \
  channel=email purpose=transactional to_address=test@example.com \
  template_code=receipt_copy related_transaction_kind=sale \
  related_transaction_id=<txn_id> client_request_id=$(uuidgen)

http GET "$BASE/customers/$CID/messages" $H
http POST "$BASE/customer-messages/<message_id>/retry" $H
```

**Assert**: send returns `201` with an `id`; the message appears in `GET
/messages` with `status` in {`queued`,`sent`}; retry on a `failed`/`bounced`
message returns `204`.

## Step 6 — Consent (US5)

```sh
http GET "$BASE/customers/$CID/consent" $H
http POST "$BASE/customers/$CID/consent" $H \
  channel=email purpose=marketing event_kind=opt_out source=pos
http GET "$BASE/customers/$CID/consent" $H
```

**Assert**: matrix updates to show `email/marketing → opted_out`; history
gains a row with `event_kind=opt_out`, `source=pos`. Subsequent attempt to
send a marketing-email template returns `403` with `code=consent_required`.

## Pass criteria

A clean walkthrough with all assertions met against a freshly migrated +
seeded environment qualifies the build for release.
