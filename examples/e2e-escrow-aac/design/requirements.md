# Requirements

> Binding contract for this change — the agent designs and tests to satisfy every `AC-*` and `NFR-*` below; it does not invent scope.

**Marketplace escrow payments core**

## User Stories

### US-01 — Seller onboarding _(priority: High)_
As a **marketplace operator**, I want **register sellers with a basic profile**, so that **orders can be attributed and paid out to a known seller**.

| AC | Criterion |
|---|---|
| AC-01 | Given a new seller email and display name, When the seller is registered, Then a seller is created in ACTIVE status and a seller identity is returned. |
| AC-02 | Given an email already used by an existing seller, When registration is attempted again, Then it is rejected and no new seller is created. |

### US-02 — Place an order _(priority: High)_
As a **buyer**, I want **place an order for an amount against a seller**, so that **I can purchase goods**.

| AC | Criterion |
|---|---|
| AC-03 | Given an active seller and a positive amount, When an order is placed, Then an order is created in PLACED status with an order identity and the amount. |
| AC-04 | Given an amount that is zero or negative, When an order is placed, Then it is rejected and no order is created. |

### US-03 — Escrow settlement _(priority: High)_
As a **marketplace operator**, I want **hold an order's funds in escrow and settle them on completion or cancellation**, so that **buyers and sellers are protected until the order resolves**.

| AC | Criterion |
|---|---|
| AC-05 | Given an order that has just been placed, When escrow is opened for the order, Then an escrow is created holding the order amount in PENDING status. |
| AC-06 | Given a PENDING escrow whose order is completed, When the escrow is released, Then the escrow moves to RELEASED and the held amount is credited to the seller. |
| AC-07 | Given a PENDING escrow whose order is cancelled, When the escrow is refunded, Then the escrow moves to REFUNDED and the held amount is returned to the buyer. |
| AC-08 | Given an escrow that is not in PENDING status, When a release is attempted, Then it is rejected and the escrow status is unchanged. |

## Non-functional requirements (ISO 25010)

| ID | Category | Metric | Measurement | Source | Scope |
|---|---|---|---|---|---|
| NFR-01 | Performance | p95 < 200ms for an escrow state transition | in-process domain-service benchmark | US-03 | BC-Escrow |
| NFR-02 | Reliability | escrow release/refund is idempotent on retry (no double settlement) | replay the same settlement command twice in a unit test | US-03 | BC-Escrow |

## Traceability (AC → locked test)

| AC | Covered by | Status |
|---|---|---|
| AC-01 | TC-SEL-01 🔒 | ✅ |
| AC-02 | TC-SEL-02 🔒 | ✅ |
| AC-03 | TC-ORD-01 🔒 | ✅ |
| AC-04 | TC-ORD-02 🔒 | ✅ |
| AC-05 | TC-ESC-01 🔒 | ✅ |
| AC-06 | TC-ESC-02 🔒 | ✅ |
| AC-07 | TC-ESC-03 🔒 | ✅ |
| AC-08 | TC-ESC-04 🔒 | ✅ |

## Traceability (NFR → test, advisory)

| NFR | Referenced by |
|---|---|
| NFR-01 | TC-ESC-05 |
| NFR-02 | TC-ESC-02 🔒, TC-ESC-03 🔒 |

