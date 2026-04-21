# Feature Specification: POS Customer View

**Feature Branch**: `002-customer-view`
**Created**: 2026-04-21
**Status**: Draft
**Input**: User description: "POS Customer View — a consolidated customer workspace inside the POS back office (and surfaced in the register UI where appropriate) that centralizes customer search, profile management, full purchase history (reusing existing Sales / Returns / Inventory transaction data), and one-off email/SMS messaging with consent tracking."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Find a customer fast (Priority: P1)

A store associate is at the register or back office and needs to pull up an existing customer using whatever the customer can give them — name, phone, email, loyalty ID, or a printed receipt number — and open the right profile in seconds.

**Why this priority**: Without reliable search, every other capability (history, messaging, profile edits) is unreachable. This is the entry point to the entire feature and is required at register pace.

**Independent Test**: Seed a realistic customer set and verify that typing a partial name, a phone fragment, an email fragment, a loyalty ID, or a receipt/ticket ID returns the expected customer at the top of the list, and that selecting the result opens that customer's profile.

**Acceptance Scenarios**:

1. **Given** the customer list contains 50,000 customers, **When** the associate types the first 4 characters of a customer's last name, **Then** matching customers appear within 2 seconds and the intended customer is visible in the first page of results.
2. **Given** the associate types a 7-digit fragment of a phone number with parentheses or dashes, **When** the search runs, **Then** the customer with that phone is returned regardless of the punctuation/spacing the associate typed.
3. **Given** two customers share the same first and last name, **When** the associate searches by that name, **Then** the result list shows distinguishing details (city, last purchase date, last 4 of phone, email) so the associate can pick the right one.
4. **Given** the associate pastes a receipt/ticket ID printed at the bottom of a receipt, **When** the search runs, **Then** the system returns the customer linked to that transaction (or a clear "no customer attached" result).
5. **Given** the associate applies the filter "Last purchase in the last 30 days" and sets city = "Austin", **When** the list refreshes, **Then** only customers matching both filters are shown and the result count is displayed.

---

### User Story 2 - View a customer's full purchase history (Priority: P1)

From a customer's profile, an associate, support user, or returns clerk needs to see every sale, return, and exchange that customer has made across the business, drill into the line items (including serial numbers for serialized products), and start a return directly from a historical receipt.

**Why this priority**: Purchase history is the primary reason staff open a customer profile (returns, warranty, "what did I buy last time?"). It is also the largest reuse of the existing Inventory + Sales data and must be tightly consistent with it.

**Independent Test**: Pick a customer with at least one sale, one return, and one exchange in the seeded data. Verify the history tab lists all three with correct totals, drill into a sale and confirm line items match the underlying sales transaction (including serials and store/location), and start a return from a historical receipt that successfully feeds the existing returns workflow.

**Acceptance Scenarios**:

1. **Given** a customer has past sales, returns, and exchanges across multiple stores, **When** the user opens the History tab, **Then** all transactions appear in reverse-chronological order with date/time, store, register, ticket ID, transaction type, total, payment method, and status.
2. **Given** a sale included a serialized product, **When** the user drills into that sale, **Then** the line items show product, quantity, unit price, discounts, tax, line total, the location it was fulfilled from, and the serial number(s).
3. **Given** the user is viewing a completed sale, **When** they choose "Start return" on a line, **Then** the existing returns workflow opens pre-populated with that line's product, quantity, price, and original transaction reference.
4. **Given** the user is viewing a completed sale, **When** they choose "Reprint receipt" or "Email receipt", **Then** the receipt is regenerated from the same source transaction and (for email) is sent to the customer's primary email and recorded in the messages timeline.
5. **Given** the customer has 500+ transactions, **When** the user filters history by date range, store, transaction type, minimum amount, or specific SKU, **Then** the list updates accordingly and shows the matching count.
6. **Given** the customer profile is open, **When** the user looks at the summary panel, **Then** they see lifetime spend, visit count, average order value, last purchase date, and last store visited, all computed from the same underlying transaction data.

---

### User Story 3 - Create and maintain customer profiles safely (Priority: P1)

Associates need to create new customer profiles quickly during checkout, customer service reps need to keep contact info current, and managers need confidence that edits are auditable and don't break links to past transactions.

**Why this priority**: Profile data quality is a prerequisite for both search (P1) and messaging (P2). Without safe edit/create, the customer list rots quickly.

**Independent Test**: Create a customer at checkout in under 30 seconds with name + phone + opt-in. Edit a different existing customer's email and address as a customer service rep, then confirm their entire prior purchase history is still attached and a field-level change log entry was recorded.

**Acceptance Scenarios**:

1. **Given** an associate is at checkout with no customer attached, **When** they choose "New customer" and enter name + phone, **Then** the profile is created, attached to the in-progress sale, and reachable via search immediately.
2. **Given** a customer service rep edits a customer's email and primary address, **When** they save, **Then** the changes are persisted, the customer's full purchase history remains attached, and a change-log entry records old value, new value, user, and timestamp.
3. **Given** a manager has restricted "tax ID" and "date of birth" to manager+ roles, **When** an associate opens the profile, **Then** those fields are either hidden or read-only for the associate.
4. **Given** a privileged user opens the change log, **When** they view a field's history, **Then** they see every change with old value, new value, user, and timestamp.
5. **Given** a customer is deactivated, **When** an associate searches for them, **Then** the customer appears flagged as inactive and cannot be attached to a new sale, but their history remains intact.
6. **Given** a manager identifies two duplicate customer profiles, **When** they merge them, **Then** all transactions from both profiles end up under the surviving customer, the merged-away customer is retained as a tombstone pointing to the survivor, and the merge action is recorded in the audit log.
7. **Given** an associate enters an invalid phone or email, **When** they try to save, **Then** the save is blocked with a clear validation message.

---

### User Story 4 - Send one-off messages to a customer (Priority: P2)

Staff need to send a one-off email or SMS from a customer's profile (e.g., "your special-order item is in", "your service appointment is tomorrow"), pick from a small set of approved templates or write a free-text note, and see the result in the customer's message timeline.

**Why this priority**: This is high-value but depends on P1 (find customer, view profile). It is the primary new write-side capability beyond profile edits.

**Independent Test**: From a customer profile with both email and SMS opt-in, send a templated "pickup ready" email and a free-text SMS. Confirm both appear in the timeline with delivery status, the user who sent them, and the channel.

**Acceptance Scenarios**:

1. **Given** the customer is opted in to SMS, **When** the user picks the "Pickup ready" template and chooses a related transaction, **Then** the message body is pre-populated using merge fields (customer first name, ticket ID, store name) and the user can preview it before sending.
2. **Given** the user is composing an SMS, **When** the body exceeds the SMS character limit, **Then** a character/segment counter is shown and the user is warned before sending.
3. **Given** the customer is **not** opted in for marketing email, **When** the user tries to send a marketing-tagged template, **Then** the send is blocked with an explanation, while transactional templates (e.g., receipt copy, order status) remain available where allowed.
4. **Given** a message has been sent, **When** the messaging provider reports delivered/bounced/failed, **Then** the message timeline reflects the latest status and the sender's identity is shown.
5. **Given** the messaging provider is unavailable, **When** a send is attempted, **Then** the failure is logged against the message record, the user sees a clear "delivery failed — retry?" state, and the rest of the POS continues to function normally.
6. **Given** the user opens the Messages tab, **When** they filter by channel (email vs SMS) or by template, **Then** the timeline updates to show only matching entries.

---

### User Story 5 - Manage messaging templates, opt-ins, and consent (Priority: P3)

A marketing or admin user needs to define which templates are available to staff, manage opt-in/opt-out flags, and ensure regulatory rules (consent, unsubscribe) are enforced consistently.

**Why this priority**: Required for compliant rollout but can ship after P1/P2 with a small initial template set and a basic opt-in toggle.

**Independent Test**: As an admin, add a new SMS template tagged "marketing", flip a customer's marketing-SMS opt-in off, and confirm staff cannot send that template to that customer; flip it back on and confirm the send succeeds.

**Acceptance Scenarios**:

1. **Given** an admin creates a new template tagged "marketing", **When** staff open the compose screen for a customer who is not opted in to marketing, **Then** that template is unavailable or visibly blocked.
2. **Given** a customer opts out via an unsubscribe link or in-store request, **When** staff open the profile, **Then** the relevant opt-in flag is off, the consent history shows when/how/where the change was made, and marketing sends are blocked.
3. **Given** an admin disables a template, **When** staff open compose, **Then** the disabled template no longer appears in the picker.

---

### Edge Cases

- A customer transacts as a guest (no profile attached). The receipt/ticket ID still resolves, but the search shows "no customer attached" and offers "Create profile from this sale".
- An associate searches with a string that matches 200+ customers. The list shows the first page with a clear total count and prompts the user to refine.
- A merged-away customer is referenced by an old bookmark or deep link. The system redirects to the surviving customer and shows a small "merged from …" indicator.
- A customer has both email and SMS opt-in off. Compose is disabled with an explanation and a quick link to update preferences (subject to role).
- A messaging provider returns "delivered" hours after send. The message status updates retroactively without resending.
- A customer's purchase history spans thousands of transactions. The history view paginates / lazy-loads and remains responsive.
- A historical sale was voided after the fact. It appears in the customer's history with a "voided" status and is not eligible for return.
- An associate at Store A has region-restricted visibility and tries to open a customer who has only ever transacted at Store B. The profile is either hidden or shown with reduced detail per policy.
- Two associates edit the same profile concurrently. The second save warns about a conflict and shows the latest values rather than silently overwriting.
- A customer's phone or email is changed; future messaging uses the new value, but historical messages still show the address they were sent to.

## Requirements *(mandatory)*

### Functional Requirements

#### Customer list & search

- **FR-001**: System MUST provide a paginated, sortable customer list with configurable columns (at minimum: name, phone, email, city, tags, last purchase date, total spend, last store visited, active/inactive).
- **FR-002**: System MUST provide a global search that supports partial, case-insensitive matches and ignores common punctuation/spacing in phone numbers (e.g., `(512) 555-1234` matches `5125551234`).
- **FR-003**: Search MUST match against name, phone, email, internal customer ID, external loyalty ID, and receipt/ticket ID.
- **FR-004**: System MUST provide filters for: tags, customer type (individual vs business), city/state, last purchase date range, total spend range, active vs inactive, and per-channel communication opt-in status.
- **FR-005**: When multiple customers match similar details, the list MUST surface disambiguating fields (e.g., city, last 4 of phone, email, last purchase date) on each row.
- **FR-006**: The list MUST display a result count and support pagination or virtualized scrolling for very large result sets.

#### Customer profile management

- **FR-007**: System MUST allow creating a new customer with a minimal required set (name OR company name, plus at least one contact method) directly from checkout and from the customer list.
- **FR-008**: System MUST support editing core profile fields: identification (internal ID, external loyalty/CRM IDs), personal (first/last or company, contact type), contact (primary phone, secondary phone, email, multiple typed addresses — billing/shipping/service), and preferences (preferred contact method, per-channel opt-in flags, language, marketing tags/segments).
- **FR-009**: System MUST validate phone and email format on save and enforce uniqueness rules where configured (e.g., email unique within tenant when present).
- **FR-010**: System MUST support role-based field-level edit and visibility rules so sensitive fields (e.g., tax ID, date of birth) can be restricted to specific roles.
- **FR-011**: System MUST record a field-level change log for every profile edit (old value, new value, user, timestamp) and expose it to privileged roles.
- **FR-012**: System MUST support deactivating a customer such that the customer cannot be attached to new sales but all historical links remain intact.
- **FR-013**: System MUST support a soft-delete or anonymization path that preserves transactional integrity (orders still reference a customer, even if anonymized).
- **FR-014**: System MUST allow privileged users to merge two customer profiles. After merge, all transactions and messages from both profiles MUST be reachable from the surviving profile, the merged-away profile MUST remain as a tombstone redirecting to the survivor, and the merge MUST be recorded in the audit log with both source IDs and the user.
- **FR-015**: System MUST detect concurrent edits to the same profile and prevent silent overwrites.

#### Purchase history (reuses existing Inventory / Sales / Returns data)

- **FR-016**: System MUST source purchase history from existing Sales, Returns, and related Inventory transaction records — not from a duplicated copy — so quantities, serials, and totals stay consistent with Inventory.
- **FR-017**: Each history row MUST display: date/time, store/site, register, ticket/receipt ID, transaction type (sale, return, exchange, service order), total, tax, payment method(s), and transaction status (completed, voided, refunded).
- **FR-018**: Drill-down on a transaction MUST display line items with product/SKU, description, quantity, unit price, discounts, tax, extended line total, fulfillment location, serial numbers for serialized items, and links to related POs or RMAs where applicable.
- **FR-019**: System MUST allow starting a return or exchange directly from a historical receipt; this MUST invoke the existing returns workflow with the original transaction reference and pre-populated lines.
- **FR-020**: System MUST allow reprinting and emailing a receipt from any historical sale; emailed receipts MUST be recorded in the customer's message timeline.
- **FR-021**: System MUST allow filtering and sorting of history by date range, store, transaction type, minimum amount, and specific SKU.
- **FR-022**: System MUST display per-customer summary metrics — lifetime spend, visit count, average order value, last purchase date, last store visited — computed from the same underlying transaction data.
- **FR-023**: History MUST paginate or lazy-load for customers with hundreds or thousands of transactions and remain responsive.

#### Messaging (email & SMS)

- **FR-024**: System MUST allow sending a one-off email or SMS from a customer profile, choosing from approved templates or composing a free-text message.
- **FR-025**: Templates MUST support merge fields including at least: customer first/last name, last order date, ticket/order ID, SKU names from a referenced transaction, store name, and pickup location.
- **FR-026**: Compose MUST support a preview before sending and MUST show an SMS character/segment counter when composing SMS.
- **FR-027**: System MUST persist every outbound message as a `CustomerMessage` record linked to the customer, the sender, the channel, the template (if any), and optionally a related transaction.
- **FR-028**: System MUST display messages chronologically on a Messages tab within the profile, with filters by channel and by template.
- **FR-029**: System MUST integrate with an abstract messaging provider for email and SMS, accept asynchronous status callbacks, and update each message with the latest status (queued, sent, delivered, bounced, failed) and timestamp.
- **FR-030**: System MUST enforce per-channel and per-purpose opt-in: marketing-tagged templates MUST be blocked for customers who are not opted in to that channel for marketing, while transactional messages (e.g., receipt copy, order status, pickup ready) remain available where legally allowed.
- **FR-031**: System MUST record a consent history per channel: when, how, and where (POS / online portal / support) opt-in was granted or withdrawn.
- **FR-032**: System MUST surface unsubscribe handling so that an unsubscribe event from the messaging provider updates the customer's opt-in flags and is reflected in consent history.
- **FR-033**: Failure of the messaging provider MUST NOT block other POS operations. Failed messages MUST be visible on the timeline with a retry action available to authorized roles.

#### Permissions, privacy, and audit

- **FR-034**: System MUST provide role-based access for: viewing customer profiles, editing contact details, viewing purchase history, sending messages, viewing message content, exporting customer lists, performing merges, and viewing audit/consent history.
- **FR-035**: System MUST support optional region/store scoping so that, when configured, lower-privilege roles see only customers who have transacted at their assigned store(s), while HQ roles see globally.
- **FR-036**: Sensitive fields MUST be maskable or hidden for lower-privilege roles based on configuration.
- **FR-037**: System MUST log every profile edit, merge, deactivation, message send, and consent change with the acting user and timestamp, and expose the log to privileged roles.
- **FR-038**: System MUST provide mechanisms to support data subject requests (view, export, delete/anonymize a customer's personal data) without orphaning prior transactions.

### Key Entities *(include if feature involves data)*

- **Customer**: A person or company the business transacts with. Holds identification (internal customer ID, external loyalty/CRM IDs), personal info (name or company name, contact type), contact info (phones, email, multiple typed addresses), preferences (preferred channel, per-channel opt-in flags, language, tags/segments), and lifecycle state (active, inactive, anonymized). Linked 1:many to historical Sales / Returns transactions (which already exist in the inventory feature) and to Messages.
- **CustomerAddress**: A typed address (billing / shipping / service) belonging to a Customer. A Customer may have many.
- **CustomerConsent**: A per-channel, per-purpose record of opt-in/out events (channel, purpose, state, source, user/system that recorded it, timestamp). A Customer has a history of these.
- **CustomerProfileChange**: An audit entry capturing field-level edits to a Customer (field, old value, new value, user, timestamp).
- **CustomerMerge**: A record of a merge action capturing the surviving customer, the merged-away customer (tombstone), the user, and the timestamp.
- **CustomerMessage**: A single outbound message to a Customer (channel — email or SMS, template ref or free-text, body snapshot, sender, related transaction ref optional, provider message ID, status history, timestamps).
- **MessageTemplate**: A reusable message body with channel, purpose tag (marketing vs transactional), supported merge fields, and enabled/disabled state.
- **Sales transaction / Return / Exchange / Service order**: **Existing** entities owned by the inventory + sales features. The Customer View feature references them but does not redefine them. Each gains an optional reference to a Customer.
- **Serial number / SKU / Location / Site / Purchase order / RMA**: **Existing** inventory entities, surfaced as read-only context inside transaction drill-downs in the customer history view.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A trained associate can locate a target customer using any single typical input (name fragment, phone fragment, email fragment, loyalty ID, or receipt ID) and open their profile in **under 5 seconds** on the standard customer dataset, in 95% of attempts.
- **SC-002**: From a customer profile, a returns clerk can start a return on a historical sale in **under 3 clicks/taps** and the resulting return uses the same line data as the original sale (no manual re-entry).
- **SC-003**: 100% of customer purchase history rows reconcile exactly with the underlying Sales / Returns / Inventory transaction records (no orphans, no duplicates, no totals drift) when audited.
- **SC-004**: After a merge, 100% of transactions and messages from the merged-away customer are reachable from the surviving customer, and any deep link to the merged-away customer redirects correctly.
- **SC-005**: Zero marketing-tagged messages can be sent to customers who are not opted in for that channel in production sampling and in automated test runs.
- **SC-006**: Every outbound message has a final delivery status (delivered, bounced, failed, or explicitly retried) recorded against it within the provider's expected callback window in 99% of cases.
- **SC-007**: Failures of the messaging provider do not degrade core POS sales/returns flows — sales and returns continue to complete normally during a simulated provider outage.
- **SC-008**: 100% of profile edits, merges, deactivations, message sends, and consent changes appear in the audit/consent log with user and timestamp.
- **SC-009**: For a customer with 1,000+ historical transactions, the history tab loads its first page and remains interactive in **under 2 seconds**.
- **SC-010**: A new associate can create a customer at checkout (name + phone + opt-in) in **under 30 seconds** without leaving the sale.

## Assumptions

- The existing inventory/sales feature already owns canonical Sales, Returns, Exchange, Serial, SKU, Location, Site, PO, and RMA entities; the Customer View feature **references** them rather than redefining them.
- Sales/return transactions either already carry an optional customer reference or can be extended to do so; the customer feature relies on that link to assemble purchase history.
- Email and SMS sending is handled by an abstract external "messaging provider" — the spec does not pick a specific vendor.
- Multi-tenant isolation rules (one tenant = one business) already established by the inventory feature also apply to customers, messages, consent, and audit records.
- Role definitions (Associate, Customer Service, Manager, Admin, etc.) already exist at the platform level; this feature defines which of them can do what, but does not introduce a new RBAC system.
- Region/store scoping for visibility is configurable per tenant and defaults to "global" until configured otherwise.
- Marketing vs transactional classification of a template is determined by the tagging on the template, not by the message body.
- Bulk marketing campaigns and segmentation tooling beyond simple tags are **out of scope** for this feature.
- Customer-facing self-service portals (where customers manage their own profile) are **out of scope**; this spec is staff-facing, with consent events from external sources merely being recorded.
- A formal loyalty/points engine is **out of scope**; the spec only stores the loyalty ID for lookup and display.
