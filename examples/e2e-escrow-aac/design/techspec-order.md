# Tech Spec — Order

> **Classification:** Tier 1 / L2

## 1. Context & Scope
Place orders against active sellers and enforce positive amount.

## 2. Requirements — Functional (FR)
- FR-03: Place an order for a given active seller with a positive amount, returning OrderId.
- FR-04: Reject placement when amount is zero or negative.

##    Requirements — Non-functional / SLO
_(none)_

## 3. Module view (static structure)
flowchart LR
    InAdapter[REST Controller] --> InPort[PlaceOrderUseCase]
    InPort --> Domain[Order Aggregate]
    Domain --> OutPort[OrderRepository]
    Domain --> SellerPort[SellerRepository]
    OutPort --> OutAdapter[In‑Memory Order Repo]
    SellerPort --> InMemorySellerRepo[In‑Memory Seller Repo]

## 4. C&C view (runtime components & connectors)
HTTP/JSON · JWT auth (sync) ; Java method calls inside JVM

##    Affected components
- order/domain/model/Order.java
- order/domain/model/OrderId.java
- order/domain/port/in/PlaceOrderUseCase.java
- order/domain/port/out/OrderRepository.java
- order/application/PlaceOrderService.java
- order/adapters/inmemory/InMemoryOrderRepository.java

##    Interface / contract changes (ports)
- package order.domain.port.in; import tech.vsf.ptnt.msfw.domain.core.StringIdentity; public interface PlaceOrderUseCase { OrderId place(SellerId sellerId, Money amount); }
- package order.domain.port.out; import java.util.Optional; public interface OrderRepository { Optional<Order> findById(OrderId id); Order save(Order order); }

## 5. Domain model
classDiagram
    class OrderId {
        <<value object>>
    }
    class Money {
        <<value object>>
    }
    enum OrderStatus { PLACED, CANCELLED, COMPLETED }
    class Order {
        +OrderId id
        +SellerId sellerId
        +Money amount
        +OrderStatus status
        +static Order place(SellerId sellerId, Money amount)
        +void cancel()
        +void complete()
    }

##    Invariants (enforced in the aggregate)
- Invariant-03: Seller must exist and be ACTIVE – PlaceOrderService checks SellerRepository.findById(sellerId) and throws DomainException(SELLER_NOT_ACTIVE) otherwise.
- Invariant-04: Amount must be positive – place() validates amount > 0, else throws DomainException(INVALID_AMOUNT).

## 5.1 Event flow (Command → Event → Policy → Read Model)

**Domain Events**

| ID | Name (past tense) | Aggregate | Data | Traces |
|---|---|---|---|---|
| EVT-02 | OrderPlaced | Order | orderId, sellerId, amount | AC-03 |

## 5.2 Integration contracts (sync APIs / async events)

**APIs (sync — OpenAPI digest)**

| ID | Method | Path | Summary | Auth | Idempotency | Traces |
|---|---|---|---|---|---|---|
| API-02 | POST | /api/v1/orders | Place a new order | JWT |  | AC-03, AC-04 |

## 6. Data model (ERD / schema)
erDiagram
    ORDER {
        string order_id PK
        string seller_id FK
        decimal amount
        varchar status
    }

## 7. Key flows
sequenceDiagram
    participant Controller as REST Controller
    participant UC as PlaceOrderUseCase
    participant SellerRepo as SellerRepository
    participant OrderRepo as OrderRepository
    Controller->>UC: place(sellerId,amount)
    UC->>SellerRepo: findById(sellerId)
    alt seller active
        UC->>OrderRepo: save(new Order(...))
        UC-->>Controller: orderId
    else seller not found / inactive
        UC-->>Controller: DomainException(SELLER_NOT_ACTIVE)
    end

## 8. Decisions (ADR-style)
- ADR-02: Validate amount in domain service rather than controller → because business rule belongs to aggregate.

## 9. Test strategy
See [`testcases-order.md`](testcases-order.md) for the full case list. Executable oracle (locked):
- `src/test/java/order/DomainPlaceOrderTest.java`
- `src/test/java/order/DomainPlaceOrderInvalidAmountTest.java`

## 10. Open questions
_(none)_

