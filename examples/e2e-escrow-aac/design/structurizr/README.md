# Architecture as Code

Architecture description (C4 + ISO/IEC/IEEE 42010) as Structurizr DSL — one model, many views. Generated from the design (`../AD.md` + the Tech Specs).

## Files

- `workspace.dsl` — master (model + views + `!docs` + `!adrs`)
- `styles.dsl` — tag → shape/colour
- `<context>.dsl` — components inside each bounded context
- `documentation/` — prose embedding the views (`!docs`)
- `adr/` — numbered MADR decisions (`!adrs`)

## Views by stakeholder

| Stakeholder | Concern | View key |
|---|---|---|
| Business / PO | scope & external actors | `SystemContext` |
| Architect | services + datastores, sync/async | `Containers` |
| Dev — Seller | internal structure | `seller_components` |
| Dev — Order | internal structure | `order_components` |
| Dev — Escrow | internal structure | `escrow_components` |

## Render / validate

```bash
# View interactively at http://localhost:8080
docker run -it --rm -p 8080:8080 -v "$PWD/examples/e2e-escrow-aac/design/structurizr:/usr/local/structurizr" structurizr/lite

# Validate (pin a dated tag — NEVER :latest, which is a no-op stub)
docker run --rm -v "$PWD:/work" -w /work structurizr/cli:2025.11.09 \
  validate -workspace examples/e2e-escrow-aac/design/structurizr/workspace.dsl
```
