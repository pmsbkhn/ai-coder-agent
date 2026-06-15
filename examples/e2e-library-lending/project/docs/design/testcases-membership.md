# Test Cases — Membership

> Acceptance cases for `techspec-membership.md`. Approved cases with an oracle file are **locked** (the Coder implements to pass them, may not edit them). Format: `TC-<CTX>-NN [Title]: setup → action → assert`.

## Domain invariant cases (guard clauses in the Aggregate Root)

**TC-MEM-01 [[Member Registration] default limit 5 and ACTIVE status]**

When MemberService.register("John") is called, then the returned Member has borrowLimit=5 and status=ACTIVE.

_Oracle:_ `src/test/java/com/example/library/membership/MemberRegistrationTest.java`

