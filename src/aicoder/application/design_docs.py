"""Render a DesignSpec into explicit, reviewable Markdown artifacts (M07), following
the org's three-document house style:

- **AD** — a SAD-style Architecture Description (system level): goals, architecture
  style + principles, bounded-context map, cross-cutting decisions, and the
  AD↔TechSpec index.
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

from aicoder.domain.models import DesignSpec, TechSpec

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

def render_ad(spec: DesignSpec, requirement: str, docs_dir: str = _DOCS_SUBDIR) -> str:
    """The umbrella Architecture Description (system level)."""
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
        f"## Requirement\n{requirement}\n\n"
        f"## Summary\n{spec.summary}\n\n"
        + _section("Goals", _bullets(spec.goals))
        + _section("Architecture style", _block(spec.architecture_style))
        + _section("Design principles", _bullets(spec.principles))
        + _section("Bounded-context map", _block(spec.context_map))
        + _section("Cross-cutting decisions", _bullets(spec.decisions))
        + _section("Non-functional requirements / constraints", _bullets(spec.nfr))
        + _section("Bounded contexts (→ Tech Spec · Test Cases)", bc_rows)
    )


# --------------------------------------------------------------------------- #
# Tech Spec (core design template)
# --------------------------------------------------------------------------- #

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
