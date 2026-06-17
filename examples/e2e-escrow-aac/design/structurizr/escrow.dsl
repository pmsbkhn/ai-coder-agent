# Components for bounded context: Escrow
# Included by workspace.dsl into the `escrow` container.
escrow_escrowrepository = component "EscrowRepository" "outbound port" "port.out"
escrow_escrowservice = component "EscrowService" "application service" "application"
escrow_escrow = component "Escrow" "aggregate / value object" "domain"
escrow_escrowid = component "EscrowId" "aggregate / value object" "domain"
escrow_escrowstatus = component "EscrowStatus" "aggregate / value object" "domain"
escrow_idempotencykey = component "IdempotencyKey" "aggregate / value object" "domain"
escrow_escrowservice -> escrow_escrow "operates on"
escrow_escrowservice -> escrow_escrowid "operates on"
escrow_escrowservice -> escrow_escrowstatus "operates on"
escrow_escrowservice -> escrow_idempotencykey "operates on"
escrow_escrowservice -> escrow_escrowrepository "persists via"
