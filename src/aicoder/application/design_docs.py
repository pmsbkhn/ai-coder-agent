"""Render a DesignSpec into explicit, reviewable Markdown artifacts (M07), following
the org's house style:

- **Requirements** — (Slice B, only with a structured intake) the binding US/AC/NFR
  contract (templates A1/A3) + the AC→test traceability matrix proving every acceptance
  criterion is pinned by a locked test (what the linter's T1/T3 enforce).
- **AD** — a SAD-style Architecture Description (system level): goals, architecture
  style + principles, bounded-context map, cross-cutting decisions, and the
  AD↔TechSpec index (links to requirements.md when present).
- **Tech Spec** — one per bounded context (1 BC = 1 Tech Spec): Context & Scope,
  Requirements (FR/NFR), Module + C&C views, Domain model + Invariants, Data model
  (ERD), Decisions (ADR-style), Test strategy, Open questions.
- **Test Cases** — one per bounded context: the TC-XXX-NN cases grouped by kind
  (domain invariant / adapter & integration / fitness function), each linking to its
  executable oracle file when present.

Pure functions over domain models — no I/O, no infra — so they live in the
application layer; the orchestrator writes the strings out via the git tool, and an
architect reviews them at the approval gate before coding.
"""

from __future__ import annotations

import re

from aicoder.domain.models import DesignSpec, RequirementSpec, TechSpec

_DOCS_SUBDIR = "docs/design"


def _slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return s or "context"


def tech_spec_path(ts: TechSpec, docs_dir: str = _DOCS_SUBDIR) -> str:
    return f"{docs_dir}/techspec-{_slug(ts.bounded_context)}.md"


def test_cases_path(ts: TechSpec, docs_dir: str = _DOCS_SUBDIR) -> str:
    return f"{docs_dir}/testcases-{_slug(ts.bounded_context)}.md"


def ad_path(docs_dir: str = _DOCS_SUBDIR) -> str:
    return f"{docs_dir}/AD.md"


def requirements_path(docs_dir: str = _DOCS_SUBDIR) -> str:
    return f"{docs_dir}/requirements.md"


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items) if items else "_(none)_"


def _section(title: str, body: str) -> str:
    return f"## {title}\n{body}\n\n"


def _block(text: str) -> str:
    """Embed a free-form field (may already contain a mermaid fence) verbatim."""
    return text.strip() if text and text.strip() else "_(none)_"


# --------------------------------------------------------------------------- #
# AD (SAD-style)
# --------------------------------------------------------------------------- #

def _glossary_section(spec: DesignSpec) -> str:
    """Template A4 — the Ubiquitous-Language table. Returns "" when empty. The Bounded
    Context column is the point: the SAME term in two contexts is the split signal."""
    if not spec.glossary:
        return ""
    rows = ["| ID | Term | Definition | Bounded Context | Aliases to avoid | Example |",
            "|---|---|---|---|---|---|"]
    for g in spec.glossary:
        rows.append(
            f"| {g.id} | {_md_escape(g.term)} | {_md_escape(g.definition)} | "
            f"{_md_escape(g.bounded_context)} | {_md_escape(', '.join(g.aliases_to_avoid))} | "
            f"{_md_escape(g.example)} |"
        )
    return _section("Ubiquitous Language (Glossary)", "\n".join(rows))


def _use_cases_section(spec: DesignSpec) -> str:
    """Template A2 — derived Use Cases grouping User Stories. Returns "" when empty."""
    if not spec.use_cases:
        return ""
    blocks: list[str] = []
    for uc in spec.use_cases:
        head = " ".join(p for p in [uc.id, f"— {uc.name}" if uc.name else ""] if p)
        meta = []
        if uc.primary_actor:
            meta.append(f"primary: {uc.primary_actor}")
        if uc.secondary_actors:
            meta.append(f"secondary: {', '.join(uc.secondary_actors)}")
        if uc.traces_to:
            meta.append(f"from {', '.join(uc.traces_to)}")
        lines = [f"### {head}" + (f"  _({'; '.join(meta)})_" if meta else "")]
        if uc.preconditions:
            lines.append(f"- **Pre:** {uc.preconditions}")
        if uc.postconditions:
            lines.append(f"- **Post:** {uc.postconditions}")
        if uc.main_flow:
            lines.append("- **Main flow:** " + " ".join(f"{i+1}. {s}" for i, s in enumerate(uc.main_flow)))
        if uc.alt_flows:
            lines.append("- **Alt / exceptions:** " + "; ".join(uc.alt_flows))
        blocks.append("\n".join(lines))
    return _section("Use Cases", "\n\n".join(blocks))


def _relationships_section(spec: DesignSpec) -> str:
    """Template A6 — the typed Context-Map relationships table. Returns "" when empty."""
    if not spec.relationships:
        return ""
    rows = ["| ID | Upstream | Downstream | Kind | Mechanism | Notes |",
            "|---|---|---|---|---|---|"]
    for r in spec.relationships:
        rows.append(
            f"| {r.id} | {_md_escape(r.upstream)} | {_md_escape(r.downstream)} | "
            f"{r.kind.value} | {_md_escape(r.mechanism)} | {_md_escape(r.notes)} |"
        )
    return _section("Context relationships (typed Context Map)", "\n".join(rows))


def _sagas_section(spec: DesignSpec) -> str:
    """Template A8.3 — the Saga / Process Manager specs (steps + compensation). "" when empty."""
    if not spec.sagas:
        return ""
    blocks: list[str] = []
    for s in spec.sagas:
        head = " ".join(p for p in [s.id, f"— {s.name}" if s.name else ""] if p)
        meta = f"**Trigger:** {s.trigger or '—'} · **Kind:** {s.kind}"
        if s.timeout:
            meta += f" · **Timeout:** {s.timeout}"
        if s.traces_to:
            meta += f" · **Traces:** {', '.join(s.traces_to)}"
        lines = [f"### {head}", meta]
        if s.steps:
            lines += ["", "| # | Service | Action | Success event | Compensation |",
                      "|---|---|---|---|---|"]
            lines += [f"| {i} | {_md_escape(st.service)} | {_md_escape(st.action)} | "
                      f"{_md_escape(st.success_event)} | {_md_escape(st.compensation)} |"
                      for i, st in enumerate(s.steps, 1)]
        blocks.append("\n".join(lines))
    return _section("Sagas / Process Managers", "\n\n".join(blocks))


def render_ad(
    spec: DesignSpec, requirement: str, docs_dir: str = _DOCS_SUBDIR,
    requirements_link: str | None = None,
) -> str:
    """The umbrella Architecture Description (system level). When `requirements_link` is
    given (Slice B structured intake) the AD points at the requirements.md that holds the
    binding US/AC/NFR contract + the AC→test traceability matrix."""
    req_pointer = (
        f"> 📋 Binding requirements & AC→test traceability: "
        f"[`{requirements_link}`]({requirements_link})\n\n"
        if requirements_link else ""
    )
    glossary = _glossary_section(spec)
    use_cases = _use_cases_section(spec)
    bc_rows = "\n".join(
        f"- **{ts.bounded_context}** → "
        f"[`{tech_spec_path(ts, docs_dir).split('/')[-1]}`]({tech_spec_path(ts, docs_dir).split('/')[-1]}) "
        f"· tests [`{test_cases_path(ts, docs_dir).split('/')[-1]}`]({test_cases_path(ts, docs_dir).split('/')[-1]}) "
        f"— {ts.summary}"
        for ts in spec.tech_specs
    ) or "_(none)_"
    return (
        f"# Architecture Description\n\n"
        f"> System-level design for one change; reviewed by an architect before "
        f"implementation. One AD spans one or more Tech Specs — **1 bounded context = "
        f"1 Tech Spec**. Detailed per-context design lives in the linked Tech Specs.\n\n"
        f"{req_pointer}"
        f"## Requirement\n{requirement}\n\n"
        f"## Summary\n{spec.summary}\n\n"
        + _section("Goals", _bullets(spec.goals))
        + _section("Architecture style", _block(spec.architecture_style))
        + _section("Design principles", _bullets(spec.principles))
        + _section("Bounded-context map", _block(spec.context_map))
        + _section("Cross-cutting decisions", _bullets(spec.decisions))
        + _section("Non-functional requirements / constraints", _bullets(spec.nfr))
        + use_cases
        + glossary
        + _section("Bounded contexts (→ Tech Spec · Test Cases)", bc_rows)
        + _relationships_section(spec)
        + _sagas_section(spec)
    )


# --------------------------------------------------------------------------- #
# Requirements (structured intake — Slice B): US/NFR tables + traceability matrix
# --------------------------------------------------------------------------- #

def _md_escape(text: str) -> str:
    """Keep a free-text cell on one table row (escape pipes / newlines)."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def render_requirements(
    req_spec: RequirementSpec, design: DesignSpec | None = None,
    docs_dir: str = _DOCS_SUBDIR, review=None,
) -> str:
    """The human-authored requirements contract (templates A1/A3) plus, when a design is
    available, the AC→test traceability matrix that proves every acceptance criterion is
    pinned by a locked test (the T1/T3 the linter enforces). `design` may be None to
    render the contract alone. When `review` (a TestReview) is supplied, the matrix also
    flags the criteria an adversarial concern is linked to (Option B: concern→AC)."""
    out: list[str] = ["# Requirements\n",
                      "> Binding contract for this change — the agent designs and tests to "
                      "satisfy every `AC-*` and `NFR-*` below; it does not invent scope.\n"]
    if req_spec.title:
        out.append(f"**{req_spec.title}**\n")

    # User Stories (template A1)
    out.append("## User Stories\n")
    for us in req_spec.stories:
        head = " ".join(p for p in [us.id, f"— {us.title}" if us.title else ""] if p)
        if us.priority:
            head += f" _(priority: {us.priority})_"
        out.append(f"### {head}")
        if us.as_a or us.i_want or us.so_that:
            out.append(f"As a **{us.as_a}**, I want **{us.i_want}**, so that **{us.so_that}**.\n")
        if us.acceptance:
            out.append("| AC | Criterion |")
            out.append("|---|---|")
            for ac in us.acceptance:
                out.append(f"| {ac.id} | {_md_escape(ac.as_text())} |")
            out.append("")

    # NFRs (template A3)
    out.append("## Non-functional requirements (ISO 25010)\n")
    if req_spec.nfrs:
        out.append("| ID | Category | Metric | Measurement | Source | Scope |")
        out.append("|---|---|---|---|---|---|")
        for n in req_spec.nfrs:
            out.append(
                f"| {n.id} | {n.category.value} | {_md_escape(n.metric)} | "
                f"{_md_escape(n.measurement)} | {_md_escape(n.source)} | {_md_escape(n.scope)} |"
            )
        out.append("")
    else:
        out.append("_(none)_\n")

    if design is not None:
        out.append(_render_traceability(req_spec, design, review))
    return "\n".join(out) + "\n"


def _render_traceability(req_spec: RequirementSpec, design: DesignSpec, review=None) -> str:
    """AC→test and NFR→test matrices computed from the proposed tests' `traces_to`. An
    uncovered AC is flagged ⚠️ (the linter's T1 also blocks it under review_strict).

    When a `review` (TestReview) is supplied, an AC that an adversarial concern is linked to
    (`concern_items[].traces_to`) is marked ⚠️ even though a tracing test exists — ✅ here
    means only "a locked test traces to this AC", NOT "the behaviour is verified correct";
    the linked concern is shown so a nominally-covered criterion is not silently trusted."""
    # id -> list of test labels that trace to it (locked tests carry a 🔒)
    by_id: dict[str, list[str]] = {}
    for t in design.all_tests():
        label = (t.id or t.path or t.title or "test")
        if t.path and t.content:
            label += " 🔒"
        for rid in t.traces_to:
            by_id.setdefault(rid, []).append(label)

    # id -> concern texts the reviewer linked to it (Option B: structured concern→AC).
    concern_by_id: dict[str, list[str]] = {}
    for c in (getattr(review, "concern_items", None) or []):
        for rid in c.traces_to:
            if c.text:
                concern_by_id.setdefault(rid, []).append(c.text)

    lines = ["## Traceability (AC → locked test)\n",
             "> ✅ = a locked test traces to this AC (traceability), **not** a guarantee the "
             "behaviour is correct. ⚠️ concern = a tracing test exists but the reviewer flagged it.\n",
             "| AC | Covered by | Status | Review concern |", "|---|---|---|---|"]
    for ac in req_spec.acceptance_ids:
        tests = by_id.get(ac, [])
        concerns = concern_by_id.get(ac, [])
        if concerns:
            status = "⚠️ concern"
        elif tests:
            status = "✅"
        else:
            status = "⚠️ uncovered"
        lines.append(f"| {ac} | {', '.join(tests) or '—'} | {status} | "
                     f"{_md_escape('; '.join(concerns)) if concerns else '—'} |")
    lines.append("")
    if req_spec.nfrs:
        lines += ["## Traceability (NFR → test, advisory)\n",
                  "| NFR | Referenced by | Review concern |", "|---|---|---|"]
        for nfr in req_spec.nfrs:
            concerns = concern_by_id.get(nfr.id, [])
            lines.append(f"| {nfr.id} | {', '.join(by_id.get(nfr.id, [])) or '—'} | "
                         f"{_md_escape('; '.join(concerns)) if concerns else '—'} |")
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Tech Spec (core design template)
# --------------------------------------------------------------------------- #

def _event_flow_section(ts: TechSpec) -> str:
    """Template A5 — the Command → Event → Policy → Read-Model tables for one context.
    Returns "" when the context models no event flow (a plain CRUD change), so a simple
    change's Tech Spec is not padded with empty tables."""
    if not (ts.commands or ts.events or ts.policies or ts.read_models):
        return ""
    p: list[str] = ["## 5.1 Event flow (Command → Event → Policy → Read Model)\n"]
    if ts.commands:
        p += ["**Commands**\n",
              "| ID | Name | Actor | Aggregate | Input | Precondition | Traces |",
              "|---|---|---|---|---|---|---|"]
        p += [f"| {c.id} | {_md_escape(c.name)} | {_md_escape(c.actor)} | "
              f"{_md_escape(c.aggregate)} | {_md_escape(c.input)} | "
              f"{_md_escape(c.precondition)} | {', '.join(c.traces_to)} |" for c in ts.commands]
        p.append("")
    if ts.events:
        p += ["**Domain Events**\n",
              "| ID | Name (past tense) | Aggregate | Data | Traces |",
              "|---|---|---|---|---|"]
        p += [f"| {e.id} | {_md_escape(e.name)} | {_md_escape(e.aggregate)} | "
              f"{_md_escape(e.data)} | {', '.join(e.traces_to)} |" for e in ts.events]
        p.append("")
    if ts.policies:
        p += ["**Policies** (When event → then command — source of async flows)\n",
              "| ID | Rule | When (event) | Then (command) | Traces |",
              "|---|---|---|---|---|"]
        p += [f"| {pol.id} | {_md_escape(pol.rule)} | {pol.when_event} | "
              f"{pol.then_command} | {', '.join(pol.traces_to)} |" for pol in ts.policies]
        p.append("")
    if ts.read_models:
        p += ["**Read Models**\n",
              "| ID | Name | Source events | Serves | Traces |",
              "|---|---|---|---|---|"]
        p += [f"| {r.id} | {_md_escape(r.name)} | {', '.join(r.source_events)} | "
              f"{_md_escape(r.serves)} | {', '.join(r.traces_to)} |" for r in ts.read_models]
        p.append("")
    return "\n".join(p) + "\n"


def _integration_section(ts: TechSpec) -> str:
    """Template A8.1/A8.2 — the sync API + async event-schema contracts for one context.
    Returns "" when the context exposes no integration contract (an internal-only change)."""
    if not (ts.apis or ts.event_schemas):
        return ""
    p: list[str] = ["## 5.2 Integration contracts (sync APIs / async events)\n"]
    if ts.apis:
        p += ["**APIs (sync — OpenAPI digest)**\n",
              "| ID | Method | Path | Summary | Auth | Idempotency | Traces |",
              "|---|---|---|---|---|---|---|"]
        p += [f"| {a.id} | {a.method} | {_md_escape(a.path)} | {_md_escape(a.summary)} | "
              f"{_md_escape(a.auth)} | {_md_escape(a.idempotency)} | {', '.join(a.traces_to)} |"
              for a in ts.apis]
        p.append("")
    if ts.event_schemas:
        p += ["**Events (async — CloudEvents)**\n",
              "| ID | Event | Consumers | Channel | Versioning | Reliability | Traces |",
              "|---|---|---|---|---|---|---|"]
        p += [f"| {e.id} | {_md_escape(e.event_name)} | {_md_escape(', '.join(e.consumers))} | "
              f"{_md_escape(e.channel)} | {_md_escape(e.versioning)} | {_md_escape(e.reliability)} | "
              f"{', '.join(e.traces_to)} |" for e in ts.event_schemas]
        p.append("")
    return "\n".join(p) + "\n"


def render_tech_spec(ts: TechSpec, docs_dir: str = _DOCS_SUBDIR) -> str:
    """The technical specification for one bounded context (core design sections)."""
    # One file can back several cases (many @Test methods) — list each oracle path once,
    # in first-seen order, so §9 is not a duplicated dump of the same file.
    oracle_paths: list[str] = []
    for t in ts.test_plan:
        if t.path and t.path not in oracle_paths:
            oracle_paths.append(t.path)
    tests_line = (
        f"See [`{test_cases_path(ts, docs_dir).split('/')[-1]}`]"
        f"({test_cases_path(ts, docs_dir).split('/')[-1]}) for the full case list. "
        f"Executable oracle (locked):\n"
        + (_bullets([f"`{p}`" for p in oracle_paths])
           if oracle_paths else "_(spec-only — no executable file)_")
    )
    return (
        f"# Tech Spec — {ts.bounded_context}\n\n"
        + (f"> **Classification:** {ts.classification}\n\n" if ts.classification else "")
        + _section("1. Context & Scope", _block(ts.summary))
        + _section("2. Requirements — Functional (FR)", _bullets(ts.requirements_functional))
        + _section("   Requirements — Non-functional / SLO", _bullets(ts.requirements_nonfunctional))
        + _section("3. Module view (static structure)", _block(ts.module_view))
        + _section("4. C&C view (runtime components & connectors)", _block(ts.cnc_view))
        + _section("   Affected components", _bullets(ts.affected))
        + _section("   Interface / contract changes (ports)", _bullets(ts.interface_changes))
        + _section("5. Domain model", _block(ts.domain_model))
        + _section("   Invariants (enforced in the aggregate)", _bullets(ts.invariants))
        + _event_flow_section(ts)
        + _integration_section(ts)
        + _section("6. Data model (ERD / schema)", _block(ts.erd))
        + _section("7. Key flows", _block(ts.key_flows))
        + _section("8. Decisions (ADR-style)", _bullets(ts.adrs) if ts.adrs else _block(ts.adr_notes))
        + _section("9. Test strategy", tests_line)
        + _section("10. Open questions", _bullets(ts.open_questions))
    )


# --------------------------------------------------------------------------- #
# Test Cases (TC-XXX-NN house style)
# --------------------------------------------------------------------------- #

_KIND_TITLES = {
    "domain": "Domain invariant cases (guard clauses in the Aggregate Root)",
    "adapter": "Adapter & integration cases (security / persistence)",
    "fitness": "Fitness functions (architecture rules)",
}


def _render_case(t) -> str:
    head = " ".join(p for p in [t.id, f"[{t.title}]" if t.title else ""] if p).strip() or "TC"
    lines = [f"**{head}**"]
    if t.spec:
        lines.append(t.spec.strip())
    if t.path:
        lines.append(f"_Oracle:_ `{t.path}`")
    elif t.rationale:
        lines.append(f"_Rationale:_ {t.rationale}")
    return "\n\n".join(lines)


def render_test_cases(ts: TechSpec, docs_dir: str = _DOCS_SUBDIR) -> str:
    """The TC-XXX-NN test-case specification for one bounded context, grouped by kind.
    Mirrors the org's *-tests.txt house style; each case links to its locked oracle."""
    out = [f"# Test Cases — {ts.bounded_context}\n",
           f"> Acceptance cases for `{tech_spec_path(ts, docs_dir).split('/')[-1]}`. "
           f"Approved cases with an oracle file are **locked** (the Coder implements to "
           f"pass them, may not edit them). Format: `TC-<CTX>-NN [Title]: setup → action "
           f"→ assert`.\n"]
    by_kind: dict[str, list] = {}
    for t in ts.test_plan:
        by_kind.setdefault(t.kind or "domain", []).append(t)
    for kind in ("domain", "adapter", "fitness"):
        cases = by_kind.get(kind)
        if not cases:
            continue
        out.append(f"## {_KIND_TITLES.get(kind, kind)}\n")
        out.append("\n\n".join(_render_case(t) for t in cases))
        out.append("")
    # any unknown kinds
    for kind, cases in by_kind.items():
        if kind in ("domain", "adapter", "fitness"):
            continue
        out.append(f"## {kind}\n")
        out.append("\n\n".join(_render_case(t) for t in cases))
        out.append("")
    return "\n".join(out) + "\n"
