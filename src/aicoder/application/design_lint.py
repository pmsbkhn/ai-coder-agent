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

The L1–L4 family guards CODE-BUILD consistency (will it compile / link?). The L5–L7
family guards ORACLE & TRACEABILITY quality — a design can compile and still ship a
test oracle that does not actually pin the behavior, or a per-context test-case set
that does not trace to its context. These are the gaps an e2e run surfaced on a vague
multi-context requirement:

  L5  a test case is filed under the WRONG bounded context — its id (``TC-<CTX>-NN``)
      or its executable path's package belongs to a different context's Tech Spec than
      the one whose ``test_plan`` carries it. (This is what dumped every Catalog/
      Membership/Lending case into the Catalog doc and left the Lending doc empty,
      breaking the "1 BC = 1 Test-Case doc" traceability.)
  L6  oracle-coverage gaps: (6a) a ``domain`` case that SPECIFIES behavior but locks no
      executable oracle (empty ``path``/``content``) — the happy path / invariant is
      documented in prose but nothing holds the Coder to it; (6b) a bounded context with
      an EMPTY ``test_plan`` while sibling contexts carry cases — that context ships no
      acceptance oracle at all.
  L7  context-map arrow drawn against the real dependency: the map draws ``A --> B``
      (A depends on B) but the only cross-context reference runs the other way (B uses a
      type owned by A) — the architecture diagram contradicts the ownership decisions.
  L9  a shared kernel modeled as a peer bounded context — a Tech Spec named
      ``SharedKernel`` / ``Common`` / ``Kernel`` holding only shared value objects and the
      exception hierarchy. A shared kernel is a shared MODULE the contexts depend on, not a
      context of its own; this also tends to produce inverted context-map arrows (caught by
      L7's shared-kernel case, which fires even for a map-only node with no Tech Spec).
  L8  the locked test oracle invokes an operation (``bookRepo.findAllCopies()``,
      ``memberRepo.findAll()``) that NO interface / domain model / key-flow declares —
      the oracle out-runs the published API surface, so the Coder must invent an
      undeclared method to compile. To stay high-precision, L8 filters out non-domain
      calls: getters/setters, JUnit assertions, common JDK methods + BigDecimal
      arithmetic, STATIC calls on a Type (``UUID.randomUUID()``), and zero-arg
      value-object/record accessors (``copy.status()``) — while still keeping zero-arg
      repository finders (``repo.findAll()``).

The T-family (Slice B) guards REQUIREMENTS TRACEABILITY against the structured intake
(`RequirementSpec`), and only fires when one was supplied:

  T1  an acceptance criterion (``AC-*``) is not covered by any locked oracle test — no
      runnable test's ``traces_to`` references it, so the requirement is unenforced.
  T3  a locked test traces to NO known requirement id (orphan) — it pins behavior that no
      ``AC-*``/``NFR-*`` asked for, breaking the requirement↔test thread.
  T2  an NFR (``NFR-*``) is addressed by neither a test ``traces_to`` nor a design note —
      ADVISORY only (lives in ``lint_nfr_coverage``, never blocks/heals), since an NFR like
      "p95 < 300ms" usually cannot be pinned by a unit test.
  T4  event-flow consistency + traceability (``lint_event_flow``) — a Policy reacting to an
      undeclared event / triggering an undeclared command, or a CMD/EVT/POL with no
      ``traces_to``. ADVISORY only (Slice C), surfaced to the architect.
  T5  integration back-tracking signal (``lint_integration``, Slice D) — a saga too long or
      too many synchronous cross-context relationships, i.e. the Bước-3 boundaries are
      probably wrong. ADVISORY only.

T1/T3 are HARD: they join the L-family in ``lint_design``'s return value, so they block
under ``design.review_strict`` and drive design-heal. T2/T4/T5 are returned separately.

Pure function over the domain models — no infra, no I/O, fully deterministic. Findings
are advisory by default (surfaced to the architect gate); under ``design.review_strict``
a non-empty result blocks the run before the human gate, just like a failed review.
"""

from __future__ import annotations

import re

from aicoder.domain.models import DesignSpec, RequirementSpec, TechSpec

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
# A directed edge in a mermaid context map: `A -->|label| B`, `A --> B`, `A -.-> B`.
# Captures (source, target); the arrowhead points at the target.
_MAP_EDGE = re.compile(r"\b([A-Za-z_]\w*)\b\s*-[.-]*->\s*(?:\|[^|]*\|\s*)?\b([A-Za-z_]\w*)\b")
# `TC-CAT-01` -> context code `CAT`.
_TC_CODE = re.compile(r"\bTC-([A-Za-z]+)-\d+", re.IGNORECASE)
# A method INVOCATION in test source: `bookRepo.findAll(`, `UUID.randomUUID(` — captures
# (receiver, method, empty-parens?). The leading receiver lets L8 drop static calls on a
# Type (`UUID.randomUUID()`); the empty-parens group lets it drop zero-arg value-object
# accessors (`copy.status()`). A `new Type(` constructor has no leading `name.` so it never
# matches; a call chained on a result (`).foo(`) has no identifier receiver, also skipped.
_INVOKE = re.compile(r"([A-Za-z_]\w*)\.([a-z]\w*)\s*\(\s*(\))?")
# getters / setters / fluent accessors — never part of the published operation surface.
_GETTERISH = re.compile(r"^(?:get|set|is|has)[A-Z]")
# Verb prefixes that mark a genuine repository/port OPERATION even when zero-arg — so a
# bare `repo.findAll()` is still checked, while `member.status()` (a record accessor) is
# treated as a value read and skipped.
_FINDER_VERBS = ("find", "save", "load", "fetch", "list", "count", "delete", "remove",
                 "persist", "store", "query", "search", "lookup", "exists")
# JDK / JUnit / std-lib calls a test makes that are NOT the design's API — kept out of L8
# so the rule only flags genuinely-undeclared DOMAIN operations (false-positive guard).
_JDK_NOISE = frozenset({
    "get", "add", "remove", "contains", "size", "isEmpty", "isBlank", "stream",
    "filter", "collect", "map", "forEach", "toList", "of", "ofNullable", "orElse",
    "orElseThrow", "isPresent", "equals", "hashCode", "toString", "name", "ordinal",
    "values", "valueOf", "compareTo", "format", "fixed", "parse", "now", "plus",
    "plusDays", "plusHours", "plusMinutes", "minus", "minusDays", "trim", "length",
    "charAt", "substring", "split", "replace", "thenReturn", "when", "verify", "mock",
    "any", "eq", "atZone", "toInstant", "from", "until", "between",
    # BigDecimal / Money arithmetic and numeric conversions — not domain operations.
    "multiply", "divide", "subtract", "abs", "negate", "setScale", "scale", "pow",
    "signum", "round", "max", "min", "doubleValue", "intValue", "longValue",
})

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


def _api_surface(spec: DesignSpec) -> set[str]:
    """Every method name the design PUBLISHES anywhere — interface contracts, domain
    model, and key-flow sequences, across all contexts. The locked oracle (L8) may only
    invoke operations drawn from this surface; anything else is an API the Coder would
    have to invent because the design never declared it."""
    names: set[str] = set()
    for ts in spec.tech_specs:
        text = ("\n".join(ts.interface_changes) + "\n" + ts.domain_model
                + "\n" + ts.key_flows)
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


def _context_slugs(spec: DesignSpec) -> dict[str, str]:
    """lowercased bounded-context name -> the canonical name, one per Tech Spec."""
    return {ts.bounded_context.lower(): ts.bounded_context for ts in spec.tech_specs}


# Conventional names for a shared-kernel / common-types module — which is a shared MODULE
# every context depends on, NOT a peer bounded context.
_SHARED_KERNEL_NAMES = frozenset({
    "sharedkernel", "shared", "common", "commons", "kernel", "sharedmodule",
    "sharedtypes", "shareddomain",
})


def _is_shared_kernel(name: str) -> bool:
    return re.sub(r"[\s_-]+", "", name).lower() in _SHARED_KERNEL_NAMES


def _path_context(path: str, slugs: dict[str, str]) -> str | None:
    """The bounded context a test path lives in, by matching a package segment against a
    known context slug (`.../library/membership/MembershipServiceTest.java` -> the
    Membership context). None if no/ambiguous match."""
    segs = {s.lower() for s in path.replace("\\", "/").split("/")}
    hits = [name for slug, name in slugs.items() if slug in segs]
    return hits[0] if len(hits) == 1 else None


def _ref_dependencies(spec: DesignSpec, owners: dict[str, set[str]]) -> set[tuple[str, str]]:
    """`(referencer_ctx, owner_ctx)` pairs: a context references a domain type owned by a
    single OTHER context. This is the real cross-context dependency direction, used by L7
    to check the context-map arrows regardless of any shared-kernel decision."""
    deps: set[tuple[str, str]] = set()
    for ts in spec.tech_specs:
        for t in _referenced_types(ts):
            own = owners.get(t)
            if not own or len(own) != 1 or t.endswith(_SERVICE_SUFFIXES):
                continue
            owner = next(iter(own))
            if owner != ts.bounded_context:
                deps.add((ts.bounded_context, owner))
    return deps


def _locked_tests(spec: DesignSpec) -> list:
    """The executable, locked-oracle cases (path + content) — the only ones that
    actually pin behavior, so the only ones AC traceability (T1/T3) counts."""
    return [t for ts in spec.tech_specs for t in ts.test_plan if t.path and t.content]


def lint_design(spec: DesignSpec, req_spec: RequirementSpec | None = None) -> list[str]:
    """Return an ordered, de-duplicated list of cross-document consistency findings.
    Empty list == the design is internally consistent on these checks.

    When `req_spec` (the structured requirements intake, Slice B) is supplied, the
    traceability rules T1/T3 are ALSO enforced (HARD — they block under review_strict
    and drive the design-heal loop, exactly like L1-L9). NFR coverage (T2) is advisory
    and lives in `lint_nfr_coverage`, not here, so it never blocks. With no req_spec
    (the prose path) T1/T3 are skipped and behavior is unchanged."""
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

    slugs = _context_slugs(spec)

    # L5 — a test case is filed under the wrong context's Tech Spec.
    for ts in spec.tech_specs:
        for t in ts.test_plan:
            if t.kind == "fitness":  # fitness rules may legitimately span contexts
                continue
            home = _path_context(t.path, slugs) if t.path else None
            if home is None:  # fall back to the TC-<CTX>-NN code when there is no path
                m = _TC_CODE.search(t.id)
                code = m.group(1).lower() if m else ""
                for slug, name in slugs.items():
                    if code and slug.startswith(code):
                        home = name
                        break
            if home and home != ts.bounded_context:
                issues.append(
                    f"L5 test case `{t.id or t.title or t.path}` is filed under the "
                    f"`{ts.bounded_context}` Tech Spec but belongs to `{home}` (its "
                    f"id/path names that context) — move it to `{home}`'s test_plan so "
                    f"each context's Test-Case doc traces to its own context."
                )

    # L6a — a domain case specifies behavior but locks no executable oracle.
    for ts in spec.tech_specs:
        for t in ts.test_plan:
            if t.kind == "domain" and t.spec.strip() and not (t.path and t.content):
                issues.append(
                    f"L6 domain case `{t.id or t.title}` [{ts.bounded_context}] specifies "
                    f"behavior but locks no executable oracle (path+content) — happy paths "
                    f"and invariants must be locked as runnable tests, not left spec-only."
                )

    # L6b — a bounded context carries no test cases at all (multi-context designs).
    if len(spec.tech_specs) > 1:
        for ts in spec.tech_specs:
            if not ts.test_plan:
                issues.append(
                    f"L6 context `{ts.bounded_context}` has an empty test_plan — every "
                    f"bounded context must carry its own acceptance cases (1 BC = 1 "
                    f"Test-Case doc); add its domain cases or move the misfiled ones here."
                )

    # L7 — a context-map arrow drawn against the real dependency direction.
    ref_deps = _ref_dependencies(spec, owners)
    name_of = {slug: name for slug, name in slugs.items()}
    flagged_edges: set[tuple[str, str]] = set()
    for a_raw, b_raw in _MAP_EDGE.findall(spec.context_map):
        b = name_of.get(b_raw.lower())
        # the source may be a map-only node that is not a declared context (e.g. a
        # `Common` shared-kernel node), so fall back to its raw name.
        a = name_of.get(a_raw.lower(), a_raw)
        if not b or a == b or (a, b) in flagged_edges:
            continue
        # arrow a->b reads "a depends on b". Two unambiguous inversions:
        #  (1) `a` is a shared kernel — everyone depends ON it, never the reverse;
        #  (2) both are real contexts and the only cross-reference runs b->a (not a->b).
        if _is_shared_kernel(a_raw):
            flagged_edges.add((a, b))
            issues.append(
                f"L7 context-map draws `{a} --> {b}` but `{a}` is a shared kernel — "
                f"every context depends ON the shared kernel, not the reverse. Reverse "
                f"the arrow to `{b} --> {a}` (or drop the shared-kernel node)."
            )
        elif (a in name_of.values() and (b, a) in ref_deps
              and (a, b) not in ref_deps):
            flagged_edges.add((a, b))
            issues.append(
                f"L7 context-map draws `{a} --> {b}` (reads as `{a}` depends on `{b}`) "
                f"but the references run the other way — `{b}` uses a type owned by "
                f"`{a}`. Reverse the arrow to `{b} --> {a}` so the map matches ownership."
            )

    # L8 — a locked test invokes an operation the design never declares.
    api = _api_surface(spec)
    for ts in spec.tech_specs:
        for t in ts.test_plan:
            if not t.content:
                continue
            seen: set[str] = set()
            for recv, name, emptyparen in _INVOKE.findall(t.content):
                if (name in seen or name in api or name in _JDK_NOISE
                        or _GETTERISH.match(name)):
                    continue
                if recv[:1].isupper():  # static call on a Type, e.g. UUID.randomUUID(...)
                    continue
                if emptyparen and not name.startswith(_FINDER_VERBS):
                    continue  # zero-arg value-object / record accessor (copy.status())
                seen.add(name)
                issues.append(
                    f"L8 locked test `{t.id or t.path}` [{ts.bounded_context}] invokes "
                    f"`{name}(...)` but no interface / domain model / key-flow in the "
                    f"design declares it — declare `{name}` on the owning port or "
                    f"aggregate (or drop the call) so the oracle only exercises the "
                    f"published API surface."
                )

    # L9 — a shared kernel modeled as a peer bounded context.
    for ts in spec.tech_specs:
        if _is_shared_kernel(ts.bounded_context):
            issues.append(
                f"L9 `{ts.bounded_context}` is listed as a bounded context, but a shared "
                f"kernel is a shared MODULE the other contexts depend on (identifiers, "
                f"Money/Email value objects, the DomainException hierarchy) — not a peer "
                f"context. Don't give it its own Tech Spec / test_plan / BC row; home its "
                f"types in an owning context or a clearly-labeled shared-kernel module the "
                f"others reference (map arrows point TO it)."
            )

    # --- Traceability (Slice B) — only when a structured requirements intake exists.
    if req_spec is not None:
        known = set(req_spec.acceptance_ids) | set(req_spec.nfr_ids)
        locked = _locked_tests(spec)

        # T1 — every acceptance criterion must be pinned by a locked oracle test.
        covered: set[str] = set()
        for t in locked:
            covered |= set(t.traces_to)
        for ac in req_spec.acceptance_ids:
            if ac not in covered:
                issues.append(
                    f"T1 acceptance criterion `{ac}` is not covered by any locked test — "
                    f"every AC must be pinned by a runnable oracle. Add a test whose "
                    f"`traces_to` includes `{ac}` (or lock an existing spec-only case)."
                )

        # T3 — every locked test must trace to at least one known requirement id.
        for ts in spec.tech_specs:
            for t in ts.test_plan:
                if t.kind == "fitness" or not (t.path and t.content):
                    continue  # fitness rules / spec-only cases need not map to an AC
                if not (set(t.traces_to) & known):
                    issues.append(
                        f"T3 locked test `{t.id or t.path}` [{ts.bounded_context}] traces to "
                        f"no known requirement (traces_to={t.traces_to or '[]'}) — every "
                        f"locked test must reference at least one AC-/NFR- id from the "
                        f"requirements; set `traces_to` or drop the test."
                    )

    return issues


def lint_nfr_coverage(spec: DesignSpec, req_spec: RequirementSpec | None = None) -> list[str]:
    """T2 (ADVISORY) — each NFR should be addressed: referenced by a test's `traces_to`
    OR mentioned in the design text (system nfr / per-context NFR / decisions / invariants
    / ADRs). Advisory by design — it NEVER blocks and NEVER drives design-heal (an NFR like
    'p95 < 300ms' usually cannot be pinned by a unit test); it is surfaced to the architect.
    Returns [] when no req_spec was supplied."""
    if req_spec is None:
        return []
    referenced: set[str] = set()
    for ts in spec.tech_specs:
        for t in ts.test_plan:
            referenced |= set(t.traces_to)
    haystack = "\n".join([
        spec.summary, *spec.nfr, *spec.decisions, *spec.principles,
        *(x for ts in spec.tech_specs
          for x in (*ts.requirements_nonfunctional, *ts.invariants, *ts.adrs, ts.summary)),
    ])
    out: list[str] = []
    for nfr in req_spec.nfrs:
        if nfr.id in referenced or nfr.id in haystack:
            continue
        out.append(
            f"T2 NFR `{nfr.id}` [{nfr.category.value}] '{nfr.metric}' is not addressed by any "
            f"test (`traces_to`) or design note — add a decision/invariant/test that handles "
            f"it, or record it as out of scope."
        )
    return out


def lint_event_flow(spec: DesignSpec, req_spec: RequirementSpec | None = None) -> list[str]:
    """T4 (ADVISORY) — event-flow consistency + traceability (Slice C). Never blocks /
    heals; surfaced to the architect. Empty when no context models an event flow.

      T4a  a Policy reacts to an event id (`when_event`) that no DomainEvent declares.
      T4b  a Policy triggers a command id (`then_command`) that no Command declares.
      T4c  (only with a req_spec) a Command / Event / Policy carries no `traces_to` — the
           flow element does not derive from any stated requirement.
    """
    evt_ids = {e.id for ts in spec.tech_specs for e in ts.events if e.id}
    cmd_ids = {c.id for ts in spec.tech_specs for c in ts.commands if c.id}
    out: list[str] = []
    for ts in spec.tech_specs:
        for p in ts.policies:
            if p.when_event and p.when_event not in evt_ids:
                out.append(
                    f"T4 policy `{p.id}` [{ts.bounded_context}] reacts to `{p.when_event}` "
                    f"but no DomainEvent declares that id — declare the event or fix the ref."
                )
            if p.then_command and p.then_command not in cmd_ids:
                out.append(
                    f"T4 policy `{p.id}` [{ts.bounded_context}] triggers `{p.then_command}` "
                    f"but no Command declares that id — declare the command or fix the ref."
                )
        if req_spec is not None:
            for el in (*ts.commands, *ts.events, *ts.policies):
                if not el.traces_to:
                    out.append(
                        f"T4 event-flow element `{el.id}` [{ts.bounded_context}] has no "
                        f"`traces_to` — link it to the US/AC it derives from (or drop it)."
                    )
    return out


# A saga longer than this, or this many synchronous cross-context relationships, is the
# design-flow "Bước 5 → quay lui Bước 3" smell: the context boundaries are probably wrong.
_MAX_SAGA_STEPS = 5
_MAX_SYNC_RELATIONSHIPS = 3


def lint_integration(spec: DesignSpec, req_spec: RequirementSpec | None = None) -> list[str]:
    """T5 (ADVISORY) — the integration back-tracking signal (design-flow Bước 5). A saga
    that is too long, or too many synchronous cross-context calls, usually means the Bước-3
    boundaries are wrong (contexts too finely split). Never blocks/heals — it tells the
    architect to reconsider the Context Map. Empty when no integration is modeled."""
    out: list[str] = []
    for s in spec.sagas:
        if len(s.steps) > _MAX_SAGA_STEPS:
            out.append(
                f"T5 saga `{s.id}` has {len(s.steps)} steps (> {_MAX_SAGA_STEPS}) — a long "
                f"saga is a boundary smell; consider whether two contexts it spans should "
                f"merge (design-flow Bước 5 → quay lại Bước 3)."
            )
    # "sync" is a substring of "async" — exclude async mechanisms explicitly so an
    # event-driven relationship ("async (event)") is not miscounted as synchronous.
    sync = [r for r in spec.relationships
            if "sync" in (m := (r.mechanism or "").lower()) and "async" not in m]
    if len(sync) > _MAX_SYNC_RELATIONSHIPS:
        ids = ", ".join(r.id for r in sync)
        out.append(
            f"T5 the design has {len(sync)} synchronous cross-context relationships "
            f"({ids}) — high sync coupling suggests the Bước-3 boundaries may be wrong; "
            f"consider merging the tightly-coupled contexts."
        )
    return out


def _traces(items) -> str:
    """`→ AC-01, AC-02` for an element carrying `traces_to` (empty string when none)."""
    ids = ", ".join(getattr(items, "traces_to", []) or [])
    return f" → {ids}" if ids else ""


def render_contracts(spec: DesignSpec) -> str:
    """A compact, per-context digest of the binding contracts — fed to (a) the adversarial
    Reviewer so it judges the tests AGAINST the contracts, and (b) the Designer on a
    design-heal REVISE (designer_llm.revise_design), which otherwise sees only this digest,
    not the full previous DesignSpec. So the digest MUST name every droppable element —
    event flow, integration contracts, the test→requirement traces, and the system-level
    relationships/sagas — or a revise pass silently forgets them. Compact (ids + labels,
    no test bodies) to stay token-cheap."""
    blocks: list[str] = []

    # System-level structure (droppable on a revise that only sees the per-context digest).
    sys_lines: list[str] = []
    if spec.relationships:
        sys_lines.append("Context relationships:")
        sys_lines += [f"  - {r.id} {r.upstream}→{r.downstream} [{r.kind.value}; "
                      f"{r.mechanism}]" for r in spec.relationships]
    if spec.sagas:
        sys_lines.append("Sagas:")
        sys_lines += [f"  - {s.id} {s.name} ({s.kind}, {len(s.steps)} steps)" for s in spec.sagas]
    if spec.use_cases:
        sys_lines.append("Use cases: "
                         + "; ".join(f"{u.id} {u.name}{_traces(u)}" for u in spec.use_cases))
    if spec.glossary:
        sys_lines.append("Glossary: "
                         + "; ".join(f"{g.id} {g.term}@{g.bounded_context}" for g in spec.glossary))
    if sys_lines:
        blocks.append("## System\n" + "\n".join(sys_lines))

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
        # Event flow (template A5) — name each element so a revise keeps them.
        if ts.commands or ts.events or ts.policies or ts.read_models:
            lines.append("Event flow:")
            lines += [f"  - {c.id} {c.name} (cmd){_traces(c)}" for c in ts.commands]
            lines += [f"  - {e.id} {e.name} (evt){_traces(e)}" for e in ts.events]
            lines += [f"  - {p.id} ({p.when_event}→{p.then_command}) (policy){_traces(p)}"
                      for p in ts.policies]
            lines += [f"  - {r.id} {r.name} (read-model){_traces(r)}" for r in ts.read_models]
        # Integration contracts (template A8).
        if ts.apis or ts.event_schemas:
            lines.append("Integration:")
            lines += [f"  - {a.id} {a.method} {a.path}{_traces(a)}" for a in ts.apis]
            lines += [f"  - {e.id} {e.event_name} → {', '.join(e.consumers)}{_traces(e)}"
                      for e in ts.event_schemas]
        # Tests + their requirement traces (NOT the bodies) — so a revise does not drop
        # coverage or re-derive traces_to from scratch.
        if ts.test_plan:
            lines.append("Tests (id [title] → traces):")
            lines += [f"  - {t.id} [{t.title}]{_traces(t)}"
                      + ("" if (t.path and t.content) else " (spec-only)")
                      for t in ts.test_plan]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
