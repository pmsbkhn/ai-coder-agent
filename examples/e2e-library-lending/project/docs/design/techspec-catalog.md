# Tech Spec — Catalog

> **Classification:** Tier 2 – Data L3

## 1. Context & Scope
Manages bibliographic titles and physical copies. A Copy aggregate holds its status (AVAILABLE, ON_LOAN, LOST). The context exposes a CatalogService used by Lending to reserve/release copies.

## 2. Requirements — Functional (FR)
- FR1: Create a Title with a unique ISBN.
- FR2: Add a new Copy for an existing Title; newly created Copy must be AVAILABLE.
- FR3: Mark a Copy as LOST (terminal state).

##    Requirements — Non-functional / SLO
- NFR1: All operations are O(1) in‑memory.

## 3. Module view (static structure)
flowchart TD
    A[CatalogController] --> B[CatalogServicePortIn]
    B --> C[CopyAggregate]
    C --> D[CatalogRepositoryPortOut]

## 4. C&C view (runtime components & connectors)
_(none)_

##    Affected components
- src/main/java/com/example/library/catalog/Title.java
- src/main/java/com/example/library/catalog/Copy.java
- src/main/java/com/example/library/catalog/CopyStatus.java
- src/main/java/com/example/library/catalog/CatalogService.java

##    Interface / contract changes (ports)
- public interface CatalogService {
-   Copy createCopy(String titleId);
-   void markLost(UUID copyId);
-   Optional<Copy> findCopy(UUID copyId);
- }

## 5. Domain model
classDiagram
    class Title {
        +UUID id
        +String isbn
        +String name
    }
    class Copy {
        +UUID id
        +UUID titleId
        -CopyStatus status
        +setStatus(CopyStatus)
        +getStatus()
    }
    enum CopyStatus { AVAILABLE ON_LOAN LOST }

##    Invariants (enforced in the aggregate)
- Invariant C1: A Copy may only transition from AVAILABLE → ON_LOAN, ON_LOAN → AVAILABLE or any state → LOST. Any other transition throws DomainException(CODE.INVALID_COPY_STATUS_TRANSITION).
- Invariant C2: Once a Copy is in LOST state it is terminal; further status changes are prohibited.

## 6. Data model (ERD / schema)
erDiagram
    TITLE ||--o{ COPY : has
    COPY {
        UUID id PK
        UUID titleId FK
        varchar status
    }

## 7. Key flows
sequenceDiagram
    participant Client
    participant CatalogService
    participant CopyAggregate
    Client->>CatalogService: createCopy(titleId)
    CatalogService->>CopyAggregate: new Copy(status=AVAILABLE)
    CopyAggregate-->>CatalogService: CopyCreated
    CatalogService-->>Client: Copy

## 8. Decisions (ADR-style)
- ADR-001: Use enum CopyStatus instead of string literals → ensures compile‑time safety and centralised transition logic.
- ADR-002: Keep Catalog completely in‑memory for the core layer → simplifies testing and isolates domain from persistence concerns.

## 9. Test strategy
See [`testcases-catalog.md`](testcases-catalog.md) for the full case list. Executable oracle (locked):
- `src/test/java/com/example/library/catalog/CopyCreationTest.java`

## 10. Open questions
_(none)_

