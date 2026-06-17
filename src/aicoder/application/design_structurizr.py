"""Render a DesignSpec into Structurizr DSL (Architecture-as-Code, C4) — a master
`workspace.dsl` plus one fragment per bounded context, mirroring the Markdown set:

- **workspace.dsl** (≈ the AD): one `softwareSystem`; each bounded context is a
  `container`; cross-context dependencies become relationships (from the typed
  `relationships`, falling back to the `context_map` edges); plus a System Context
  view, a Container view, and one Component view per context.
- **<context>.dsl** (≈ a Tech Spec): the components INSIDE that context's container —
  inbound use-case ports, the application service, the aggregate(s), and outbound
  repository/gateway ports — derived from the Tech Spec's `interface_changes` +
  `domain_model`. The master `!include`s each fragment INTO its container block, so a
  fragment is only valid in the scope the master provides — i.e. the child files
  depend on the master, exactly like a Tech Spec depends on its AD.

Pure functions over the domain models — no I/O, no infra — so this lives in the
application layer next to `design_docs`; the orchestrator writes the strings out via
the git tool when the profile opts in (`design.formats` contains "structurizr"). The
DSL is generated from the already-validated, already-linted `DesignSpec`, so it is
valid by construction — the LLM never writes DSL directly (that would bypass the
structured-output validation + the L/T consistency linter).
"""

from __future__ import annotations

import re

from aicoder.domain.models import DesignSpec, TechSpec

_DSL_SUBDIR = "docs/design/structurizr"

# Type tokens that name a port / service / aggregate in the free-text contracts.
_IFACE = re.compile(r"\binterface\s+([A-Za-z_]\w*)")
_PORTISH = re.compile(r"\b([A-Z]\w*(?:UseCase|Port|Repository|Gateway|Service))\b")
_DECL = re.compile(r"\b(?:class|enum|record)\s+([A-Z]\w*)")
# A directed edge in a mermaid context map: `A --> B`, `A -.-> B`, `A -->|label| B`.
_MAP_EDGE = re.compile(r"\b([A-Za-z_]\w*)\b\s*-[.-]*->\s*(?:\|[^|]*\|\s*)?\b([A-Za-z_]\w*)\b")


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


def render_context_dsl(ts: TechSpec) -> str:
    """The component fragment for one bounded context — `!include`d by the master into
    that context's container block, so it references the container scope the master owns."""
    prefix = _ident(ts.bounded_context)
    # Structurizr identifiers are GLOBAL, so namespace each component by its container to
    # avoid clashing with the container id or a same-named type in another context.
    comps = [(f"{prefix}_{cid}", name, desc, tag) for cid, name, desc, tag in _components(ts)]
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
    mids = apps or doms  # what an inbound port hands off to
    for i in ins:
        for m in mids:
            lines.append(f'{i} -> {m} "handles"')
    for a in apps:
        for d in doms:
            lines.append(f'{a} -> {d} "operates on"')
        for o in outs:
            lines.append(f'{a} -> {o} "persists via"')
    if not apps:
        for d in doms:
            for o in outs:
                lines.append(f'{d} -> {o} "persists via"')
    return "\n".join(lines) + "\n"


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
            edges.append(f"        {d} -> {u} \"{label}\"")
    if edges:
        return edges
    for a_raw, b_raw in _MAP_EDGE.findall(spec.context_map or ""):
        a, b = _ident(a_raw), _ident(b_raw)
        if a in container_ids and b in container_ids and a != b and (a, b) not in seen:
            seen.add((a, b))
            edges.append(f"        {a} -> {b} \"uses\"")
    return edges


def render_workspace_dsl(spec: DesignSpec, requirement: str) -> str:
    """The master workspace — the system, one container per bounded context (each
    `!include`-ing its component fragment), the cross-context relationships, and the
    System Context / Container / per-context Component views."""
    sysid = "system"
    title = _q(spec.summary[:70]) or "System"
    container_ids = {_ident(ts.bounded_context) for ts in spec.tech_specs}

    model = ["    model {", f'        {sysid} = softwareSystem "{title}" {{']
    for ts in spec.tech_specs:
        cid = _ident(ts.bounded_context)
        model.append(
            f'            {cid} = container "{_q(ts.bounded_context)}" '
            f'"{_q(ts.summary)}" "BoundedContext" {{'
        )
        model.append(f"                !include {cid}.dsl")
        model.append("            }")
    model.append("        }")
    model += _relationship_edges(spec, container_ids)
    model.append("    }")

    views = [
        "    views {",
        f'        systemContext {sysid} "SystemContext" {{',
        "            include *",
        "            autolayout lr",
        "        }",
        f'        container {sysid} "Containers" {{',
        "            include *",
        "            autolayout lr",
        "        }",
    ]
    for ts in spec.tech_specs:
        cid = _ident(ts.bounded_context)
        views += [
            f'        component {cid} "{cid}_components" {{',
            "            include *",
            "            autolayout lr",
            "        }",
        ]
    views.append("    }")

    header = f'workspace "{title}" "{_q(requirement[:160])}" {{'
    return "\n".join([header, "", *model, "", *views, "}"]) + "\n"


def render_structurizr(spec: DesignSpec, requirement: str,
                       docs_subdir: str = _DSL_SUBDIR) -> dict[str, str]:
    """All Structurizr files for a design, as {repo-relative path: content}: the master
    workspace plus one fragment per bounded context."""
    files = {workspace_path(docs_subdir): render_workspace_dsl(spec, requirement)}
    for ts in spec.tech_specs:
        files[context_path(ts, docs_subdir)] = render_context_dsl(ts)
    return files
