"""Deterministic design linter (no LLM) — cross-document consistency checks over a
DesignSpec BEFORE it is locked as the oracle.

This complements the adversarial (LLM) Test Reviewer: the Reviewer judges whether the
*tests* adequately constrain the requirement, but a design can be perfectly testable
and still be internally self-contradictory in a way that makes the build fail no matter
how good the Coder is. These checks catch exactly that class of multi-bounded-context
inconsistency — the kind that produced HEALING_FAILED on the Digital Library e2e run:

  L1  a method invoked in a key-flow / sequence diagram is not declared in ANY
      interface/contract or on an aggregate in the domain model
      (e.g. ``LoanAggregate->>CatalogService: setCopyStatus(ON_LOAN)`` where
      ``CatalogService`` exposes no ``setCopyStatus``).
  L2  the same method name is declared with conflicting arity across two interface
      contracts — two contexts disagreeing on a shared operation's shape. (Service-vs-
      aggregate arity differences — e.g. ``LendingService.isOverdue(loanId, date)`` vs
      ``Loan.isOverdue(date)`` — are NOT flagged here: the service legitimately carries
      the id, so they are indistinguishable from a normal wrapper and are left to the
      contract-aware Reviewer to judge.)
  L3  a type crosses a bounded-context boundary without a single declared owner —
      either the same type is claimed by two contexts (L3a) or one context references a
      type owned by another with no shared-kernel / published-language decision (L3b).
      This is the gap that lets the Coder re-create ``Copy`` / ``CopyStatus`` per package.
  L4  status-enum suffix drift (``CopyStatus`` + ``LoanState``) — a naming convention
      that invites the Coder to define one name and the test to import the other.

Pure function over the domain models — no infra, no I/O, fully deterministic. Findings
are advisory by default (surfaced to the architect gate); under ``design.review_strict``
a non-empty result blocks the run before the human gate, just like a failed review.
"""

from __future__ import annotations

import re

from aicoder.domain.models import DesignSpec, TechSpec

# A method call / declaration: `name(args)`. Greedy-free param capture (no nested parens).
_METHOD = re.compile(r"\b([A-Za-z_]\w*)\s*\(([^()]*)\)")
# A project type token: a CamelCase / Capitalised identifier.
_TYPE_TOKEN = re.compile(r"\b([A-Z][A-Za-z0-9]+)\b")
# A type *declaration* inside a mermaid class/erd block.
_TYPE_DECL = re.compile(r"\b(?:class|enum|interface)\s+([A-Z]\w+)")
# Whether the design explicitly decided how types cross a context boundary.
_SHARED_KERNEL = re.compile(
    r"shared[- ]?kernel|published[- ]?language|anti[- ]?corruption|\bACL\b|conformist",
    re.IGNORECASE,
)

# mermaid sequence keywords that can look like `word(...)` but are not method calls.
_FLOW_KEYWORDS = {"alt", "opt", "loop", "par", "note", "activate", "deactivate",
                  "rect", "critical", "break", "and", "end"}
# Names that denote a service/port, not a domain type — a cross-context *call* target
# is expected (that is the orchestration); only crossing with a domain *type* is a smell.
_SERVICE_SUFFIXES = ("Service", "Port", "Repository", "Controller", "Facade",
                     "Adapter", "Oa", "Manager", "Client", "Gateway")


def _arity(params: str) -> int:
    return len([p for p in params.split(",") if p.strip()])


def _simple_type(path_or_name: str) -> str:
    """`.../catalog/Copy.java` or `Copy.java` -> `Copy`."""
    base = path_or_name.replace("\\", "/").rsplit("/", 1)[-1]
    return base[:-5] if base.endswith(".java") else base


def _declared_method_names(spec: DesignSpec) -> set[str]:
    """Every method name declared anywhere (interfaces + domain models) — for L1, which
    only asks "is this called-in-a-flow method declared SOMEWHERE?"."""
    names: set[str] = set()
    for ts in spec.tech_specs:
        text = "\n".join(ts.interface_changes) + "\n" + ts.domain_model
        names |= {name for name, _ in _METHOD.findall(text)}
    return names


def _interface_arities(spec: DesignSpec) -> dict[str, set[int]]:
    """Method name -> arities, drawn ONLY from interface contracts (not the domain
    model) — for L2. Two interface declarations disagreeing on arity is an unambiguous
    contract clash; mixing in the aggregate's arity would flag normal service wrappers."""
    out: dict[str, set[int]] = {}
    for ts in spec.tech_specs:
        for name, params in _METHOD.findall("\n".join(ts.interface_changes)):
            out.setdefault(name, set()).add(_arity(params))
    return out


def _owners(spec: DesignSpec) -> dict[str, set[str]]:
    """type name -> set of bounded contexts that own/declare it (from `affected` paths
    and mermaid `class`/`enum` declarations)."""
    out: dict[str, set[str]] = {}
    for ts in spec.tech_specs:
        names = {_simple_type(a) for a in ts.affected}
        names |= set(_TYPE_DECL.findall(ts.domain_model))
        for n in names:
            if n:
                out.setdefault(n, set()).add(ts.bounded_context)
    return out


def _referenced_types(ts: TechSpec) -> set[str]:
    text = "\n".join(ts.interface_changes) + "\n" + ts.domain_model + "\n" + ts.key_flows
    return set(_TYPE_TOKEN.findall(text))


def lint_design(spec: DesignSpec) -> list[str]:
    """Return an ordered, de-duplicated list of cross-document consistency findings.
    Empty list == the design is internally consistent on these checks."""
    issues: list[str] = []
    declared_names = _declared_method_names(spec)
    iface_arities = _interface_arities(spec)
    owners = _owners(spec)
    shared_kernel = any(
        _SHARED_KERNEL.search(t)
        for t in (*spec.principles, *spec.decisions,
                  *(a for ts in spec.tech_specs for a in ts.adrs))
    )

    # L1 — a key-flow calls a method nobody declares.
    for ts in spec.tech_specs:
        seen: set[str] = set()
        for name, _params in _METHOD.findall(ts.key_flows):
            if (name[:1].islower() and name not in declared_names
                    and name not in _FLOW_KEYWORDS and name not in seen):
                seen.add(name)
                issues.append(
                    f"L1 [{ts.bounded_context}] key-flow calls `{name}(...)` but no "
                    f"interface or domain method declares `{name}` — add it to a "
                    f"contract or fix the call (typo / wrong owner)."
                )

    # L2 — one method name, conflicting arity across two interface contracts.
    for name in sorted(iface_arities):
        arities = iface_arities[name]
        if len(arities) > 1:
            issues.append(
                f"L2 method `{name}` is declared with conflicting arity "
                f"({sorted(arities)}) across interface contracts — two contexts "
                f"disagree on the operation's shape; reconcile to one signature."
            )

    # L3a — the same type is owned by more than one bounded context.
    for t in sorted(owners):
        if len(owners[t]) > 1:
            issues.append(
                f"L3 type `{t}` is owned by multiple contexts "
                f"({sorted(owners[t])}) — declare a single owner / shared kernel so "
                f"the Coder does not re-create it per package."
            )

    # L3b — a context references another context's type without a sharing decision.
    if not shared_kernel:
        flagged: set[tuple[str, str]] = set()
        for ts in spec.tech_specs:
            for t in sorted(_referenced_types(ts)):
                own = owners.get(t)
                if not own or len(own) != 1 or ts.bounded_context in own:
                    continue
                if t.endswith(_SERVICE_SUFFIXES):
                    continue
                owner = next(iter(own))
                if (ts.bounded_context, t) in flagged:
                    continue
                flagged.add((ts.bounded_context, t))
                issues.append(
                    f"L3 context `{ts.bounded_context}` references type `{t}` owned by "
                    f"`{owner}` but the design declares no shared-kernel / "
                    f"published-language / ACL decision for crossing the boundary."
                )

    # L4 — status-enum suffix drift.
    statusish = [t for t in owners if t.endswith("Status")]
    stateish = [t for t in owners if t.endswith("State")]
    if statusish and stateish:
        issues.append(
            f"L4 mixed status-enum suffixes: {sorted(statusish)} use `…Status` but "
            f"{sorted(stateish)} use `…State` — standardize one convention so the "
            f"production code and the locked tests agree on the name."
        )

    return issues


def render_contracts(spec: DesignSpec) -> str:
    """A compact, per-context digest of the binding contracts (interfaces, invariants,
    domain model, key flows) — fed to the adversarial Reviewer so it can judge the
    tests AGAINST the contracts, not in a vacuum."""
    blocks: list[str] = []
    for ts in spec.tech_specs:
        lines = [f"## {ts.bounded_context}"]
        if ts.interface_changes:
            lines.append("Interfaces / contracts:")
            lines += [f"  - {c}" for c in ts.interface_changes]
        if ts.invariants:
            lines.append("Invariants:")
            lines += [f"  - {i}" for i in ts.invariants]
        if ts.domain_model.strip():
            lines += ["Domain model:", ts.domain_model.strip()]
        if ts.key_flows.strip():
            lines += ["Key flows:", ts.key_flows.strip()]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
