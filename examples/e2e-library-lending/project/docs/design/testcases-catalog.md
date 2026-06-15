# Test Cases — Catalog

> Acceptance cases for `techspec-catalog.md`. Approved cases with an oracle file are **locked** (the Coder implements to pass them, may not edit them). Format: `TC-<CTX>-NN [Title]: setup → action → assert`.

## Domain invariant cases (guard clauses in the Aggregate Root)

**TC-CAT-01 [[Copy Creation] sets status AVAILABLE]**

Given a Title exists, when CatalogService.createCopy(titleId) is called, then the returned Copy has status AVAILABLE.

_Oracle:_ `src/test/java/com/example/library/catalog/CopyCreationTest.java`

