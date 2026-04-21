# Feature Specification: POS Inventory Management

**Feature Branch**: `001-inventory-management`  
**Created**: 2026-04-20  
**Status**: Draft  
**Input**: User description: "Inventory system on POS — purchase orders (create & receive), serial number enforcement, returns/RMA, inventory counts/reconciliation, multi-location management"

## Clarifications

### Session 2026-04-20

- Q: When a POS register loses connectivity to the inventory service, how should serialized vs non-serialized sales behave? → A: Block serialized sales while offline; non-serialized sales queue locally and reconcile on reconnect.
- Q: Which inventory costing method should drive the count variance value and RMA credit value? → A: FIFO cost layers — track received cost per layer and consume oldest first; serialized SKUs use their own actual receipt cost.
- Q: What canonical role set should authorize inventory state transitions in v1? → A: Fixed named roles — Cashier, Receiver, Inventory Clerk, Store Manager, Purchasing, Admin.
- Q: What is the shipped-default policy for no-receipt customer returns? → A: Store Manager approval required, refund as store credit only, and for serialized SKUs a serial lookup must locate a prior sale by this business; no-receipt returns are enabled by default with this policy.
- Q: What scope of lot tracking should v1 deliver for `lot-tracked` SKUs? → A: Capture lot (and optional expiry) at receive, require lot at POS sale, surface lot on returns/RMAs/counts/transfers, consume oldest lot first by receive date; expiry is recorded but does not block sales in v1.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create and Receive Purchase Orders (Priority: P1)

A purchasing clerk needs to replenish stock from a vendor. They draft a purchase order with line items, route it for approval, send it to the vendor, then later receive the goods (in full or in part) into a chosen inventory location so on-hand quantities reflect what just arrived on the dock.

**Why this priority**: Receiving is the primary way new inventory enters the system. Without it there is no trustworthy on-hand quantity and no foundation for any other inventory feature (counts, transfers, RMAs all assume goods have been received). This is the MVP.

**Independent Test**: Create a draft PO with two line items for a single vendor, walk it through approval and "sent" states, then receive a partial quantity at a chosen location. Verify (a) on-hand at that location increases by the received quantity, (b) backordered quantity equals ordered minus received, and (c) the PO state is `receiving` (not `closed`) until the remainder arrives.

**Acceptance Scenarios**:

1. **Given** a vendor exists and a user has the purchasing role, **When** the user creates a PO with vendor, ship-to location, line items (SKU, qty, unit cost, expected date), terms, and notes, **Then** the system saves the PO in `draft` state and assigns it a unique PO number.
2. **Given** a PO is in `draft`, **When** the user submits it and an authorized approver approves it, **Then** the PO advances through `submitted` → `approved` and becomes eligible for sending and receiving.
3. **Given** an approved PO that has been sent, **When** a receiver records receipt of fewer units than ordered for a line, **Then** the system records a partial receipt, increases on-hand at the selected receiving location, marks the remainder as backordered, and leaves the PO in `receiving`.
4. **Given** a PO line is fully received (within tolerance), **When** all lines on the PO are fully received, **Then** the PO advances to `closed` automatically.
5. **Given** a receipt is being recorded, **When** the received quantity exceeds the ordered quantity by more than the configured over-receive tolerance, **Then** the system blocks the receipt and surfaces the variance for resolution.
6. **Given** a PO is in any state other than `approved`, `sent`, or `receiving`, **When** a user attempts to receive against it, **Then** the system rejects the action.
7. **Given** a user without the cancel/approve role, **When** they attempt to cancel or approve a PO, **Then** the system denies the action and logs the attempt.
8. **Given** any PO event (creation, approval, receipt), **When** the event occurs, **Then** the system emits an event record that downstream integrations can consume.

---

### User Story 2 - Serial Number Enforcement (Priority: P1)

For high-value/serialized products (e.g., phones, laptops), the business must know exactly which physical unit is on the shelf, which one was sold to which customer, and which one came back. Receivers must capture serials at intake; cashiers must attach a serial at sale; returns must reference the original serial.

**Why this priority**: Serial enforcement is required to prevent shrinkage and fraud on the most expensive SKUs and to satisfy warranty and RMA workflows. Without it, returns and RMAs (Story 3) cannot be trusted, and counts (Story 4) will not reconcile for serialized SKUs. It must ship alongside receiving (Story 1) for serialized SKUs to be sellable at all.

**Independent Test**: Configure one SKU as `serialized`. Receive 3 units against a PO and confirm the system refuses to post the receipt until exactly 3 distinct serials are entered. Sell one of those serials at POS and confirm it cannot be sold again. Attempt a return at POS using a serial that was never sold and confirm it is rejected.

**Acceptance Scenarios**:

1. **Given** a SKU configured as `non-serialized`, `serialized`, or `lot-tracked`, **When** the receiving or sale flow runs for that SKU, **Then** the system applies the matching serial/lot policy and skips serial entry only for `non-serialized`.
2. **Given** a PO line for a `serialized` SKU with received quantity N, **When** the receiver attempts to post the receipt, **Then** the system requires exactly N distinct, previously-unknown serials and refuses to post if the count or uniqueness check fails.
3. **Given** a sale of a `serialized` SKU at POS, **When** the cashier adds the line, **Then** the system requires selection or scan of an in-stock serial at the selling location and refuses to complete the sale without one.
4. **Given** a serial has lifecycle state `sold`, **When** any user attempts to add the same serial to another sale line, **Then** the system rejects the action.
5. **Given** a customer return for a `serialized` SKU, **When** the cashier processes the return, **Then** the system requires a serial that was previously sold and is not currently in `returned`, `scrapped`, or `RMA closed` state.
6. **Given** a serial exists in the system, **When** a user looks it up, **Then** the system returns its full lifecycle history (in-stock → reserved → sold → returned/scrapped/RMA pending → RMA closed) including timestamps, locations, and related documents (PO, sale, return, RMA).

---

### User Story 3 - Returns & RMAs (Priority: P2)

Customers bring back items they bought (with or without a receipt); some of those items go back on the shelf, some go to an open-box bin, some are damaged, and some need to be sent back to the vendor on an RMA. Staff must process all of these without thinking about ledger mechanics.

**Why this priority**: Returns are an everyday POS operation but they depend on receiving (Story 1) and serial enforcement (Story 2) being in place to be trustworthy. Vendor RMAs are lower frequency than customer returns but high financial value, so they belong here rather than later.

**Independent Test**: Process a customer return tied to a prior sale: choose reason "defective" and disposition "send to vendor RMA". Verify the item is removed from sellable on-hand, a vendor RMA document is created and linked to the original PO and serial (if serialized), and the serial moves to `RMA pending`. Then mark the RMA `shipped` and `closed` and verify the serial reaches `RMA closed`.

**Acceptance Scenarios**:

1. **Given** a customer presents an item with the original sale receipt, **When** the cashier starts a return, **Then** the system pre-fills line items from that sale and requires a reason code and disposition per line.
2. **Given** a customer presents an item without a receipt, **When** the cashier starts a no-receipt return, **Then** the system applies the default no-receipt rules (Store Manager approval, refund as store credit only, prior-sale serial lookup required for serialized SKUs) before allowing posting.
3. **Given** a return line has a disposition (return to stock / open-box / damage / vendor RMA), **When** the return is posted, **Then** the system applies the inventory adjustment to the correct location and quality state automatically with no further user input.
4. **Given** any return line is for a `serialized` SKU, **When** the return is posted, **Then** the serial's lifecycle state is updated to match the disposition (e.g., `returned` for resale, `scrapped` for damage, `RMA pending` for vendor RMA).
5. **Given** items have been dispositioned to "vendor RMA", **When** a user creates a vendor RMA, **Then** the system links it to the originating PO and the specific items/serials and tracks it through `open` → `shipped` → `closed`.
6. **Given** a vendor RMA reaches `closed`, **When** the closing user posts the outcome, **Then** the linked serials advance to `RMA closed` and any credit/replacement is recorded against the vendor.

---

### User Story 4 - Inventory Counts & Reconciliation (Priority: P2)

Managers periodically verify that the on-hand quantity in the system matches what is physically in the store. They scope a count (full store, or a cycle count by location/category/vendor/SKU list), assign sections to staff, collect counted quantities (often via barcode), review variances, and post adjustments — with a full audit trail.

**Why this priority**: Counts protect the integrity of the inventory record over time. They depend on locations (Story 5) being modeled and on receiving (Story 1) producing the system quantities being checked.

**Independent Test**: Create a cycle-count session scoped to one category at one location, assign it to a user, count three items (one matching, one short, one over), review the variance report, and post. Verify each variance produces an adjustment transaction with user, timestamp, and reason recorded, and that on-hand balances now equal the counted values.

**Acceptance Scenarios**:

1. **Given** a manager wants to verify stock, **When** they create a count session, **Then** they can scope it as a full store count or a cycle count filtered by location, category, vendor, or SKU list, and assign items/locations to specific users.
2. **Given** a counter has been assigned items, **When** they open the counting UI, **Then** they can record counted quantity per item per location, scan barcodes to identify items, and (if the option is enabled) the system quantity is hidden during counting.
3. **Given** counting is complete, **When** the manager opens the variance report, **Then** they see, per item per location, the system quantity, the counted quantity, the unit and total value variance, and can drill into who counted what.
4. **Given** a variance report has been reviewed, **When** the manager approves the count session, **Then** the system generates one inventory adjustment transaction per item/location variance and records the user, timestamp, and reason on each.
5. **Given** a count session is in progress, **When** any user views the affected items, **Then** the audit trail clearly shows the session is open and identifies who is responsible.

---

### User Story 5 - Multiple Locations & Transfers (Priority: P2)

A business with multiple stores, a backroom, and bins within those locations needs to know what stock sits where and to move stock between locations under a controlled document so that nothing "disappears in transit".

**Why this priority**: Locations underpin Stories 1, 3, and 4 (receiving must target a location, returns must restock at the right location, counts are scoped by location). It is P2 only because a single-location business can ship without transfers; the moment a second location exists, this becomes blocking.

**Independent Test**: Define a site with two locations ("Front" and "Backroom"). Receive stock into Backroom, then create a transfer to Front for a serialized item: pick/ship at Backroom and receive at Front. Verify the serial is in-transit between the two events and lives at exactly one location at a time. Confirm POS at Front can sell it only after the receive step.

**Acceptance Scenarios**:

1. **Given** a business has multiple physical sites and bins, **When** an admin defines the inventory hierarchy, **Then** the system supports site/store → locations/bins (e.g., front, backroom, warehouse).
2. **Given** any SKU at any location, **When** a user views inventory, **Then** the system shows on-hand, reserved, and available quantities per SKU per location.
3. **Given** stock needs to move between locations, **When** a user creates a transfer document, **Then** they specify source location, destination location, items, quantities, and reason, and the document is saved in `draft`.
4. **Given** a transfer has been picked and shipped at the source, **When** the source posts the ship step, **Then** stock moves from source on-hand to in-transit; **When** the destination posts receive, **Then** stock moves from in-transit to destination on-hand.
5. **Given** a transfer line is for a `serialized` SKU, **When** the source ships, **Then** the user must explicitly select the serial(s); the serial is recorded as in-transit and is not present at any location until receive is posted.
6. **Given** POS is configured with a per-location selling restriction, **When** a cashier tries to sell an item not stocked at their location, **Then** the system blocks the sale (or shows availability at other locations, per configuration) and never allows a serial to be sold from a location it is not currently at.

---

### Edge Cases

- A receiver scans the same serial twice on the same PO line — system rejects the duplicate and keeps the running count accurate.
- A receiver scans a serial that already exists in the system (from a prior receipt) — system rejects it as not unique.
- A PO is partially received, then the vendor cancels the remainder — user must be able to close the PO short without forcing a phantom receipt; backordered quantity is cleared and an event is emitted.
- A customer returns a serialized item whose serial was never sold by this business — system rejects the return regardless of receipt presence (the no-receipt default still requires a prior-sale serial lookup).
- A count session is open on a SKU at a location and a sale of that SKU happens at the same location mid-count — the system must reflect the late sale in the variance calculation (either by locking sales during count or by adjusting the system quantity used for variance to a snapshot taken at session start; whichever the configuration specifies).
- A transfer is shipped but never received (lost in transit) — stock must remain visible as "in-transit" on a report and an authorized user must be able to write it off via an inventory adjustment with a reason code.
- Two cashiers attempt to sell the same serial at the same time at two registers — exactly one sale succeeds; the other is rejected with a clear message.
- A receipt is recorded against a PO line at a quantity within over-receive tolerance — the receipt posts, the PO line is marked complete, and the over-quantity is recorded as a tolerance overage (not as a separate exception requiring approval).
- A no-receipt return is attempted while no-receipt returns have been disabled by an `Admin` for that store — system rejects the action.
- An item's serial policy is changed from `non-serialized` to `serialized` while stock exists — system requires backfilling serials for existing on-hand or blocks the policy change until on-hand is zero (per configuration).
- A POS register loses connectivity mid-transaction — any `serialized` line in the basket is blocked until reconnect; `non-serialized` lines complete and queue locally, then reconcile to on-hand on reconnect with no double-decrement.

## Requirements *(mandatory)*

### Functional Requirements

**Purchase Orders**

- **FR-001**: System MUST allow authorized users to create a purchase order containing a vendor, ship-to location, one or more line items (SKU, ordered quantity, unit cost, expected date), payment/shipping terms, and free-text notes.
- **FR-002**: System MUST manage purchase order state through the lifecycle `draft` → `submitted` → `approved` → `sent` → `receiving` → `closed`, and MUST allow cancellation only from non-terminal states.
- **FR-003**: System MUST restrict approval and cancellation actions to users holding the corresponding authorization role and MUST log all such actions with user and timestamp.
- **FR-004**: System MUST allow receipts to be posted only against POs in `approved`, `sent`, or `receiving` state.
- **FR-005**: System MUST support partial receipts, configurable over-receive tolerance, and automatic creation/tracking of backordered quantities for unreceived units.
- **FR-006**: System MUST require the user to select an inventory location for every line on every receipt and MUST update on-hand and available quantities at that location immediately upon posting.
- **FR-007**: System MUST emit a structured event (consumable by downstream integrations) on PO creation, approval, and each receipt.

**Serial Number Enforcement**

- **FR-008**: System MUST allow each SKU to be configured with a serial policy of `non-serialized`, `serialized` (unique per unit), or `lot-tracked`.
- **FR-009**: System MUST require, for receipts of `serialized` SKUs, exactly one distinct, previously-unknown serial per unit received and MUST refuse to post the receipt otherwise.
- **FR-010**: System MUST require, for POS sales of `serialized` SKUs, that each sale line is bound to a specific in-stock serial at the selling location, and MUST prevent the same serial from being sold more than once.
- **FR-011**: System MUST require, for returns of `serialized` SKUs, that the supplied serial was previously sold by the business and is not currently in `returned`, `scrapped`, or `RMA closed` state.
- **FR-012**: System MUST maintain a serial lifecycle with the states `in-stock`, `reserved`, `sold`, `returned`, `scrapped`, `RMA pending`, and `RMA closed`, and MUST provide lookup by serial that returns the full state history with timestamps and linked documents.

**Returns & RMAs**

- **FR-013**: System MUST support customer returns linked to an original sale receipt, pre-filling sold lines for selection.
- **FR-014**: System MUST support no-receipt customer returns gated by configurable rules. The shipped default policy MUST require: (a) `Store Manager` approval, (b) refund issued as store credit only (no cash or card refund), and (c) for `serialized` SKUs, a serial lookup that locates a prior sale of that serial by this business; if no such prior sale is found, the system MUST reject the return. An `Admin` MAY relax any of these rules per store.
- **FR-015**: System MUST require a reason code and a disposition (e.g., return to stock, return to open-box stock, move to damage, send to vendor RMA) on every return line.
- **FR-016**: System MUST automatically apply the correct inventory adjustment (location and quality state) for each return line based on its disposition, with no additional user input required at posting time.
- **FR-017**: System MUST allow vendor RMAs to be created, linked to the originating PO and to specific items/serials, and tracked through `open` → `shipped` → `closed`.
- **FR-018**: System MUST update the serial lifecycle state of any serialized item involved in a customer return or vendor RMA to match the disposition and the RMA progress.

**Inventory Counts & Reconciliation**

- **FR-019**: System MUST allow authorized users to create count sessions scoped as a full-store count or a cycle count filtered by location, category, vendor, or SKU list.
- **FR-020**: System MUST allow assignment of count sessions (or sub-sections of them) to specific users.
- **FR-021**: System MUST provide a counting interface that captures counted quantity per item per location and supports barcode scanning to identify items.
- **FR-022**: System MUST provide a per-session option to hide the system quantity from counters during counting to prevent bias.
- **FR-023**: System MUST produce a variance report showing system quantity, counted quantity, and unit and total value variance per item per location, drillable to the counter.
- **FR-024**: System MUST, on manager approval of a count session, generate one inventory adjustment transaction per non-zero variance and record user, timestamp, and reason on each adjustment.

**Multiple Locations & Transfers**

- **FR-025**: System MUST represent an inventory hierarchy of site/store → locations/bins (e.g., front, backroom, warehouse).
- **FR-026**: System MUST track on-hand, reserved, and available quantities per SKU per location.
- **FR-027**: System MUST allow authorized users to create transfer documents containing source location, destination location, items, quantities, and reason.
- **FR-028**: System MUST move stock from source on-hand to in-transit when the source posts ship, and from in-transit to destination on-hand when the destination posts receive.
- **FR-029**: System MUST require explicit serial selection on the source-ship step for any `serialized` line on a transfer, and MUST guarantee that a given serial is at exactly one location (or in-transit) at any time.
- **FR-030**: System MUST be configurable, per POS register/location, to display stock by location and to restrict selling to the register's home location.

**Cross-Cutting**

- **FR-031**: System MUST record an immutable audit entry (user, timestamp, action, before/after) for every inventory-affecting action (receipts, sales, returns, RMAs, transfers, count adjustments, manual adjustments).
- **FR-032**: System MUST enforce role-based authorization on every state transition for POs, returns, RMAs, transfers, and count sessions.
- **FR-033**: System MUST keep on-hand and available quantities consistent under concurrent operations (no negative on-hand from a race; no double-sell of a serial).
- **FR-034**: When a POS register loses connectivity to the inventory service, the system MUST block all sales of `serialized` SKUs at that register until connectivity is restored, and MUST allow sales of `non-serialized` SKUs to be captured locally and reconciled to inventory automatically on reconnect (without operator intervention beyond normal sale completion).
- **FR-035**: System MUST value inventory using FIFO (First-In, First-Out) cost layers per SKU per location for `non-serialized` and `lot-tracked` SKUs: each receipt creates a layer at its received unit cost, and each outbound movement (sale, transfer-out, RMA, count shortage adjustment) consumes from the oldest available layer first. For `serialized` SKUs, the system MUST use the actual receipt unit cost of the specific serial as its unit value. The variance report (FR-023) and vendor RMA credit value (FR-017) MUST use these computed unit values.
- **FR-036**: System MUST recognize a fixed canonical role set — `Cashier`, `Receiver`, `Inventory Clerk`, `Store Manager`, `Purchasing`, `Admin` — and MUST pin every state transition referenced in FR-003 and FR-032 to one or more of these roles, as follows: PO create/submit = `Purchasing`; PO approve/cancel = `Store Manager` or `Admin`; PO receive = `Receiver` or `Inventory Clerk`; POS sale and customer return (with receipt) = `Cashier`; no-receipt return approval = `Store Manager`; vendor RMA create/ship/close = `Inventory Clerk` or `Store Manager`; transfer create/ship/receive = `Inventory Clerk` or `Store Manager`; count session create/assign/approve = `Store Manager`; count entry = any assigned user; manual inventory adjustment = `Store Manager` or `Admin`; configuration of tolerances, no-receipt rules, and per-location selling restrictions = `Admin`.
- **FR-037**: For SKUs with serial policy `lot-tracked`, the system MUST: (a) require capture of a lot code (and accept an optional expiry date) on every PO receipt line, (b) require selection of an in-stock lot at the selling location on every POS sale line, (c) surface the lot on every customer return, vendor RMA, transfer (source-ship and destination-receive), and count line, and (d) consume lots FIFO by receive date on outbound movements. Expiry, when present, MUST be recorded and viewable but MUST NOT block sales in v1.

### Key Entities *(include if feature involves data)*

- **Vendor**: Supplier the business buys from; identified by code/name; has terms, contact, and payment info; referenced by POs and vendor RMAs.
- **Site / Location / Bin**: Hierarchical place where inventory lives. A site contains locations; a location may contain bins. Inventory balances are kept per (SKU, location).
- **Product / SKU**: Sellable unit. Carries serial policy (`non-serialized`, `serialized`, `lot-tracked`), category, vendor, unit cost, and price.
- **Serial**: Unique identifier for one physical unit of a `serialized` SKU. Has lifecycle state, current location (or in-transit), and links to PO receipt, sale, return, and RMA documents that touched it.
- **Lot**: Grouping for `lot-tracked` SKUs identified by a lot code captured at receive, with optional expiry date; carried on receipts, sales, returns, RMAs, transfers, and counts; consumed FIFO by receive date.
- **Inventory Balance**: The current quantity of a SKU at a location, decomposed into on-hand, reserved, and available; for transfers, an additional in-transit pseudo-location applies.
- **Inventory Cost Layer**: For `non-serialized` and `lot-tracked` SKUs, an ordered FIFO layer at a (SKU, location) carrying remaining quantity and unit cost from the originating receipt; outbound movements consume oldest layers first. For `serialized` SKUs the unit cost lives directly on the Serial.
- **Purchase Order (PO)**: Vendor-bound order document with header (vendor, ship-to, terms, notes, state) and line items (SKU, ordered qty, unit cost, expected date, received qty, backordered qty).
- **PO Receipt**: Posting event that brings goods from a PO into a specific location; references PO lines, captured serials/lots, received quantity, and receiver.
- **Sale**: POS transaction; relevant here as the source of returns and as the consumer of serials at sale time.
- **Customer Return**: Document tied to a sale (or no-receipt) with lines carrying reason code, disposition, and (for serialized) the returning serial; drives automatic inventory adjustments.
- **Vendor RMA**: Document for returning goods to a vendor; linked to the originating PO and specific items/serials; states `open` → `shipped` → `closed`.
- **Transfer**: Document moving stock between two locations; carries source, destination, lines, reason, and ship/receive postings; for serialized lines, carries explicit serial selections.
- **Count Session**: Scoped count (full or cycle by location/category/vendor/SKU list) with assigned counters, captured counts, and variance report; on approval generates inventory adjustments.
- **Inventory Adjustment**: Atomic change to an inventory balance with user, timestamp, reason, and source document (count session, return disposition, RMA, transfer write-off, manual adjustment).
- **Audit Entry**: Immutable record of an inventory- or document-affecting action.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A purchasing clerk can create, approve, send, and post a first partial receipt for a 5-line PO end-to-end in under 5 minutes.
- **SC-002**: For SKUs flagged `serialized`, 100% of receipts and 100% of POS sales have a captured serial; 0 serials are sold more than once across any 90-day audit window.
- **SC-003**: 95% of customer returns are completed in under 90 seconds from start to printed receipt for the cashier.
- **SC-004**: After a count session is approved, on-hand quantities for the counted scope match the counted quantities in 100% of cases (i.e., adjustments fully reconcile system to counted).
- **SC-005**: Cycle counts of up to 200 line items can be created, assigned, counted, reviewed, and posted by a single manager and one counter in under 60 minutes.
- **SC-006**: For any SKU at any location, on-hand and available quantities are visible to a cashier within 2 seconds of opening the lookup, and reflect the most recent receipt, sale, return, transfer, or adjustment within 5 seconds of that event.
- **SC-007**: Every inventory-affecting action is retrievable from the audit trail with user, timestamp, and before/after values; spot-check audits find a 100% match between actions taken and audit entries.
- **SC-008**: Across all stores in a multi-location deployment, at no point can a serial appear at more than one location (or simultaneously at a location and in-transit) — verified by a daily integrity check returning zero violations.
- **SC-009**: Inventory shrinkage attributable to untracked movements (i.e., movements without a source document) drops to under 0.2% of inventory value per quarter once the system is in steady-state use.

## Assumptions

- The POS already has user accounts, role/permission management, and authentication; this feature consumes those rather than defining them.
- A product/SKU master with categories and vendor associations already exists or will be defined as part of an adjacent feature; this spec assumes such records are addressable.
- A single business may operate one or many sites; locations/bins are always at least one (a single-location deployment is supported as a degenerate case of the hierarchy).
- Currency, tax, and payment handling are owned by the broader POS sales feature; this spec only references unit cost on POs and does not define financial postings to a general ledger.
- Barcode scanning is supported by the POS hardware; the counting and receiving UIs accept scanned input identically to typed input.
- Over-receive tolerance and per-location selling restrictions are configurable by `Admin`; default values are conservative (zero over-receive tolerance, no per-location selling restriction). No-receipt return policy ships enabled with the default rules in FR-014 and is configurable per store by `Admin`.
- Downstream integrations (accounting, e-commerce, vendor EDI) consume the events emitted by this feature but are out of scope to define here.
- "Real-time" inventory updates mean within a few seconds of the source event under normal load, not strictly synchronous across all viewers.
