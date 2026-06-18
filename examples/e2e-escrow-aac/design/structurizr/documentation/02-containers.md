# Containers (C4 L2)

**Architecture style:** Hexagonal per bounded context; orchestration for escrow state changes, choreography via domain events within the same JVM.

## Design principles

- DB-per-context; no foreign keys across contexts
- Idempotency for all money-moving commands
- Domain invariants enforced inside aggregates

## Cross-cutting decisions

- Seller owns SellerId, Email, DisplayName and is the source of truth for seller data (Shared Kernel import only for read-only Id).
- Order owns OrderId and references SellerId; it depends on Seller via Customer/Supplier relationship.
- Escrow owns EscrowId and depends on OrderId; it uses synchronous Java calls to OrderRepository.
- IdempotencyKey from shared kernel is stored inside Escrow aggregate to guarantee exactly-once settlement.

![Containers](embed:Containers)
