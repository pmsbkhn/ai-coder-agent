# Test Cases — Order

> Acceptance cases for `techspec-order.md`. Approved cases with an oracle file are **locked** (the Coder implements to pass them, may not edit them). Format: `TC-<CTX>-NN [Title]: setup → action → assert`.

## Domain invariant cases (guard clauses in the Aggregate Root)

**TC-ORD-01 [[AC-03] Successful order placement]**

Given an in‑memory SellerRepository containing an ACTIVE seller with id S1, when PlaceOrderUseCase.place(S1, Money.of(100)) is invoked, then an OrderId is returned and the OrderRepository contains one Order with status PLACED and amount 100.

_Oracle:_ `src/test/java/order/DomainPlaceOrderTest.java`

**TC-ORD-02 [[AC-04] Reject zero or negative amount]**

Given an ACTIVE seller, when PlaceOrderUseCase.place(sellerId, Money.of(0)) is invoked, then DomainException with code INVALID_AMOUNT is thrown and no Order is persisted.

_Oracle:_ `src/test/java/order/DomainPlaceOrderInvalidAmountTest.java`

