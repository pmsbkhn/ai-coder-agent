"""Render a DesignSpec into a marketplace-grade Architecture-as-Code set (C4 +
ISO/IEC/IEEE 42010), mirroring the design-flow Appendix A7. From the
already-validated, already-linted `DesignSpec` (the LLM never writes DSL directly),
this emits, under `docs/design/structurizr/`:

- **workspace.dsl** — the master: actors + external systems, one `softwareSystem`
  whose containers are the bounded contexts (each `!include`-ing its component
  fragment) plus a per-context datastore (DB-per-service), the message bus when the
  design is event-driven, cross-context relationships, data-ownership edges, and the
  views (System Context, Containers, per-context Components, one Dynamic view per
  Saga) — with `!docs documentation` and `!adrs adr` embedded.
- **styles.dsl** — tag → shape/colour (separated from content).
- **<context>.dsl** — the components INSIDE one context's container (inbound ports,
  application service, aggregate(s), outbound ports), derived from the Tech Spec.
- **bus.dsl** — the shared Message Bus container (only when the design is event-driven).
- **documentation/*.md** — prose embedding the views via `![alt](embed:ViewKey)` (`!docs`).
- **adr/NNNN-*.md** — MADR-lite Architecture Decision Records, numbered only (`!adrs`).
- **README.md** — an index of the set (lives OUTSIDE adr/).
- (opt-in) **.github/workflows/aac.yml** — CI that validates + exports the DSL.

Pure functions over the domain models — no I/O, no infra. The output is meant to be
parseable by `structurizr/cli` (pin a dated tag such as 2025.11.09 — NEVER `:latest`,
which is a deprecation no-op stub). `structurizr_lint.validate_structurizr` is a
pure-Python regression guard over the rendered files; the real parse runs in CI.

DSL syntax rules every renderer here obeys (each is a real bug that shipped elsewhere
because an unvalidated DSL was accepted):
  1. `{` is always the LAST token on its line; the block body is on following lines.
  2. `=` always has a space on both sides.
  3. An `!adrs` directory contains ONLY numbered `NNNN-*.md` files (a README throws).
  4. Every `![alt](embed:KEY)` names a view key that is actually defined.
  5. Structurizr identifiers are GLOBAL — every component is namespaced by its container.
"""

from __future__ import annotations

import re

from aicoder.domain.models import DesignSpec, TechSpec

_DSL_SUBDIR = "docs/design/structurizr"
_CLI_TAG = "structurizr/cli:2025.11.09"  # last dated tag that runs the real CLI

# Type tokens that name a port / service / aggregate in the free-text contracts.
_IFACE = re.compile(r"\binterface\s+([A-Za-z_]\w*)")
_PORTISH = re.compile(r"\b([A-Z]\w*(?:UseCase|Port|Repository|Gateway|Service))\b")
_DECL = re.compile(r"\b(?:class|enum|record)\s+([A-Z]\w*)")
# A directed edge in a mermaid context map: `A --> B`, `A -.-> B`, `A -->|label| B`.
_MAP_EDGE = re.compile(r"\b([A-Za-z_]\w*)\b\s*-[.-]*->\s*(?:\|[^|]*\|\s*)?\b([A-Za-z_]\w*)\b")
# An outbound port that OWNS persistence (DB-per-service) — a Gateway is a remote call,
# not a datastore, so it is excluded and never draws a fake DB write.
_PERSISTENCE = re.compile(r"(Repository|Store|Dao|Oa)$")
# Free-text actor strings that are really a service/system, not a C4 person.
_ACTOR_NOISE = re.compile(
    r"(service|system|gateway|api|scheduler|cron|timer|worker|engine|module|context|bus|queue|broker)",
    re.IGNORECASE,
)


def workspace_path(docs_subdir: str = _DSL_SUBDIR) -> str:
    return f"{docs_subdir}/workspace.dsl"


def context_path(ts: TechSpec, docs_subdir: str = _DSL_SUBDIR) -> str:
    return f"{docs_subdir}/{_ident(ts.bounded_context)}.dsl"


def _ident(name: str) -> str:
    """A valid Structurizr identifier: lower snake, leading letter."""
    s = re.sub(r"[^0-9A-Za-z]+", "_", (name or "").strip()).strip("_").lower()
    if not s:
        return "ctx"
    return s if s[0].isalpha() else f"c_{s}"


def _q(text: str) -> str:
    """Safe content for a double-quoted DSL string (one line, no embedded quotes)."""
    return re.sub(r"\s+", " ", (text or "").replace('"', "'")).strip()


def _slug(text: str, words: int = 7) -> str:
    """A short filename slug from free text: first few words, kebab-case."""
    toks = re.findall(r"[A-Za-z0-9]+", (text or "").lower())
    s = "-".join(toks[:words])
    return s or "decision"


# A leading "ADR-01:" / "ADR 2 -" style prefix a model sometimes bakes into a decision
# string — stripped so it is not doubled by our own numbering (ADR 0005 "ADR-01: ...").
_ADR_PREFIX = re.compile(r"^\s*ADR[-\s]?\d+\s*[:.\-]?\s*", re.IGNORECASE)


def _strip_adr_prefix(text: str) -> str:
    stripped = _ADR_PREFIX.sub("", text or "", count=1).strip()
    return stripped or (text or "").strip()


def _classify(name: str) -> str:
    if name.endswith("UseCase"):
        return "port.in"
    if name.endswith(("Repository", "Gateway")):
        return "port.out"
    if name.endswith("Service"):
        return "application"
    return "port.in"  # bare "*Port" — treat as an inbound port


def _components(ts: TechSpec) -> list[tuple[str, str, str, str]]:
    """(identifier, name, description, tag) for the components of one context, derived
    from its interface contracts (ports/services) and domain model (aggregates)."""
    text = "\n".join(ts.interface_changes)
    ports = sorted(set(_IFACE.findall(text)) | set(_PORTISH.findall(text)))
    aggregates = [a for a in sorted(set(_DECL.findall(ts.domain_model))) if a not in ports]
    out: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()
    for n in ports:
        tag = _classify(n)
        cid = _ident(n)
        if cid in seen:
            continue
        seen.add(cid)
        desc = {"port.in": "inbound use-case port", "port.out": "outbound port",
                "application": "application service"}.get(tag, "port")
        out.append((cid, n, desc, tag))
    for n in aggregates:
        cid = _ident(n)
        if cid in seen:
            continue
        seen.add(cid)
        out.append((cid, n, "aggregate / value object", "domain"))
    return out


def _ctx_components(ts: TechSpec) -> list[tuple[str, str, str, str]]:
    """`_components` with each identifier namespaced by its container id (rule 5)."""
    prefix = _ident(ts.bounded_context)
    return [(f"{prefix}_{cid}", name, desc, tag) for cid, name, desc, tag in _components(ts)]


def _persistence_ports(ts: TechSpec) -> list[str]:
    """Namespaced component ids of this context's persistence ports — the ones that own a
    datastore (DB-per-service). A `*Gateway` is a remote call, not a DB, so it is excluded."""
    return [cid for cid, name, _desc, tag in _ctx_components(ts)
            if tag == "port.out" and _PERSISTENCE.search(name)]


def render_context_dsl(ts: TechSpec) -> str:
    """The component fragment for one bounded context — `!include`d by the master into
    that context's container block, so it references the container scope the master owns."""
    prefix = _ident(ts.bounded_context)
    comps = _ctx_components(ts)
    lines = [
        f"# Components for bounded context: {ts.bounded_context}",
        f"# Included by workspace.dsl into the `{prefix}` container.",
    ]
    for cid, name, desc, tag in comps:
        lines.append(f'{cid} = component "{_q(name)}" "{desc}" "{tag}"')
    ins = [c[0] for c in comps if c[3] == "port.in"]
    apps = [c[0] for c in comps if c[3] == "application"]
    doms = [c[0] for c in comps if c[3] == "domain"]
    outs = [c[0] for c in comps if c[3] == "port.out"]
    # A persistence port is "persists via"; a remote *Gateway is "calls" — never claim a
    # gateway is a datastore (mirrors the DB-ownership exclusion in _persistence_ports).
    out_label = {c[0]: ("persists via" if _PERSISTENCE.search(c[1]) else "calls")
                 for c in comps if c[3] == "port.out"}
    mids = apps or doms  # what an inbound port hands off to
    for i in ins:
        for m in mids:
            lines.append(f'{i} -> {m} "handles"')
    for a in apps:
        for d in doms:
            lines.append(f'{a} -> {d} "operates on"')
        for o in outs:
            lines.append(f'{a} -> {o} "{out_label[o]}"')
    if not apps:
        for d in doms:
            for o in outs:
                lines.append(f'{d} -> {o} "{out_label[o]}"')
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Master-model helpers (actors, externals, message bus, sagas)
# --------------------------------------------------------------------------- #

def _container_ids(spec: DesignSpec) -> set[str]:
    return {_ident(ts.bounded_context) for ts in spec.tech_specs}


def _uses_bus(spec: DesignSpec) -> bool:
    """The design is event-driven (choreography) — model a shared Message Bus."""
    return any(ts.events or ts.event_schemas for ts in spec.tech_specs)


def _actors(spec: DesignSpec) -> list[tuple[str, str]]:
    """(actor_id, label) people for the C4 L1 view, from the Use Cases' actors. Free-text
    is filtered (service/system tokens dropped), de-duplicated by identifier."""
    container_ids = _container_ids(spec)
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for uc in spec.use_cases:
        for raw in [uc.primary_actor, *uc.secondary_actors]:
            label = _q(raw)
            if not label:
                continue
            if _ACTOR_NOISE.search(label):
                continue
            ident = _ident(label)
            if not ident or ident in container_ids or ident in seen:
                continue
            seen.add(ident)
            out.append((f"actor_{ident}", label))
    return out


def _externals(spec: DesignSpec) -> list[tuple[str, str]]:
    """(ext_id, label) external systems — relationship/context-map endpoints that are not a
    known bounded context (e.g. a third-party gateway the design integrates with)."""
    container_ids = _container_ids(spec)
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    endpoints: list[str] = []
    for r in spec.relationships:
        endpoints += [r.upstream, r.downstream]
    for a, b in _MAP_EDGE.findall(spec.context_map or ""):
        endpoints += [a, b]
    for raw in endpoints:
        label = _q(raw)
        ident = _ident(label)
        if not label or not ident or ident in container_ids or ident in seen:
            continue
        seen.add(ident)
        out.append((f"ext_{ident}", label))
    return out


def _resolve_service(name: str, container_ids: set[str], actor_ids: set[str]) -> str | None:
    """Map a free-text saga-step service (or trigger) to a declared element id: a container
    (exact ident, then substring either way) or an actor. None when nothing matches."""
    ident = _ident(name)
    if ident in container_ids:
        return ident
    for cid in sorted(container_ids):
        if cid in ident or ident in cid:
            return cid
    if f"actor_{ident}" in actor_ids:
        return f"actor_{ident}"
    return None


def _saga_dynamics(spec: DesignSpec, actor_ids: set[str]) -> list[tuple[str, str, list[tuple[str, str, str]]]]:
    """For each Saga with resolvable steps, return (view_key, name, edges) for a happy-path
    dynamic view and (when any step compensates) a compensation view. `edges` is a list of
    (src_id, dst_id, label); a view is dropped unless it has >= 2 distinct nodes."""
    container_ids = _container_ids(spec)
    out: list[tuple[str, str, list[tuple[str, str, str]]]] = []
    used_keys: set[str] = set()

    def _key(base: str) -> str:
        key, n = base, 2
        while key in used_keys:
            key, n = f"{base}_{n}", n + 1
        used_keys.add(key)
        return key

    for saga in spec.sagas:
        steps = [s for s in saga.steps if s.service]
        if not steps:
            continue
        # resolve each step's service to a node id, in order
        resolved = [(s, _resolve_service(s.service, container_ids, actor_ids)) for s in steps]
        nodes = [(s, nid) for s, nid in resolved if nid]
        distinct = {nid for _s, nid in nodes}
        if len(distinct) < 2:
            continue  # a 1-node dynamic is useless and the CLI rejects dangling edges

        base = (_ident(saga.name) or _ident(saga.id) or "saga").title().replace("_", "")
        # happy path: trigger? -> n0 -> n1 -> ... using each step's success event as the label.
        # Number by EMISSION order (not step index) so the flow reads 1., 2., ... even when
        # the trigger collapses onto the first step's node (a self-edge is dropped).
        edges: list[tuple[str, str, str]] = []
        prev = _resolve_service(saga.trigger, container_ids, actor_ids) if saga.trigger else None
        for s, nid in nodes:
            if prev and prev != nid:
                n = len(edges) + 1
                label = _q(f"{n}. {s.action}" + (f" -> {s.success_event}" if s.success_event else "")) or f"{n}."
                edges.append((prev, nid, label))
            prev = nid
        if len({n for e in edges for n in (e[0], e[1])}) >= 2:
            out.append((_key(base), _q(saga.name) or saga.id, edges))

        # compensation: reverse order, only over steps that declare a compensating action
        comp_nodes = [(s, nid) for s, nid in nodes if s.compensation]
        comp_edges: list[tuple[str, str, str]] = []
        for i in range(len(comp_nodes) - 1, 0, -1):
            s, nid = comp_nodes[i]
            _ps, pid = comp_nodes[i - 1]
            if nid != pid:
                comp_edges.append((nid, pid, _q(f"Undo: {s.compensation}")))
        if len({n for e in comp_edges for n in (e[0], e[1])}) >= 2:
            out.append((_key(f"{base}Compensation"), f"{_q(saga.name) or saga.id} — compensation", comp_edges))
    return out


def _relationship_edges(spec: DesignSpec, container_ids: set[str]) -> list[str]:
    """Cross-context dependency edges for the master model. Prefer the typed
    `relationships` (downstream depends on upstream); fall back to parsing the
    `context_map` mermaid edges. Only emit edges whose endpoints are real containers."""
    edges: list[str] = []
    seen: set[tuple[str, str]] = set()
    for r in spec.relationships:
        d, u = _ident(r.downstream), _ident(r.upstream)
        if d in container_ids and u in container_ids and d != u and (d, u) not in seen:
            seen.add((d, u))
            kind = getattr(r.kind, "value", str(r.kind))
            label = _q(f"{kind}: {r.mechanism}" if r.mechanism else kind)
            edges.append(f'        {d} -> {u} "{label}"')
    if edges:
        return edges
    for a_raw, b_raw in _MAP_EDGE.findall(spec.context_map or ""):
        a, b = _ident(a_raw), _ident(b_raw)
        if a in container_ids and b in container_ids and a != b and (a, b) not in seen:
            seen.add((a, b))
            edges.append(f'        {a} -> {b} "uses"')
    return edges


# --------------------------------------------------------------------------- #
# Master workspace.dsl
# --------------------------------------------------------------------------- #

def render_workspace_dsl(spec: DesignSpec, requirement: str) -> str:
    sysid = "system"
    title = _q(spec.summary[:70]) or "System"
    container_ids = _container_ids(spec)
    actors = _actors(spec)
    actor_ids = {aid for aid, _label in actors}
    externals = _externals(spec)
    uses_bus = _uses_bus(spec)
    single = len(spec.tech_specs) == 1

    m: list[str] = ["    model {", "        !impliedRelationships true", ""]
    for aid, label in actors:
        m.append(f'        {aid} = person "{label}"')
    for eid, label in externals:
        m.append(f'        {eid} = softwareSystem "{label}" "" "External"')
    if actors or externals:
        m.append("")

    m.append(f'        {sysid} = softwareSystem "{title}" {{')
    for ts in spec.tech_specs:
        cid = _ident(ts.bounded_context)
        m.append(f'            {cid} = container "{_q(ts.bounded_context)}" "{_q(ts.summary)}" "BoundedContext" {{')
        m.append(f"                !include {cid}.dsl")
        m.append("            }")
        if _persistence_ports(ts):
            m.append(
                f'            {cid}_db = container "{_q(ts.bounded_context)} Database" '
                f'"Persistence owned by the {_q(ts.bounded_context)} context (DB-per-service)." '
                f'"Datastore" "Database"'
            )
    if uses_bus:
        m.append("            !include bus.dsl")
    m.append("            !docs documentation")
    m.append("            !adrs adr")
    m.append("        }")
    m.append("")

    # cross-context relationships (downstream -> upstream)
    m += _relationship_edges(spec, container_ids)
    # data ownership: each persistence port -> its context DB
    for ts in spec.tech_specs:
        cid = _ident(ts.bounded_context)
        for pid in _persistence_ports(ts):
            m.append(f'        {pid} -> {cid}_db "reads/writes" "JDBC"')
    # choreography: producer -> bus -> consumer(s). An event_schema normally lives on its
    # PRODUCER context (design-flow A8.2), but a model may misfile an INBOUND event on the
    # consumer's spec; detect that (the context is its own only consumer) and draw it as a
    # consume edge (bus -> ctx) instead of a wrong "publishes" edge.
    if uses_bus:
        for ts in spec.tech_specs:
            cid = _ident(ts.bounded_context)
            for ev in ts.event_schemas:
                name = _q(ev.event_name) or "event"
                consumer_ids = {_ident(c) for c in ev.consumers}
                others = sorted(c for c in consumer_ids if c in container_ids and c != cid)
                if cid in consumer_ids and not others:
                    m.append(f'        bus -> {cid} "{name}"')          # inbound, consumed
                else:
                    m.append(f'        {cid} -> bus "publishes {name}"')  # produced here
                    for c in others:
                        m.append(f'        bus -> {c} "{name}"')
            if not ts.event_schemas and ts.events:
                m.append(f'        {cid} -> bus "publishes domain events"')
    # actors -> the system (or the single container)
    for aid, _label in actors:
        target = _ident(spec.tech_specs[0].bounded_context) if single else sysid
        m.append(f'        {aid} -> {target} "uses"')
    # context <-> external systems
    for r in spec.relationships:
        u, d = _ident(r.upstream), _ident(r.downstream)
        label = _q(f"{getattr(r.kind, 'value', r.kind)}: {r.mechanism}" if r.mechanism
                   else getattr(r.kind, "value", str(r.kind)))
        if u in container_ids and d not in container_ids and _ident(r.downstream):
            m.append(f'        {u} -> ext_{d} "{label}"')
        elif d in container_ids and u not in container_ids and _ident(r.upstream):
            m.append(f'        {d} -> ext_{u} "{label}"')
    m.append("    }")

    # ----- views -----
    v: list[str] = [
        "    views {",
        f'        systemContext {sysid} "SystemContext" {{',
        "            include *",
        "            autolayout tb",
        "        }",
        f'        container {sysid} "Containers" {{',
        "            include *",
        "            autolayout lr",
        "        }",
    ]
    for ts in spec.tech_specs:
        cid = _ident(ts.bounded_context)
        v += [
            f'        component {cid} "{cid}_components" {{',
            "            include *",
            "            autolayout lr",
            "        }",
        ]
    for key, name, edges in _saga_dynamics(spec, actor_ids):
        v.append(f'        dynamic {sysid} "{key}" "{name}" {{')
        for src, dst, label in edges:
            v.append(f'            {src} -> {dst} "{label}"')
        v.append("            autolayout lr")
        v.append("        }")
    v.append("        !include styles.dsl")
    v.append("    }")

    header = f'workspace "{title}" "{_q(requirement[:160])}" {{'
    return "\n".join([header, "", *m, "", *v, "}"]) + "\n"


# --------------------------------------------------------------------------- #
# styles.dsl, bus.dsl
# --------------------------------------------------------------------------- #

def render_styles_dsl() -> str:
    """Tag → shape/colour. Form follows the C4 element types plus our model tags."""
    return (
        "styles {\n"
        '    element "Person" {\n        shape Person\n        background #08427b\n        color #ffffff\n    }\n'
        '    element "Software System" {\n        background #1168bd\n        color #ffffff\n    }\n'
        '    element "Container" {\n        background #438dd5\n        color #ffffff\n    }\n'
        '    element "Component" {\n        background #85bbf0\n        color #000000\n        shape RoundedBox\n    }\n'
        '    element "Database" {\n        shape Cylinder\n        background #228b22\n        color #ffffff\n    }\n'
        '    element "MessageBus" {\n        shape Pipe\n        background #e07a5f\n        color #ffffff\n    }\n'
        '    element "External" {\n        background #999999\n        color #ffffff\n    }\n'
        '    element "port.in" {\n        background #b3d4fc\n    }\n'
        '    element "port.out" {\n        background #c8e6c9\n    }\n'
        "}\n"
    )


def render_bus_dsl() -> str:
    """The shared Message Bus container — `!include`d into the softwareSystem block."""
    return (
        "# Shared asynchronous backbone (choreography). Included into the softwareSystem.\n"
        'bus = container "Event Bus" "Asynchronous message backbone for domain events "'
        ' "Message Broker" "MessageBus"\n'
    )


# --------------------------------------------------------------------------- #
# documentation/ (!docs) — prose embedding the views
# --------------------------------------------------------------------------- #

def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {_q(i)}" for i in items) if items else "_(none)_"


def render_docs(spec: DesignSpec) -> dict[str, str]:
    """Prose documentation embedding the views via `![alt](embed:ViewKey)` (rule 4).
    Always emits at least 01-introduction.md so `!docs` never points at an empty dir."""
    actor_ids = {aid for aid, _ in _actors(spec)}
    docs: dict[str, str] = {}
    docs["01-introduction.md"] = (
        "# Introduction\n\n"
        f"{_q(spec.summary)}\n\n"
        "## Goals\n\n"
        f"{_bullets(spec.goals)}\n\n"
        "## System Context (C4 L1)\n\n"
        "![System Context](embed:SystemContext)\n"
    )
    docs["02-containers.md"] = (
        "# Containers (C4 L2)\n\n"
        f"**Architecture style:** {_q(spec.architecture_style) or '_(unspecified)_'}\n\n"
        "## Design principles\n\n"
        f"{_bullets(spec.principles)}\n\n"
        "## Cross-cutting decisions\n\n"
        f"{_bullets(spec.decisions)}\n\n"
        "![Containers](embed:Containers)\n"
    )
    comp = ["# Components (C4 L3)\n"]
    for ts in spec.tech_specs:
        cid = _ident(ts.bounded_context)
        comp.append(f"## {_q(ts.bounded_context)}\n\n{_q(ts.summary)}\n\n"
                    f"![{_q(ts.bounded_context)}](embed:{cid}_components)\n")
    docs["03-components.md"] = "\n".join(comp)

    dynamics = _saga_dynamics(spec, actor_ids)
    if dynamics:
        integ = ["# Integration (dynamic flows)\n"]
        for key, name, _edges in dynamics:
            integ.append(f"## {name}\n\n![{name}](embed:{key})\n")
        docs["04-integration.md"] = "\n".join(integ)

    if spec.glossary:
        rows = ["# Glossary (Ubiquitous Language)\n",
                "| Term | Definition | Bounded Context |", "|---|---|---|"]
        for g in spec.glossary:
            rows.append(f"| {_q(g.term)} | {_q(g.definition)} | {_q(g.bounded_context)} |")
        docs["05-glossary.md"] = "\n".join(rows) + "\n"
    return docs


# --------------------------------------------------------------------------- #
# adr/ (!adrs) — MADR-lite, numbered only (rule 3: no README in this dir)
# --------------------------------------------------------------------------- #

def _madr(num: int, title: str, context: str, body: str) -> str:
    """Minimal valid MADR card. For a free-text decision the Context and Decision carry
    the same text — we do not invent rationale the design never recorded."""
    return (
        f"# {num}. {_q(title)}\n\n"
        f"- Status: Accepted\n"
        f"- Context: {_q(context)}\n\n"
        f"## Context\n\n{body.strip()}\n\n"
        f"## Decision\n\n{body.strip()}\n\n"
        f"## Consequences\n\n_Recorded as accepted; see the linked Tech Spec / model for effect._\n"
    )


def render_adrs(spec: DesignSpec) -> dict[str, str]:
    """One numbered ADR per cross-cutting decision (system) and per-context decision.
    Always emits a `0000-about-these-adrs.md` index — numbered, so it is a valid ADR file
    and NOT a README (which would break `!adrs`)."""
    files: dict[str, str] = {}
    rows = ["# 0. About these ADRs\n\n"
            "> Architecture Decision Records for this change — one decision per file, MADR-lite,\n"
            "> numbered only (no README in this directory). Generated from the DesignSpec.\n\n"
            "| # | Title | Context |", "|---|---|---|"]
    n = 0
    entries: list[tuple[str, str, str]] = []  # (title, context, body)
    for d in spec.decisions:
        clean = _strip_adr_prefix(d)
        entries.append((clean, "system-wide", clean))
    for ts in spec.tech_specs:
        for d in ts.adrs:
            clean = _strip_adr_prefix(d)
            entries.append((clean, ts.bounded_context, clean))
    for title, context, body in entries:
        n += 1
        fname = f"{n:04d}-{_slug(title)}.md"
        files[f"adr/{fname}"] = _madr(n, title[:70], context, body)
        rows.append(f"| {n:04d} | {_q(title[:70])} | {_q(context)} |")
    files["adr/0000-about-these-adrs.md"] = "\n".join(rows) + "\n"
    return files


# --------------------------------------------------------------------------- #
# README index + CI workflow
# --------------------------------------------------------------------------- #

def render_readme(spec: DesignSpec, docs_subdir: str) -> str:
    sub = docs_subdir.split("/")[-1]
    ctx_rows = "\n".join(
        f"| Dev — {_q(ts.bounded_context)} | internal structure | `{_ident(ts.bounded_context)}_components` |"
        for ts in spec.tech_specs
    )
    return (
        "# Architecture as Code\n\n"
        "Architecture description (C4 + ISO/IEC/IEEE 42010) as Structurizr DSL — one model, "
        "many views. Generated from the design (`../AD.md` + the Tech Specs).\n\n"
        "## Files\n\n"
        "- `workspace.dsl` — master (model + views + `!docs` + `!adrs`)\n"
        "- `styles.dsl` — tag → shape/colour\n"
        "- `<context>.dsl` — components inside each bounded context\n"
        "- `documentation/` — prose embedding the views (`!docs`)\n"
        "- `adr/` — numbered MADR decisions (`!adrs`)\n\n"
        "## Views by stakeholder\n\n"
        "| Stakeholder | Concern | View key |\n|---|---|---|\n"
        "| Business / PO | scope & external actors | `SystemContext` |\n"
        "| Architect | services + datastores, sync/async | `Containers` |\n"
        f"{ctx_rows}\n\n"
        "## Render / validate\n\n"
        "```bash\n"
        "# View interactively at http://localhost:8080\n"
        f"docker run -it --rm -p 8080:8080 -v \"$PWD/{docs_subdir}:/usr/local/structurizr\" structurizr/lite\n\n"
        f"# Validate (pin a dated tag — NEVER :latest, which is a no-op stub)\n"
        f"docker run --rm -v \"$PWD:/work\" -w /work {_CLI_TAG} \\\n"
        f"  validate -workspace {docs_subdir}/workspace.dsl\n"
        "```\n"
    )


def render_ci_workflow(docs_subdir: str) -> str:
    """A GitHub Actions workflow that validates + exports the DSL on every change — the
    governance gate that keeps the docs from drifting. Pinned to a working CLI tag."""
    return (
        "name: AaC (Structurizr) validate\n\n"
        "# Pin a dated tag. NEVER the :latest tag — it is a deprecation no-op stub\n"
        "# (prints a banner, exit 0, runs no CLI), which makes validate/export silently pass.\n"
        "on:\n"
        "  push:\n"
        "    paths:\n"
        f"      - '{docs_subdir}/**'\n"
        "      - '.github/workflows/aac.yml'\n"
        "  pull_request:\n"
        "    paths:\n"
        f"      - '{docs_subdir}/**'\n"
        "      - '.github/workflows/aac.yml'\n"
        "  workflow_dispatch:\n\n"
        "jobs:\n"
        "  validate:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/checkout@v5\n"
        "      - name: Validate Structurizr DSL workspace\n"
        "        run: |\n"
        f"          docker run --rm -v \"$PWD:/work\" -w /work {_CLI_TAG} \\\n"
        f"            validate -workspace {docs_subdir}/workspace.dsl\n"
        "      - name: Export all views (Mermaid)\n"
        "        run: |\n"
        "          mkdir -p build/aac\n"
        f"          docker run --rm -v \"$PWD:/work\" -w /work {_CLI_TAG} \\\n"
        f"            export -workspace {docs_subdir}/workspace.dsl -format mermaid -output build/aac\n"
        "      - name: Upload exported diagrams\n"
        "        if: always()\n"
        "        uses: actions/upload-artifact@v5\n"
        "        with:\n"
        "          name: aac-diagrams\n"
        "          path: build/aac\n"
    )


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #

def render_structurizr(spec: DesignSpec, requirement: str,
                       docs_subdir: str = _DSL_SUBDIR,
                       with_ci: bool = False) -> dict[str, str]:
    """All Architecture-as-Code files for a design, as {repo-relative path: content}: the
    master workspace + styles + per-context fragments + (event-driven) the bus + the
    embedded documentation and ADRs + a README index. With `with_ci`, also a CI workflow
    at the repo-root `.github/workflows/aac.yml`."""
    files: dict[str, str] = {
        workspace_path(docs_subdir): render_workspace_dsl(spec, requirement),
        f"{docs_subdir}/styles.dsl": render_styles_dsl(),
        f"{docs_subdir}/README.md": render_readme(spec, docs_subdir),
    }
    for ts in spec.tech_specs:
        files[context_path(ts, docs_subdir)] = render_context_dsl(ts)
    if _uses_bus(spec):
        files[f"{docs_subdir}/bus.dsl"] = render_bus_dsl()
    for name, content in render_docs(spec).items():
        files[f"{docs_subdir}/documentation/{name}"] = content
    for path, content in render_adrs(spec).items():
        files[f"{docs_subdir}/{path}"] = content
    if with_ci:
        files[".github/workflows/aac.yml"] = render_ci_workflow(docs_subdir)
    return files
