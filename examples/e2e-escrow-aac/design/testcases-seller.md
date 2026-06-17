# Test Cases — Seller

> Acceptance cases for `techspec-seller.md`. Approved cases with an oracle file are **locked** (the Coder implements to pass them, may not edit them). Format: `TC-<CTX>-NN [Title]: setup → action → assert`.

## Domain invariant cases (guard clauses in the Aggregate Root)

**TC-SEL-01 [[AC-01] Successful seller registration]**

Given a fresh in‑memory SellerRepository, when RegisterSellerUseCase.register("alice@example.com","Alice") is invoked, then a SellerId is returned, the repository contains one Seller with status ACTIVE and email "alice@example.com".

_Oracle:_ `src/test/java/seller/DomainRegisterSellerTest.java`

**TC-SEL-02 [[AC-02] Reject duplicate seller email]**

Given a repository already containing a Seller with email "bob@example.com", when RegisterSellerUseCase.register("bob@example.com","Bob") is invoked, then DomainException with code EMAIL_ALREADY_EXISTS is thrown and repository size remains 1.

_Oracle:_ `src/test/java/seller/DomainRegisterSellerDuplicateTest.java`

