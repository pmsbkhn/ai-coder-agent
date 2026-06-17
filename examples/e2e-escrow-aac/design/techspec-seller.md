# Tech Spec — Seller

> **Classification:** Tier 1 / L2

## 1. Context & Scope
Register new sellers and enforce unique email.

## 2. Requirements — Functional (FR)
- FR-01: Register a seller with email & display name, returning SellerId.
- FR-02: Reject registration when email already exists.

##    Requirements — Non-functional / SLO
_(none)_

## 3. Module view (static structure)
flowchart LR
    InAdapter[REST Controller] --> InPort[RegisterSellerUseCase]
    InPort --> Domain[Seller Aggregate]
    Domain --> OutPort[SellerRepository]
    OutPort --> OutAdapter[In‑Memory Repo]

## 4. C&C view (runtime components & connectors)
HTTP/JSON · JWT auth (sync) ; Java method calls inside JVM

##    Affected components
- seller/domain/model/Seller.java
- seller/domain/model/SellerId.java
- seller/domain/port/in/RegisterSellerUseCase.java
- seller/domain/port/out/SellerRepository.java
- seller/application/RegisterSellerService.java
- seller/adapters/inmemory/InMemorySellerRepository.java

##    Interface / contract changes (ports)
- package seller.domain.port.in; public interface RegisterSellerUseCase { SellerId register(String email, String displayName); }
- package seller.domain.port.out; import java.util.Optional; public interface SellerRepository { Optional<Seller> findByEmail(String email); Optional<Seller> findById(SellerId id); Seller save(Seller seller); }

## 5. Domain model
classDiagram
    class SellerId {
        <<value object>>
    }
    class Email {
        <<value object>>
    }
    class DisplayName {
        <<value object>>
    }
    enum SellerStatus { ACTIVE, INACTIVE }
    class Seller {
        +SellerId id
        +Email email
        +DisplayName displayName
        +SellerStatus status
        +static Seller register(String email, String displayName)
        +void activate()
    }

##    Invariants (enforced in the aggregate)
- Invariant-01: Email must be unique – RegisterSellerService checks repository.findByEmail(email) and throws DomainException(EMAIL_ALREADY_EXISTS) if present.
- Invariant-02: After successful registration the seller status is ACTIVE.

## 5.1 Event flow (Command → Event → Policy → Read Model)

**Domain Events**

| ID | Name (past tense) | Aggregate | Data | Traces |
|---|---|---|---|---|
| EVT-01 | SellerRegistered | Seller | sellerId, email, displayName | AC-01 |

## 5.2 Integration contracts (sync APIs / async events)

**APIs (sync — OpenAPI digest)**

| ID | Method | Path | Summary | Auth | Idempotency | Traces |
|---|---|---|---|---|---|---|
| API-01 | POST | /api/v1/sellers | Register a new seller | JWT |  | AC-01, AC-02 |

## 6. Data model (ERD / schema)
erDiagram
    SELLER {
        string seller_id PK
        string email UQ
        string display_name
        varchar status
    }

## 7. Key flows
sequenceDiagram
    participant Controller as REST Controller
    participant UC as RegisterSellerUseCase
    participant Repo as SellerRepository
    Controller->>UC: register(email,displayName)
    UC->>Repo: findByEmail(email)
    alt email not found
        UC->>Repo: save(new Seller(...))
        UC-->>Controller: sellerId
    else email exists
        UC-->>Controller: DomainException(EMAIL_ALREADY_EXISTS)
    end

## 8. Decisions (ADR-style)
- ADR-01: Use repository check for email uniqueness → because it guarantees consistency without DB FK → consequence: domain service must handle Optional result.

## 9. Test strategy
See [`testcases-seller.md`](testcases-seller.md) for the full case list. Executable oracle (locked):
- `src/test/java/seller/DomainRegisterSellerTest.java`
- `src/test/java/seller/DomainRegisterSellerDuplicateTest.java`

## 10. Open questions
_(none)_

