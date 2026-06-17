# Tech Spec — Escrow

> **Classification:** Tier 1 / L2

## 1. Context & Scope
Open escrow for placed orders and settle (release/refund) with idempotent guarantees.

## 2. Requirements — Functional (FR)
- FR-05: Open escrow for a PLACED order, creating PENDING escrow holding the order amount.
- FR-06: Release a PENDING escrow when its order is COMPLETED, moving to RELEASED and crediting seller.
- FR-07: Refund a PENDING escrow when its order is CANCELLED, moving to REFUNDED and returning buyer funds.
- FR-08: Reject release/refund when escrow not in PENDING.

##    Requirements — Non-functional / SLO
- NFR-01: State transition latency <200 ms (95th percentile).
- NFR-02: Release/Refund must be idempotent.

## 3. Module view (static structure)
flowchart LR
    InAdapter[REST Controller] --> InPort[EscrowService]
    InPort --> Domain[Escrow Aggregate]
    Domain --> EscrowRepo[EscrowRepository]
    Domain --> OrderRepo[OrderRepository]
    EscrowRepo --> OutAdapter[In‑Memory Escrow Repo]
    OrderRepo --> InMemoryOrderRepo[In‑Memory Order Repo]

## 4. C&C view (runtime components & connectors)
HTTP/JSON · JWT auth (sync) ; Java method calls inside JVM

##    Affected components
- escrow/domain/model/Escrow.java
- escrow/domain/model/EscrowId.java
- escrow/domain/port/in/EscrowService.java
- escrow/domain/port/out/EscrowRepository.java
- escrow/application/EscrowApplicationService.java
- escrow/adapters/inmemory/InMemoryEscrowRepository.java

##    Interface / contract changes (ports)
- package escrow.domain.port.in; import tech.vsf.ptnt.msfw.domain.core.IdempotencyKey; public interface EscrowService { EscrowId open(OrderId orderId); void release(EscrowId escrowId, IdempotencyKey idemKey); void refund(EscrowId escrowId, IdempotencyKey idemKey); }
- package escrow.domain.port.out; import java.util.Optional; public interface EscrowRepository { Optional<Escrow> findByOrderId(OrderId orderId); Optional<Escrow> findById(EscrowId id); Escrow save(Escrow escrow); }

## 5. Domain model
classDiagram
    class EscrowId {
        <<value object>>
    }
    enum EscrowStatus { PENDING, RELEASED, REFUNDED }
    class IdempotencyKey {
        <<value object>>
    }
    class Escrow {
        +EscrowId id
        +OrderId orderId
        +Money amount
        +EscrowStatus status
        +Set<IdempotencyKey> processedKeys
        +static Escrow open(OrderId orderId, Money amount)
        +void release(IdempotencyKey key)
        +void refund(IdempotencyKey key)
        +boolean isProcessed(IdempotencyKey key)
        +void markProcessed(IdempotencyKey key)
    }

##    Invariants (enforced in the aggregate)
- Invariant-05: Open can only be called when the related Order exists and is in PLACED status – EscrowApplicationService checks OrderRepository.findById(orderId) and throws DomainException(ORDER_NOT_PLACED).
- Invariant-06: release/refund may only transition from PENDING → RELEASED/REFUNDED; otherwise DomainException(ESCROW_INVALID_STATE) is thrown.
- Invariant-07: Idempotency – if the supplied IdempotencyKey is already present in processedKeys, the command becomes a no‑op (state unchanged).

## 5.1 Event flow (Command → Event → Policy → Read Model)

**Domain Events**

| ID | Name (past tense) | Aggregate | Data | Traces |
|---|---|---|---|---|
| EVT-03 | EscrowOpened | Escrow | escrowId, orderId, amount | AC-05 |
| EVT-04 | EscrowReleased | Escrow | escrowId | AC-06 |
| EVT-05 | EscrowRefunded | Escrow | escrowId | AC-07 |

## 5.2 Integration contracts (sync APIs / async events)

**APIs (sync — OpenAPI digest)**

| ID | Method | Path | Summary | Auth | Idempotency | Traces |
|---|---|---|---|---|---|---|
| API-03 | POST | /api/v1/escrows/{orderId} | Open escrow for a placed order | JWT |  | AC-05 |
| API-04 | POST | /api/v1/escrows/{escrowId}/release | Release escrow to seller after order completion | JWT | Idempotency-Key header | AC-06, NFR-02 |
| API-05 | POST | /api/v1/escrows/{escrowId}/refund | Refund escrow to buyer after order cancellation | JWT | Idempotency-Key header | AC-07, NFR-02 |

## 6. Data model (ERD / schema)
erDiagram
    ESCROW {
        string escrow_id PK
        string order_id FK
        decimal amount
        varchar status
    }

## 7. Key flows
sequenceDiagram
    participant Controller as REST Controller
    participant Service as EscrowService
    participant OrderRepo as OrderRepository
    participant EscrowRepo as EscrowRepository
    %% Open flow
    Controller->>Service: open(orderId)
    Service->>OrderRepo: findById(orderId)
    alt order in PLACED
        Service->>EscrowRepo: save(new Escrow(...,PENDING))
        Service-->>Controller: escrowId
    else not placed
        Service-->>Controller: DomainException(ORDER_NOT_PLACED)
    end
    %% Release flow
    Controller->>Service: release(escrowId, idemKey)
    Service->>EscrowRepo: findById(escrowId)
    alt status == PENDING && !isProcessed(idemKey)
        Service->>EscrowRepo: save(updated Escrow(status=RELEASED))
        Service-->>Controller: 200 OK
    else already processed
        Service-->>Controller: no‑op (idempotent)
    else invalid state
        Service-->>Controller: DomainException(ESCROW_INVALID_STATE)
    end

## 8. Decisions (ADR-style)
- ADR-03: Store IdempotencyKey inside Escrow aggregate → because it guarantees exactly‑once semantics without external store.

## 9. Test strategy
See [`testcases-escrow.md`](testcases-escrow.md) for the full case list. Executable oracle (locked):
- `src/test/java/escrow/DomainOpenEscrowTest.java`
- `src/test/java/escrow/DomainReleaseEscrowIdempotentTest.java`
- `src/test/java/escrow/DomainRefundEscrowIdempotentTest.java`
- `src/test/java/escrow/DomainReleaseInvalidStateTest.java`

## 10. Open questions
_(none)_

