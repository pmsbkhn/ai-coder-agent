# Test Cases — Escrow

> Acceptance cases for `techspec-escrow.md`. Approved cases with an oracle file are **locked** (the Coder implements to pass them, may not edit them). Format: `TC-<CTX>-NN [Title]: setup → action → assert`.

## Domain invariant cases (guard clauses in the Aggregate Root)

**TC-ESC-01 [[AC-05] Open escrow for placed order]**

Given an in‑memory OrderRepository containing a PLACED order O1 with amount 150, when EscrowService.open(O1) is invoked, then an EscrowId is returned and the EscrowRepository contains one Escrow with status PENDING and amount 150.

_Oracle:_ `src/test/java/escrow/DomainOpenEscrowTest.java`

**TC-ESC-02 [[AC-06] Release escrow to seller on order completion (idempotent)]**

Given a PENDING escrow E1 linked to order O1 that is COMPLETED, when EscrowService.release(E1, idemKey) is invoked twice with the same IdempotencyKey, then the first call moves status to RELEASED and the second call is a no‑op; final status remains RELEASED.

_Oracle:_ `src/test/java/escrow/DomainReleaseEscrowIdempotentTest.java`

**TC-ESC-03 [[AC-07] Refund escrow to buyer on order cancellation (idempotent)]**

Given a PENDING escrow E2 linked to order O2 that is CANCELLED, when EscrowService.refund(E2, idemKey) is invoked twice with the same IdempotencyKey, then the first call moves status to REFUNDED and the second call is a no‑op; final status remains REFUNDED.

_Oracle:_ `src/test/java/escrow/DomainRefundEscrowIdempotentTest.java`

**TC-ESC-04 [[AC-08] Reject release on non‑PENDING escrow]**

Given an escrow in RELEASED status, when EscrowService.release(escrowId, idemKey) is invoked, then DomainException with code ESCROW_INVALID_STATE is thrown and status remains RELEASED.

_Oracle:_ `src/test/java/escrow/DomainReleaseInvalidStateTest.java`

## Fitness functions (architecture rules)

**TC-ESC-05 [[NFR-01] Escrow state transition latency <200ms (benchmark)]**

A micro‑benchmark runs 10 000 releases on a pre‑created PENDING escrow and asserts that the 95th percentile duration is below 200 ms.

