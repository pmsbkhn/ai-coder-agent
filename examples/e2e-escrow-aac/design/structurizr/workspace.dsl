workspace "Add seller onboarding, order placement, and escrow lifecycle with idem" "Marketplace escrow payments core US-01 — Seller onboarding [High] As a marketplace operator, I want register sellers with a basic profile, so that orders can be" {

    model {
        system = softwareSystem "Add seller onboarding, order placement, and escrow lifecycle with idem" {
            seller = container "Seller" "Register new sellers and enforce unique email." "BoundedContext" {
                !include seller.dsl
            }
            order = container "Order" "Place orders against active sellers and enforce positive amount." "BoundedContext" {
                !include order.dsl
            }
            escrow = container "Escrow" "Open escrow for placed orders and settle (release/refund) with idempotent guarantees." "BoundedContext" {
                !include escrow.dsl
            }
        }
        seller -> order "Customer/Supplier: sync (Java call)"
        order -> escrow "Customer/Supplier: sync (Java call)"
    }

    views {
        systemContext system "SystemContext" {
            include *
            autolayout lr
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
    }
}
