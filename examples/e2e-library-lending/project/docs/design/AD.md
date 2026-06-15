# Architecture Description

> System-level design for one change; reviewed by an architect before implementation. One AD spans one or more Tech Specs — **1 bounded context = 1 Tech Spec**. Detailed per-context design lives in the linked Tech Specs.

## Requirement
Xây dựng lõi nghiệp vụ (pure Java 21, KHÔNG dùng Spring/DB/web ở vòng lặp này — chỉ domain model + domain service + JUnit5) cho hệ thống Thư viện số, gồm ba bounded context: (1) Catalog — quản lý Đầu sách (Title) và các Bản sao (Copy); mỗi Copy có trạng thái AVAILABLE, ON_LOAN hoặc LOST. (2) Membership — quản lý Thành viên (Member) với hạn mức mượn tối đa (mặc định 5 cuốn); thành viên có thể bị đình chỉ (SUSPENDED) và khi đó không được mượn. (3) Lending — quản lý phiếu mượn (Loan) theo vòng đời ACTIVE -> RETURNED, có thể OVERDUE; trả sách đưa Copy về AVAILABLE; tính quá hạn theo ngày đến hạn. Ràng buộc bất biến: không cho mượn vượt hạn mức; không mượn Copy không ở trạng thái AVAILABLE; thành viên SUSPENDED không mượn được; Loan đã RETURNED là trạng thái terminal (bất biến, ném lỗi nếu thao tác tiếp). Dùng java.time.LocalDate cho ngày; ném DomainException(CODE) cho vi phạm nghiệp vụ.

## Summary
Build a pure‑Java21 domain core for a digital library system, introducing three bounded contexts – Catalog, Membership and Lending – with aggregates, domain services and exhaustive JUnit5 tests that enforce borrowing limits, copy availability, member suspension and loan lifecycle invariants.

## Goals
- Enforce all business rules without any framework or persistence code.
- Provide a clean hexagonal design per bounded context for future extension.

## Architecture style
Hexagonal per bounded context – pure Java21 aggregates + domain services, orchestration via LendingService (synchronous calls) and choreography through DomainException events.

## Design principles
- In‑memory only – no external I/O in the core.
- Each aggregate owns its invariants; no cross‑aggregate mutable state.
- DomainException with explicit Code enum for every rule violation.
- Stateless domain services – they coordinate aggregates but do not hold data.

## Bounded-context map
graph LR
    Catalog -->|synchronous| Lending
    Membership -->|synchronous| Lending

## Cross-cutting decisions
- Use UUID strings as identity values for all entities (Title, Copy, Member, Loan).
- Represent dates with java.time.LocalDate; loan period is a constant 14 days.
- CopyStatus and LoanState are enums; OVERDUE is a derived boolean property.
- All invariants are checked inside aggregate methods; services only orchestrate.

## Non-functional requirements / constraints
- Latency: sub‑millisecond in‑process calls (no external latency).
- Testability: pure Java core enables fast unit tests with JUnit5.
- Portability: Java 21 language features only, no Spring or other frameworks.

## Bounded contexts (→ Tech Spec · Test Cases)
- **Catalog** → [`techspec-catalog.md`](techspec-catalog.md) · tests [`testcases-catalog.md`](testcases-catalog.md) — Manages bibliographic titles and physical copies. A Copy aggregate holds its status (AVAILABLE, ON_LOAN, LOST). The context exposes a CatalogService used by Lending to reserve/release copies.
- **Membership** → [`techspec-membership.md`](techspec-membership.md) · tests [`testcases-membership.md`](testcases-membership.md) — Manages library members, their borrowing limit (default 5) and suspension status. Provides MemberService used by Lending to validate borrowing eligibility.
- **Lending** → [`techspec-lending.md`](techspec-lending.md) · tests [`testcases-lending.md`](testcases-lending.md) — Coordinates loan creation and return, enforcing cross‑context invariants by invoking CatalogService and MemberService. The Loan aggregate tracks state (ACTIVE/RETURNED), dates and derives overdue status.

