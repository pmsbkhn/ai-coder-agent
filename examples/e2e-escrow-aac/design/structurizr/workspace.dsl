workspace "Add seller onboarding, order placement, and escrow lifecycle with idem" "Marketplace escrow payments core US-01 — Seller onboarding [High] As a marketplace operator, I want register sellers with a basic profile, so that orders can be" {

    model {
        !impliedRelationships true

        system = softwareSystem "Add seller onboarding, order placement, and escrow lifecycle with idem" {
            seller = container "Seller" "Register new sellers and enforce unique email." "BoundedContext" {
                !include seller.dsl
            }
            seller_db = container "Seller Database" "Persistence owned by the Seller context (DB-per-service)." "Datastore" "Database"
            order = container "Order" "Place orders against active sellers and enforce positive amount." "BoundedContext" {
                !include order.dsl
            }
            order_db = container "Order Database" "Persistence owned by the Order context (DB-per-service)." "Datastore" "Database"
            escrow = container "Escrow" "Open escrow for placed orders and settle (release/refund) with idempotent guarantees." "BoundedContext" {
                !include escrow.dsl
            }
            escrow_db = container "Escrow Database" "Persistence owned by the Escrow context (DB-per-service)." "Datastore" "Database"
            !docs documentation
            !adrs adr
        }

        seller -> order "Customer/Supplier: sync (Java call)"
        order -> escrow "Customer/Supplier: sync (Java call)"
        seller_sellerrepository -> seller_db "reads/writes" "JDBC"
        order_orderrepository -> order_db "reads/writes" "JDBC"
        escrow_escrowrepository -> escrow_db "reads/writes" "JDBC"
    }

    views {
        systemContext system "SystemContext" {
            include *
            autolayout tb
        }
        container system "Containers" {
            include *
            autolayout lr
        }
        component seller "seller_components" {
            include *
            autolayout lr
        }
        component order "order_components" {
            include *
            autolayout lr
        }
        component escrow "escrow_components" {
            include *
            autolayout lr
        }
        !include styles.dsl
    }
}
