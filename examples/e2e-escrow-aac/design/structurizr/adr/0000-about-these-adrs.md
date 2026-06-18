# 0. About these ADRs

> Architecture Decision Records for this change — one decision per file, MADR-lite,
> numbered only (no README in this directory). Generated from the DesignSpec.

| # | Title | Context |
|---|---|---|
| 0001 | Seller owns SellerId, Email, DisplayName and is the source of truth fo | system-wide |
| 0002 | Order owns OrderId and references SellerId; it depends on Seller via C | system-wide |
| 0003 | Escrow owns EscrowId and depends on OrderId; it uses synchronous Java | system-wide |
| 0004 | IdempotencyKey from shared kernel is stored inside Escrow aggregate to | system-wide |
