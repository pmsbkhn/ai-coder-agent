# Tech Spec — Membership

> **Classification:** Tier 2 – Data L3

## 1. Context & Scope
Manages library members, their borrowing limit (default 5) and suspension status. Provides MemberService used by Lending to validate borrowing eligibility.

## 2. Requirements — Functional (FR)
- FR1: Register a new Member with default borrowing limit of 5 and ACTIVE state.
- FR2: Suspend or reactivate a Member.
- FR3: Track the number of ACTIVE Loans per Member.

##    Requirements — Non-functional / SLO
- NFR1: All operations are O(1) in‑memory.

## 3. Module view (static structure)
flowchart TD
    A[MembershipController] --> B[MemberServicePortIn]
    B --> C[MemberAggregate]
    C --> D[MemberRepositoryPortOut]

## 4. C&C view (runtime components & connectors)
_(none)_

##    Affected components
- src/main/java/com/example/library/membership/Member.java
- src/main/java/com/example/library/membership/MemberStatus.java
- src/main/java/com/example/library/membership/MemberService.java

##    Interface / contract changes (ports)
- public interface MemberService {
-   Member register(String name);
-   void suspend(UUID memberId);
-   void activate(UUID memberId);
-   Optional<Member> findById(UUID memberId);
- }

## 5. Domain model
classDiagram
    class Member {
        +UUID id
        +String name
        -MemberStatus status
        -int borrowLimit
        -Set<UUID> activeLoanIds
        +canBorrow():boolean
        +addActiveLoan(UUID loanId)
        +removeActiveLoan(UUID loanId)
    }
    enum MemberStatus { ACTIVE SUSPENDED }

##    Invariants (enforced in the aggregate)
- Invariant M1: A Member with status SUSPENDED cannot add a new active Loan; attempts must throw DomainException(CODE.MEMBER_SUSPENDED).
- Invariant M2: The number of active Loans for a Member may never exceed borrowLimit; exceeding throws DomainException(CODE.BORROW_LIMIT_EXCEEDED).

## 6. Data model (ERD / schema)
erDiagram
    MEMBER {
        UUID id PK
        varchar name
        varchar status
        int borrow_limit
    }

## 7. Key flows
sequenceDiagram
    participant Client
    participant MemberService
    participant MemberAggregate
    Client->>MemberService: register(name)
    MemberService->>MemberAggregate: new Member(status=ACTIVE, limit=5)
    MemberAggregate-->>MemberService: MemberCreated
    MemberService-->>Client: Member

## 8. Decisions (ADR-style)
- ADR-010: Keep borrowLimit mutable only via explicit administrative command – future extension.
- ADR-011: Store activeLoanIds inside the Member aggregate to enforce limit without external queries.

## 9. Test strategy
See [`testcases-membership.md`](testcases-membership.md) for the full case list. Executable oracle (locked):
- `src/test/java/com/example/library/membership/MemberRegistrationTest.java`

## 10. Open questions
_(none)_

