# Architecture Description

> System-level design for one change; reviewed by an architect before implementation. One AD spans one or more Tech Specs — **1 bounded context = 1 Tech Spec**. Detailed per-context design lives in the linked Tech Specs.

> 📋 Binding requirements & AC→test traceability: [`requirements.md`](requirements.md)

## Requirement
Marketplace escrow payments core
US-01 — Seller onboarding [High]
As a marketplace operator, I want register sellers with a basic profile, so that orders can be attributed and paid out to a known seller.
Acceptance criteria:
  - AC-01: Given a new seller email and display name, When the seller is registered, Then a seller is created in ACTIVE status and a seller identity is returned.
  - AC-02: Given an email already used by an existing seller, When registration is attempted again, Then it is rejected and no new seller is created.
US-02 — Place an order [High]
As a buyer, I want place an order for an amount against a seller, so that I can purchase goods.
Acceptance criteria:
  - AC-03: Given an active seller and a positive amount, When an order is placed, Then an order is created in PLACED status with an order identity and the amount.
  - AC-04: Given an amount that is zero or negative, When an order is placed, Then it is rejected and no order is created.
US-03 — Escrow settlement [High]
As a marketplace operator, I want hold an order's funds in escrow and settle them on completion or cancellation, so that buyers and sellers are protected until the order resolves.
Acceptance criteria:
  - AC-05: Given an order that has just been placed, When escrow is opened for the order, Then an escrow is created holding the order amount in PENDING status.
  - AC-06: Given a PENDING escrow whose order is completed, When the escrow is released, Then the escrow moves to RELEASED and the held amount is credited to the seller.
  - AC-07: Given a PENDING escrow whose order is cancelled, When the escrow is refunded, Then the escrow moves to REFUNDED and the held amount is returned to the buyer.
  - AC-08: Given an escrow that is not in PENDING status, When a release is attempted, Then it is rejected and the escrow status is unchanged.
Non-functional requirements:
  - NFR-01 [Performance] p95 < 200ms for an escrow state transition (measure: in-process domain-service benchmark; source: US-03; scope: BC-Escrow)
  - NFR-02 [Reliability] escrow release/refund is idempotent on retry (no double settlement) (measure: replay the same settlement command twice in a unit test; source: US-03; scope: BC-Escrow)

## Summary
Add seller onboarding, order placement, and escrow lifecycle with idempotent settlement and performance constraints.

## Goals
- Enable marketplace operators to register sellers
- Allow buyers to place orders against active sellers
- Hold funds in escrow and settle them safely

## Architecture style
Hexagonal per bounded context; orchestration for escrow state changes, choreography via domain events within the same JVM.

## Design principles
- DB‑per‑context; no foreign keys across contexts
- Idempotency for all money‑moving commands
- Domain invariants enforced inside aggregates

## Bounded-context map
graph LR
    Order --> Seller[Seller]
    Escrow --> Order[Order]

## Cross-cutting decisions
- Seller owns SellerId, Email, DisplayName and is the source of truth for seller data (Shared Kernel import only for read‑only Id).
- Order owns OrderId and references SellerId; it depends on Seller via Customer/Supplier relationship.
- Escrow owns EscrowId and depends on OrderId; it uses synchronous Java calls to OrderRepository.
- IdempotencyKey from shared kernel is stored inside Escrow aggregate to guarantee exactly‑once settlement.

## Non-functional requirements / constraints
- NFR-01: p95 < 200 ms for any escrow state transition (benchmark in‑process).
- NFR-02: Release and refund commands must be idempotent; replaying the same IdempotencyKey must not double‑settle.

## Ubiquitous Language (Glossary)
| ID | Term | Definition | Bounded Context | Aliases to avoid | Example |
|---|---|---|---|---|---|
| GL-01 | SellerId | StringIdentity representing a seller aggregate identifier. | Seller |  |  |
| GL-02 | OrderId | StringIdentity representing an order aggregate identifier. | Order |  |  |
| GL-03 | EscrowId | StringIdentity representing an escrow aggregate identifier. | Escrow |  |  |
| GL-04 | Money | Shared domain type for monetary amounts (BigDecimal, USD). | Shared Kernel |  |  |

## Bounded contexts (→ Tech Spec · Test Cases)
- **Seller** → [`techspec-seller.md`](techspec-seller.md) · tests [`testcases-seller.md`](testcases-seller.md) — Register new sellers and enforce unique email.
- **Order** → [`techspec-order.md`](techspec-order.md) · tests [`testcases-order.md`](testcases-order.md) — Place orders against active sellers and enforce positive amount.
- **Escrow** → [`techspec-escrow.md`](techspec-escrow.md) · tests [`testcases-escrow.md`](testcases-escrow.md) — Open escrow for placed orders and settle (release/refund) with idempotent guarantees.

## Context relationships (typed Context Map)
| ID | Upstream | Downstream | Kind | Mechanism | Notes |
|---|---|---|---|---|---|
| REL-01 | Order | Seller | Customer/Supplier | sync (Java call) |  |
| REL-02 | Escrow | Order | Customer/Supplier | sync (Java call) |  |

