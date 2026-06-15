# Tech Spec — Lending

> **Classification:** Tier 1 – Core Domain L4

## 1. Context & Scope
Coordinates loan creation and return, enforcing cross‑context invariants by invoking CatalogService and MemberService. The Loan aggregate tracks state (ACTIVE/RETURNED), dates and derives overdue status.

## 2. Requirements — Functional (FR)
- FR1: Create a Loan for an AVAILABLE Copy and an ACTIVE, non‑suspended Member within the member's borrowing limit.
- FR2: Return a Loan, marking it RETURNED and making the associated Copy AVAILABLE again.
- FR3: Provide isOverdue(LocalDate) boolean derived from due date.

##    Requirements — Non-functional / SLO
- NFR1: All operations are pure‑Java, thread‑safe for single‑threaded unit tests.

## 3. Module view (static structure)
flowchart TD
    A[LoanController] --> B[LendingServicePortIn]
    B --> C[LoanAggregate]
    C --> D[CatalogServicePortOut]
    C --> E[MemberServicePortOut]

## 4. C&C view (runtime components & connectors)
_(none)_

##    Affected components
- src/main/java/com/example/library/lending/Loan.java
- src/main/java/com/example/library/lending/LoanState.java
- src/main/java/com/example/library/lending/LendingService.java

##    Interface / contract changes (ports)
- public interface LendingService {
-   Loan createLoan(UUID memberId, UUID copyId, LocalDate loanDate);
-   void returnLoan(UUID loanId, LocalDate returnDate);
-   boolean isOverdue(UUID loanId, LocalDate currentDate);
- }

## 5. Domain model
classDiagram
    class Loan {
        +UUID id
        +UUID memberId
        +UUID copyId
        -LoanState state
        -LocalDate loanDate
        -LocalDate dueDate
        -LocalDate returnDate
        +isOverdue(LocalDate):boolean
        +returnLoan(LocalDate)
    }
    enum LoanState { ACTIVE RETURNED }

##    Invariants (enforced in the aggregate)
- Invariant L1: A Loan can only be created if the referenced Copy is AVAILABLE; otherwise DomainException(CODE.COPY_NOT_AVAILABLE).
- Invariant L2: A Loan cannot be created for a Member whose status is SUSPENDED; otherwise DomainException(CODE.MEMBER_SUSPENDED).
- Invariant L3: A Member may not have more than borrowLimit ACTIVE Loans; exceeding throws DomainException(CODE.BORROW_LIMIT_EXCEEDED).
- Invariant L4: Returning a Loan that is already in RETURNED state throws DomainException(CODE.LOAN_ALREADY_RETURNED).
- Invariant L5: After successful creation, the Copy status becomes ON_LOAN and Loan.state = ACTIVE with dueDate = loanDate.plusDays(14).
- Invariant L6: After returning, Loan.state = RETURNED, returnDate recorded, and Copy status set back to AVAILABLE.

## 6. Data model (ERD / schema)
erDiagram
    MEMBER ||--o{ LOAN : borrows
    COPY ||--o{ LOAN : loaned_by
    LOAN {
        UUID id PK
        UUID memberId FK
        UUID copyId FK
        varchar state
        date loan_date
        date due_date
        date return_date
    }

## 7. Key flows
sequenceDiagram
    participant Client
    participant LendingService
    participant MemberService
    participant CatalogService
    participant LoanAggregate
    Client->>LendingService: createLoan(memberId, copyId, today)
    LendingService->>MemberService: findById(memberId)
    MemberService-->>LendingService: Member(active, limit)
    LendingService->>CatalogService: findCopy(copyId)
    CatalogService-->>LendingService: Copy(AVAILABLE)
    LendingService->>LoanAggregate: new Loan(state=ACTIVE, dueDate=today+14)
    LoanAggregate->>CatalogService: setCopyStatus(ON_LOAN)
    LoanAggregate-->>LendingService: LoanCreated
    LendingService-->>Client: Loan

## 8. Decisions (ADR-style)
- ADR-020: Derive overdue status from current date rather than persisting a flag – guarantees consistency.
- ADR-021: Keep Loan aggregate immutable except for state transitions via explicit methods.

## 9. Test strategy
See [`testcases-lending.md`](testcases-lending.md) for the full case list. Executable oracle (locked):
- `src/test/java/com/example/library/catalog/CopyCreationTest.java`
- `src/test/java/com/example/library/lending/LoanCreationCopyNotAvailableTest.java`
- `src/test/java/com/example/library/lending/LoanCreationMemberSuspendedTest.java`
- `src/test/java/com/example/library/lending/BorrowLimitExceededTest.java`
- `src/test/java/com/example/library/lending/SuccessfulLoanCreationTest.java`
- `src/test/java/com/example/library/lending/ReturnLoanSuccessTest.java`
- `src/test/java/com/example/library/lending/ReturnLoanAlreadyReturnedTest.java`
- `src/test/java/com/example/library/lending/OverdueCheckTest.java`

## 10. Open questions
_(none)_

