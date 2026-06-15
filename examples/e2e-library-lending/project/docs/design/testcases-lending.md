# Test Cases — Lending

> Acceptance cases for `techspec-lending.md`. Approved cases with an oracle file are **locked** (the Coder implements to pass them, may not edit them). Format: `TC-<CTX>-NN [Title]: setup → action → assert`.

## Domain invariant cases (guard clauses in the Aggregate Root)

**TC-LEN-01 [[Copy Creation] sets status AVAILABLE]**

Given a Title exists, when CatalogService.createCopy(titleId) is called, then the returned Copy has status AVAILABLE.

_Oracle:_ `src/test/java/com/example/library/catalog/CopyCreationTest.java`

**TC-LEN-02 [[Loan Creation] non‑available Copy throws COPY_NOT_AVAILABLE]**

Given a Copy whose status is ON_LOAN, when LendingService.createLoan(memberId, copyId, today) is invoked, then DomainException with code COPY_NOT_AVAILABLE is thrown.

_Oracle:_ `src/test/java/com/example/library/lending/LoanCreationCopyNotAvailableTest.java`

**TC-LEN-03 [[Loan Creation] suspended Member throws MEMBER_SUSPENDED]**

Given a Member with status SUSPENDED, when LendingService.createLoan(memberId, copyId, today) is called, then DomainException with code MEMBER_SUSPENDED is thrown.

_Oracle:_ `src/test/java/com/example/library/lending/LoanCreationMemberSuspendedTest.java`

**TC-LEN-04 [[Borrow Limit] exceeding limit throws BORROW_LIMIT_EXCEEDED]**

Given a Member who already has five ACTIVE Loans, when LendingService.createLoan(memberId, anotherCopyId, today) is invoked, then DomainException with code BORROW_LIMIT_EXCEEDED is thrown.

_Oracle:_ `src/test/java/com/example/library/lending/BorrowLimitExceededTest.java`

**TC-LEN-05 [[Successful Loan] creates ACTIVE loan and sets copy ON_LOAN]**

Given an AVAILABLE Copy and an ACTIVE Member within limit, when LendingService.createLoan is called, then a Loan with state ACTIVE and dueDate = loanDate+14 is returned and the Copy status becomes ON_LOAN.

_Oracle:_ `src/test/java/com/example/library/lending/SuccessfulLoanCreationTest.java`

**TC-LEN-06 [[Return Loan] changes state to RETURNED and makes copy AVAILABLE]**

Given an ACTIVE Loan, when LendingService.returnLoan(loanId, returnDate) is invoked, then the Loan state becomes RETURNED, returnDate recorded, and the associated Copy status becomes AVAILABLE.

_Oracle:_ `src/test/java/com/example/library/lending/ReturnLoanSuccessTest.java`

**TC-LEN-07 [[Return Loan] already RETURNED throws LOAN_ALREADY_RETURNED]**

Given a Loan that is already in state RETURNED, when LendingService.returnLoan is called again, then DomainException with code LOAN_ALREADY_RETURNED is thrown.

_Oracle:_ `src/test/java/com/example/library/lending/ReturnLoanAlreadyReturnedTest.java`

**TC-LEN-08 [[Overdue Check] isOverdue returns true only when ACTIVE and past due date]**

Given a Loan in state ACTIVE with dueDate = 2024‑01‑10, when isOverdue(2024‑01‑11) is called it returns true; for dates before or equal to dueDate or when state is RETURNED it returns false.

_Oracle:_ `src/test/java/com/example/library/lending/OverdueCheckTest.java`

