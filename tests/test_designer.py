"""Design-first phase, Slice 1 (M07): the Designer produces a DesignSpec +
executable TestPlan, schema-validated; the orchestrator logs DESIGN_PROPOSED when
enabled and skips it (current fast path) by default. No gate / no test-locking yet."""

from __future__ import annotations

from pathlib import Path

from aicoder.adapters.designer_llm import LLMDesigner
from aicoder.adapters.memory_inmemory import InMemoryMemory
from aicoder.application.orchestrator import Orchestrator
from aicoder.application.profile import load_profile
from aicoder.domain.models import DesignSpec, Plan, SessionState, Task, VerificationResult

from tests.test_orchestrator_loop import FakeBuild, FakeCoder, FakeGateway, FakePlanner

_PROFILE = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "msfw.yaml")

_VALID_DESIGN = {
    "summary": "Add a nullable note to Order and thread it to OrderPlaced.",
    "decisions": ["Keep the 2-arg placeOrder working via an overload."],
    "tech_specs": [
        {
            "bounded_context": "Orders",
            "summary": "Order carries an optional note that reaches OrderPlaced.",
            "affected": ["Order.java", "OrderPlaced.java"],
            "interface_changes": ["OrderService.placeOrder(customer, amount, note)"],
            "adr_notes": "Overload, not a breaking signature change.",
            "test_plan": [
                {"path": "src/test/java/com/example/OrderNoteTest.java",
                 "content": "class OrderNoteTest {}", "rationale": "note flows to the event"},
            ],
        },
    ],
}


class FakeLLM:
    model = "fake"

    def __init__(self, payloads: list[dict]) -> None:
        self._payloads = list(payloads)

    def complete_json(self, *, system, user, json_schema, tool_name="emit") -> dict:
        return self._payloads.pop(0)

    def complete_text(self, *, system, user, max_tokens=2048) -> str:  # pragma: no cover
        return ""


def _passed() -> VerificationResult:
    return VerificationResult(passed=True, functional_passed=True, arch_passed=True)


class FakeDesigner:
    def __init__(self, design: dict | None = None, revised: dict | None = None) -> None:
        self.calls = 0
        self.revise_calls = 0
        self._design = design or _VALID_DESIGN
        self._revised = revised  # design returned by revise_design; None = unchanged
        self.seen_analysis = None  # the AnalysisSpec handed in (ADR-08 Slice 3), if any

    def propose_design(self, requirement: str, repo_map: str, analysis=None, spec=None) -> DesignSpec:
        self.calls += 1
        self.seen_analysis = analysis
        self.seen_spec = spec
        return DesignSpec.model_validate(self._design)

    def revise_design(self, requirement, repo_map, previous, issues, analysis=None, spec=None) -> DesignSpec:
        self.revise_calls += 1
        self.seen_analysis = analysis
        self.seen_spec = spec
        return DesignSpec.model_validate(self._revised if self._revised is not None else self._design)


class _RecordingGateway(FakeGateway):
    """Captures the paths written, to assert the AD + Tech Spec files appear."""
    def __init__(self) -> None:
        super().__init__()
        self.writes: list[str] = []

    def execute_tool_call(self, request):
        if request.server == "git" and request.method == "write_file":
            self.writes.append(request.params.get("path"))
        return super().execute_tool_call(request)


def test_llm_designer_returns_valid_spec() -> None:
    designer = LLMDesigner(FakeLLM([_VALID_DESIGN]), _PROFILE)
    spec = designer.propose_design("add a note field", "# Repo Map\nclass Order")
    assert isinstance(spec, DesignSpec)
    assert spec.bounded_contexts == ["Orders"]                     # 1 BC = 1 tech spec
    ts = spec.tech_specs[0]
    assert ts.test_plan[0].path.endswith("OrderNoteTest.java")
    assert "OrderService" in ts.interface_changes[0]
    assert spec.all_tests()[0].path.endswith("OrderNoteTest.java")


def _orch(design_mode, designer, mem):
    plan = Plan(tasks=[Task(id="t1", description="x", target_files=["A.java"])])
    return Orchestrator(
        profile=_PROFILE, planner=FakePlanner(plan), coder=FakeCoder(),
        memory=mem, gateway=FakeGateway(), build=FakeBuild([_passed()]),
        designer=designer, design_mode=design_mode,
    )


def test_design_logged_when_enabled() -> None:
    mem, designer = InMemoryMemory(), FakeDesigner()
    session = _orch("always", designer, mem).run_requirement("x")
    assert session.state is SessionState.DONE
    assert designer.calls == 1
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert "DESIGN_PROPOSED" in events
    payload = next(t.payload for t in mem.get_traces(session.session_id)
                   if t.event_type == "DESIGN_PROPOSED")
    assert payload["proposed_tests"] == ["src/test/java/com/example/OrderNoteTest.java"]


def test_design_skipped_by_default() -> None:
    mem, designer = InMemoryMemory(), FakeDesigner()
    session = _orch("off", designer, mem).run_requirement("x")  # default fast path
    assert session.state is SessionState.DONE
    assert designer.calls == 0
    assert "DESIGN_PROPOSED" not in [t.event_type for t in mem.get_traces(session.session_id)]


# --- Slice 2: human gate + lock the approved tests as the oracle ----------------

class _Approval:
    def __init__(self, ok: bool) -> None:
        self.ok = ok

    def request_approval(self, kind: str, summary: str) -> bool:
        return self.ok


class _TamperingCoder(FakeCoder):
    """Tries to overwrite the design-locked test — must be refused."""
    def apply_task(self, task, files, error_context: str = ""):
        from aicoder.domain.models import CodeChange, FileEdit
        return CodeChange(edits=[
            FileEdit(path="A.java", content="class A {}"),
            FileEdit(path="src/test/java/com/example/OrderNoteTest.java", content="// tamper"),
        ])


def _gated_orch(approval, mem, coder=None):
    plan = Plan(tasks=[Task(id="t1", description="x", target_files=["A.java"])])
    return Orchestrator(
        profile=_PROFILE, planner=FakePlanner(plan), coder=coder or FakeCoder(),
        memory=mem, gateway=FakeGateway(), build=FakeBuild([_passed()]),
        designer=FakeDesigner(), design_mode="always", approval=approval,
    )


def test_approved_design_locks_proposed_tests() -> None:
    mem = InMemoryMemory()
    session = _gated_orch(_Approval(True), mem, coder=_TamperingCoder()).run_requirement("x")
    assert session.state is SessionState.DONE
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert events.count("DESIGN_PROPOSED") == 1
    assert "APPROVAL_REQUESTED" in events and "DESIGN_APPROVED" in events
    # the Coder tried to overwrite the locked test and was refused
    assert "WRITE_BLOCKED" in events


def test_rejected_design_blocks_before_coding() -> None:
    mem = InMemoryMemory()
    coder = FakeCoder()
    session = _gated_orch(_Approval(False), mem, coder=coder).run_requirement("x")
    assert session.state is SessionState.BLOCKED
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert "DESIGN_REJECTED" in events
    assert "DIFF_APPLIED" not in events     # never reached coding
    assert coder.contexts == []             # Coder never called


# --- Slice 4: tiering — auto designs complex changes, skips trivial ones --------
# Tiering is now plan-free (analysis/design run before the plan): it keys on the
# REQUIREMENT text (scope + vagueness), not on task/file count. See test_tiering.py.

_TRIVIAL_REQ = "Rename the field amount to total on Order."
_COMPLEX_REQ = "Let customers manage their orders after placing them."   # "manage" → complex


def _orch_auto(design_mode, designer, mem):
    plan = Plan(tasks=[Task(id="t1", description="x", target_files=["A.java"])])
    return Orchestrator(
        profile=_PROFILE, planner=FakePlanner(plan), coder=FakeCoder(),
        memory=mem, gateway=FakeGateway(), build=FakeBuild([_passed()]),
        designer=designer, design_mode=design_mode,
    )


def test_auto_skips_trivial_requirement() -> None:
    mem, designer = InMemoryMemory(), FakeDesigner()
    session = _orch_auto("auto", designer, mem).run_requirement(_TRIVIAL_REQ)
    assert session.state is SessionState.DONE
    assert designer.calls == 0
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert "DESIGN_SKIPPED" in events and "DESIGN_PROPOSED" not in events


def test_auto_designs_complex_requirement() -> None:
    mem, designer = InMemoryMemory(), FakeDesigner()
    session = _orch_auto("auto", designer, mem).run_requirement(_COMPLEX_REQ)
    assert session.state is SessionState.DONE
    assert designer.calls == 1
    assert "DESIGN_PROPOSED" in [t.event_type for t in mem.get_traces(session.session_id)]


def test_always_designs_even_trivial() -> None:
    mem, designer = InMemoryMemory(), FakeDesigner()
    _orch_auto("always", designer, mem).run_requirement(_TRIVIAL_REQ)
    assert designer.calls == 1   # 'always' ignores tiering and designs every requirement


def test_design_runs_before_an_empty_plan_blocks() -> None:
    # Regression for the reorder: design runs BEFORE planning, so a flaky/empty plan
    # can no longer suppress the design. The run still BLOCKS on the empty plan, but
    # only AFTER the design was proposed (and, here, approved).
    mem = InMemoryMemory()
    orch = Orchestrator(
        profile=_PROFILE, planner=FakePlanner(Plan(tasks=[])), coder=FakeCoder(),
        memory=mem, gateway=FakeGateway(), build=FakeBuild([_passed()]),
        designer=FakeDesigner(), design_mode="always",
    )
    session = orch.run_requirement("x")
    assert session.state is SessionState.BLOCKED
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert "DESIGN_PROPOSED" in events       # design happened first...
    assert events.index("DESIGN_PROPOSED") < events.index("EMPTY_PLAN")  # ...before the empty-plan block


# --- ADR-07 Slice 4: adversarial test review before locking ---------------------

# aliased so pytest doesn't try to collect the "Test"-prefixed domain model as a test
from aicoder.domain.models import TestReview as _ReviewModel  # noqa: E402


class _Reviewer:
    def __init__(self, ok: bool, concerns=None) -> None:
        self.ok = ok
        self.concerns = concerns or []
        self.calls = 0

    def review_tests(self, requirement, design_summary, tests, contracts="") -> _ReviewModel:
        self.calls += 1
        self.seen_contracts = contracts          # (1) Reviewer now receives the contracts
        return _ReviewModel(ok=self.ok, concerns=self.concerns)


def _reviewed_orch(approval, reviewer, mem, profile=_PROFILE):
    plan = Plan(tasks=[Task(id="t1", description="x", target_files=["A.java"])])
    return Orchestrator(
        profile=profile, planner=FakePlanner(plan), coder=FakeCoder(),
        memory=mem, gateway=FakeGateway(), build=FakeBuild([_passed()]),
        designer=FakeDesigner(), design_mode="always", approval=approval, reviewer=reviewer,
    )


def _strict_profile():
    return _PROFILE.model_copy(
        update={"design": _PROFILE.design.model_copy(update={"review_strict": True})})


def test_review_ok_proceeds_to_gate() -> None:
    mem, rev = InMemoryMemory(), _Reviewer(True)
    session = _reviewed_orch(_Approval(True), rev, mem).run_requirement("x")
    assert session.state is SessionState.DONE and rev.calls == 1
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert "TEST_REVIEW" in events and "DESIGN_APPROVED" in events


def test_review_strict_auto_blocks_weak_tests() -> None:
    mem, rev = InMemoryMemory(), _Reviewer(False, ["assertTrue(true) — trivially satisfiable"])
    session = _reviewed_orch(_Approval(True), rev, mem, profile=_strict_profile()).run_requirement("x")
    assert session.state is SessionState.BLOCKED
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert "TEST_REVIEW" in events and "DESIGN_REJECTED" in events
    assert "APPROVAL_REQUESTED" not in events   # blocked before the human gate
    assert "DIFF_APPLIED" not in events


def test_review_advisory_surfaces_concerns_then_human_approves() -> None:
    mem, rev = InMemoryMemory(), _Reviewer(False, ["missing the insufficient-funds case"])
    session = _reviewed_orch(_Approval(True), rev, mem).run_requirement("x")  # review_strict False
    assert session.state is SessionState.DONE
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert "TEST_REVIEW" in events and "DESIGN_APPROVED" in events
    payload = next(t.payload for t in mem.get_traces(session.session_id)
                   if t.event_type == "APPROVAL_REQUESTED")
    assert payload["review_concerns"] == ["missing the insufficient-funds case"]


# --- Deterministic design linter wired into the gate ---------------------------

# A two-context design with the e2e run's flaws (undeclared call + cross-context type).
_INCONSISTENT_DESIGN = {
    "summary": "Lending coordinates Catalog copies.",
    "decisions": [],
    "tech_specs": [
        {"bounded_context": "Catalog", "summary": "copies",
         "affected": ["src/main/java/lib/catalog/Copy.java",
                      "src/main/java/lib/catalog/CatalogService.java"],
         "interface_changes": ["interface CatalogService { Optional<Copy> findCopy(UUID id); }"],
         "test_plan": [{"path": "src/test/java/CatT.java", "content": "//", "rationale": "x"}]},
        {"bounded_context": "Lending", "summary": "loans",
         "affected": ["src/main/java/lib/lending/Loan.java"],
         "interface_changes": ["interface LendingService { Loan createLoan(UUID copyId); }"],
         "key_flows": "sequenceDiagram\n  LoanAggregate->>CatalogService: setCopyStatus(ON_LOAN)\n"
                      "  CatalogService-->>LendingService: Copy(AVAILABLE)",
         "test_plan": [{"path": "src/test/java/LenT.java", "content": "//", "rationale": "y"}]},
    ],
}


def test_design_lint_logged_and_surfaced_to_architect() -> None:
    mem = InMemoryMemory()
    plan = Plan(tasks=[Task(id="t1", description="x", target_files=["A.java"])])
    orch = Orchestrator(
        profile=_PROFILE, planner=FakePlanner(plan), coder=FakeCoder(),
        memory=mem, gateway=FakeGateway(), build=FakeBuild([_passed()]),
        designer=FakeDesigner(_INCONSISTENT_DESIGN), design_mode="always",
        approval=_Approval(True),  # non-strict → advisory: lint surfaced, run proceeds
    )
    session = orch.run_requirement("x")
    assert session.state is SessionState.DONE
    traces = mem.get_traces(session.session_id)
    lint = next(t.payload for t in traces if t.event_type == "DESIGN_LINT")
    assert lint["ok"] is False and lint["issues"]
    appr = next(t.payload for t in traces if t.event_type == "APPROVAL_REQUESTED")
    assert appr["lint_issues"]                          # carried to the human gate
    assert any("setCopyStatus" in i for i in appr["lint_issues"])  # L1 caught


def test_lint_strict_blocks_inconsistent_design_without_a_reviewer() -> None:
    mem = InMemoryMemory()
    plan = Plan(tasks=[Task(id="t1", description="x", target_files=["A.java"])])
    orch = Orchestrator(
        profile=_strict_profile(), planner=FakePlanner(plan), coder=FakeCoder(),
        memory=mem, gateway=FakeGateway(), build=FakeBuild([_passed()]),
        designer=FakeDesigner(_INCONSISTENT_DESIGN), design_mode="always",
        approval=_Approval(True), reviewer=None,        # lint alone drives the block
    )
    session = orch.run_requirement("x")
    assert session.state is SessionState.BLOCKED
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert "DESIGN_LINT" in events and "DESIGN_REJECTED" in events
    assert "APPROVAL_REQUESTED" not in events           # blocked before the human gate
    assert "DIFF_APPLIED" not in events
    rej = next(t.payload for t in mem.get_traces(session.session_id)
               if t.event_type == "DESIGN_REJECTED")
    assert rej["lint_issues"]


def test_reviewer_receives_contracts() -> None:
    mem, rev = InMemoryMemory(), _Reviewer(True)
    _reviewed_orch(_Approval(True), rev, mem).run_requirement("x")
    assert "OrderService" in rev.seen_contracts        # interfaces digest reached the reviewer


# --- Design-heal: auto-revise on deterministic lint findings (bounded) ----------

# A corrected version of _INCONSISTENT_DESIGN: setCopyStatus is declared, Copy has a
# single owner referenced via a shared-kernel decision, no arity clash, no naming drift.
_REPAIRED_DESIGN = {
    "summary": "Lending coordinates Catalog copies.",
    "decisions": ["Catalog owns Copy; Lending references it via the Catalog "
                  "published language (shared kernel), not its own copy."],
    "tech_specs": [
        {"bounded_context": "Catalog", "summary": "copies",
         "affected": ["src/main/java/lib/catalog/Copy.java",
                      "src/main/java/lib/catalog/CatalogService.java"],
         "interface_changes": ["interface CatalogService { Optional<Copy> findCopy(UUID id); "
                               "void setCopyStatus(UUID id, CopyStatus s); }"],
         "test_plan": [{"path": "src/test/java/CatT.java", "content": "//", "rationale": "x"}]},
        {"bounded_context": "Lending", "summary": "loans",
         "affected": ["src/main/java/lib/lending/Loan.java"],
         "interface_changes": ["interface LendingService { Loan createLoan(UUID copyId); }"],
         "key_flows": "sequenceDiagram\n  LoanAggregate->>CatalogService: setCopyStatus(id, ON_LOAN)",
         "test_plan": [{"path": "src/test/java/LenT.java", "content": "//", "rationale": "y"}]},
    ],
}


def _heal_orch(designer, profile, mem):
    plan = Plan(tasks=[Task(id="t1", description="x", target_files=["A.java"])])
    return Orchestrator(
        profile=profile, planner=FakePlanner(plan), coder=FakeCoder(),
        memory=mem, gateway=FakeGateway(), build=FakeBuild([_passed()]),
        designer=designer, design_mode="always", approval=_Approval(True), reviewer=None,
    )


def test_design_heal_converges_before_the_gate() -> None:
    mem = InMemoryMemory()
    designer = FakeDesigner(_INCONSISTENT_DESIGN, revised=_REPAIRED_DESIGN)
    # strict profile would BLOCK an inconsistent design — so reaching DONE proves the
    # repair pass cleaned it up before the gate.
    session = _heal_orch(designer, _strict_profile(), mem).run_requirement("x")
    assert session.state is SessionState.DONE
    assert designer.revise_calls == 1
    traces = mem.get_traces(session.session_id)
    events = [t.event_type for t in traces]
    assert "DESIGN_REVISED" in events and "DESIGN_REJECTED" not in events
    lint = next(t.payload for t in traces if t.event_type == "DESIGN_LINT")
    assert lint["ok"] is True and lint["repairs"] == 1


def test_design_heal_is_bounded_then_blocks_when_unfixed() -> None:
    mem = InMemoryMemory()
    designer = FakeDesigner(_INCONSISTENT_DESIGN)  # revise returns the same → never converges
    session = _heal_orch(designer, _strict_profile(), mem).run_requirement("x")
    assert session.state is SessionState.BLOCKED
    assert designer.revise_calls == 2              # capped by max_design_repairs (default 2)
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert events.count("DESIGN_REVISED") == 2 and "DESIGN_REJECTED" in events


def test_design_repairs_can_be_disabled() -> None:
    mem = InMemoryMemory()
    prof = _PROFILE.model_copy(
        update={"design": _PROFILE.design.model_copy(update={"max_design_repairs": 0})})
    designer = FakeDesigner(_INCONSISTENT_DESIGN, revised=_REPAIRED_DESIGN)
    session = _heal_orch(designer, prof, mem).run_requirement("x")  # non-strict default
    assert session.state is SessionState.DONE      # advisory: surfaced, not blocked
    assert designer.revise_calls == 0
    traces = mem.get_traces(session.session_id)
    assert "DESIGN_REVISED" not in [t.event_type for t in traces]
    lint = next(t.payload for t in traces if t.event_type == "DESIGN_LINT")
    assert lint["ok"] is False and lint["repairs"] == 0


# --- Explicit AD + Tech Spec files (1 bounded context = 1 tech spec) ------------

from aicoder.application.design_docs import (  # noqa: E402
    render_ad,
    render_tech_spec,
    render_test_cases,
)

_TWO_BC = {
    "summary": "Touch two contexts.",
    "decisions": ["Keep the contexts decoupled — integrate via events only."],
    "tech_specs": [
        {"bounded_context": "Orders", "summary": "order side",
         "affected": ["Order.java"], "interface_changes": [], "adr_notes": "",
         "test_plan": [{"path": "src/test/java/OrdersT.java", "content": "//", "rationale": "x"}]},
        {"bounded_context": "Payment", "summary": "payment side",
         "affected": ["Escrow.java"], "interface_changes": [], "adr_notes": "",
         "test_plan": [{"path": "src/test/java/PaymentT.java", "content": "//", "rationale": "y"}]},
    ],
}


def test_design_writes_ad_and_tech_spec_files() -> None:
    mem = InMemoryMemory()
    plan = Plan(tasks=[Task(id="t1", description="x", target_files=["A.java"])])
    gw = _RecordingGateway()
    orch = Orchestrator(
        profile=_PROFILE, planner=FakePlanner(plan), coder=FakeCoder(),
        memory=mem, gateway=gw, build=FakeBuild([_passed()]),
        designer=FakeDesigner(), design_mode="always", approval=_Approval(True),
    )
    session = orch.run_requirement("x")
    assert session.state is SessionState.DONE
    assert "docs/design/AD.md" in gw.writes
    assert "docs/design/techspec-orders.md" in gw.writes
    docs = next(t.payload["docs"] for t in mem.get_traces(session.session_id)
                if t.event_type == "DESIGN_PROPOSED")
    assert "docs/design/AD.md" in docs and "docs/design/techspec-orders.md" in docs


def test_one_tech_spec_file_per_bounded_context() -> None:
    mem = InMemoryMemory()
    plan = Plan(tasks=[Task(id="t1", description="x", target_files=["A.java"])])
    gw = _RecordingGateway()
    orch = Orchestrator(
        profile=_PROFILE, planner=FakePlanner(plan), coder=FakeCoder(),
        memory=mem, gateway=gw, build=FakeBuild([_passed()]),
        designer=FakeDesigner(_TWO_BC), design_mode="always", approval=_Approval(True),
    )
    orch.run_requirement("x")
    specs = [w for w in gw.writes if "techspec-" in w]
    assert specs == ["docs/design/techspec-orders.md", "docs/design/techspec-payment.md"]


def test_renderers_produce_ad_and_tech_spec_markdown() -> None:
    spec = DesignSpec.model_validate(_VALID_DESIGN)
    ad = render_ad(spec, "add a note", "docs/design")
    assert "# Architecture Description" in ad and "Orders" in ad and "techspec-orders.md" in ad
    ts = render_tech_spec(spec.tech_specs[0])
    assert "# Tech Spec — Orders" in ts and "OrderNoteTest.java" in ts


# --- House style: SAD-style AD, core Tech Spec, TC-XXX-NN Test Cases ------------

_RICH_DESIGN = {
    "summary": "Add escrow capture to Payment.",
    "goals": ["Protect buyer funds via escrow"],
    "architecture_style": "Hexagonal per context; choreography via PaymentReceived.",
    "principles": ["Idempotency for every money operation", "Tenant isolation"],
    "context_map": "```mermaid\ngraph TD\n  PAY-->ORD\n```",
    "decisions": ["One escrow per cart total."],
    "nfr": ["Payment availability >= 99.95%"],
    "tech_specs": [{
        "bounded_context": "Payment",
        "summary": "Escrow capture + settlement.",
        "classification": "Tier 1 — Mission Critical · L3",
        "requirements_functional": ["FR1 init escrow", "FR2 confirm payment"],
        "requirements_nonfunctional": ["confirm P99 < 100ms"],
        "module_view": "```mermaid\nflowchart TB\n  ctrl-->usecase-->domain\n```",
        "cnc_view": "Payment API -> PostgreSQL (TLS · IAM)",
        "affected": ["Payment.java", "EscrowHold.java"],
        "interface_changes": ["interface PaymentPort { EscrowHold initEscrow(Money m) }"],
        "domain_model": "```mermaid\nclassDiagram\n  class Payment\n```",
        "invariants": [
            "confirmPayment webhookAmount must equal escrow amount or DomainException(AMOUNT_MISMATCH)",
            "PAID is terminal — markFailed() after PAID throws InvalidTransitionException",
        ],
        "erd": "```mermaid\nerDiagram\n  PAYMENT ||--o{ ESCROW_HOLD : has\n```",
        "key_flows": "```mermaid\nsequenceDiagram\n  CHK->>PAY: InitEscrow\n```",
        "adrs": ["One escrow per cart → buyer pays once → settlement splits later."],
        "open_questions": ["Partial refund out of scope?"],
        "test_plan": [
            {"id": "TC-PAY-01", "title": "Amount Cross-Check / Tampering", "kind": "domain",
             "spec": "Init Payment amount=1500000; confirmPayment(txn, webhookAmount=1000000) "
                     "-> DomainException(AMOUNT_MISMATCH), state stays PENDING.",
             "path": "src/test/java/com/example/payment/PaymentAmountTest.java",
             "content": "class PaymentAmountTest {}", "rationale": "tampering guard"},
            {"id": "TC-PAY-FIT-01", "title": "Domain purity", "kind": "fitness",
             "spec": "domain package must not import application/adapter or Spring.",
             "rationale": "ArchUnit rule"},
        ],
    }],
}


def test_ad_has_sad_style_sections() -> None:
    ad = render_ad(DesignSpec.model_validate(_RICH_DESIGN), "escrow", "docs/design")
    for section in ("## Goals", "## Architecture style", "## Design principles",
                    "## Bounded-context map", "## Cross-cutting decisions"):
        assert section in ad
    assert "graph TD" in ad                                   # context map mermaid embedded
    # the BC row links to BOTH the tech spec and the test-cases doc
    assert "techspec-payment.md" in ad and "testcases-payment.md" in ad


def test_tech_spec_has_core_sections_and_invariants() -> None:
    ts = render_tech_spec(DesignSpec.model_validate(_RICH_DESIGN).tech_specs[0])
    for section in ("1. Context & Scope", "Requirements — Functional", "Module view",
                    "Invariants", "Data model", "Decisions", "Open questions"):
        assert section in ts
    assert "Tier 1 — Mission Critical" in ts                  # classification line
    assert "AMOUNT_MISMATCH" in ts                            # invariant text rendered
    assert "classDiagram" in ts and "erDiagram" in ts         # mermaid embedded


def test_test_cases_doc_groups_by_kind() -> None:
    tc = render_test_cases(DesignSpec.model_validate(_RICH_DESIGN).tech_specs[0])
    assert "# Test Cases — Payment" in tc
    assert "TC-PAY-01" in tc and "[Amount Cross-Check / Tampering]" in tc
    assert "Domain invariant cases" in tc and "Fitness functions" in tc
    assert "TC-PAY-FIT-01" in tc                              # spec-only fitness case listed
    assert "PaymentAmountTest.java" in tc                     # domain case links its oracle


def test_design_writes_testcases_doc_and_locks_only_executable() -> None:
    mem = InMemoryMemory()
    plan = Plan(tasks=[Task(id="t1", description="x", target_files=["A.java"])])
    gw = _RecordingGateway()
    orch = Orchestrator(
        profile=_PROFILE, planner=FakePlanner(plan), coder=FakeCoder(),
        memory=mem, gateway=gw, build=FakeBuild([_passed()]),
        designer=FakeDesigner(_RICH_DESIGN), design_mode="always", approval=_Approval(True),
    )
    session = orch.run_requirement("x")
    assert session.state is SessionState.DONE
    # AD + Tech Spec + Test Cases doc all written
    for doc in ("docs/design/AD.md", "docs/design/techspec-payment.md",
                "docs/design/testcases-payment.md"):
        assert doc in gw.writes
    # only the executable (domain) case is locked; the spec-only fitness case is not
    locked = next(t.payload["locked_tests"] for t in mem.get_traces(session.session_id)
                  if t.event_type == "DESIGN_APPROVED")
    assert locked == ["src/test/java/com/example/payment/PaymentAmountTest.java"]


# --- Framework conventions injected from the Profile (MSFW primitives) ---------- #

class _RecordingLLM:
    """Captures the system prompt so we can assert profile conventions reach it."""
    model = "fake"

    def __init__(self) -> None:
        self.system = ""

    def complete_json(self, *, system, user, json_schema, tool_name="emit") -> dict:
        self.system = system
        return _VALID_DESIGN

    def complete_text(self, *, system, user, max_tokens=2048) -> str:  # pragma: no cover
        return ""


def test_designer_injects_profile_conventions_into_system_prompt() -> None:
    # the msfw profile now carries `conventions` (StringIdentity, IdempotencyKey, …)
    assert _PROFILE.conventions, "msfw profile should define conventions"
    llm = _RecordingLLM()
    LLMDesigner(llm, _PROFILE).propose_design("add a note", "repo-map")
    assert "Framework conventions" in llm.system
    assert "StringIdentity" in llm.system  # a concrete primitive reached the prompt


def test_designer_no_conventions_section_when_profile_lists_none() -> None:
    prof = _PROFILE.model_copy(update={"conventions": [], "design_exemplar": ""})
    llm = _RecordingLLM()
    LLMDesigner(llm, prof).propose_design("add a note", "repo-map")
    assert "Framework conventions" not in llm.system  # framework-free profiles unchanged
    assert "Reference hexagonal layout" not in llm.system


def test_designer_injects_hexagonal_exemplar() -> None:
    assert _PROFILE.design_exemplar, "msfw profile should define a hexagonal exemplar"
    llm = _RecordingLLM()
    LLMDesigner(llm, _PROFILE).propose_design("add a note", "repo-map")
    assert "Reference hexagonal layout" in llm.system
    assert "findAllCopies" in llm.system  # the worked port contract reached the prompt


def test_designer_prompt_carries_completeness_rule() -> None:
    # the closure/enumerate-ports rule is static (framework-agnostic) — always present
    llm = _RecordingLLM()
    LLMDesigner(llm, _PROFILE.model_copy(update={"conventions": [], "design_exemplar": ""})
                ).propose_design("x", "repo-map")
    assert "CLOSURE RULE" in llm.system and "ENUMERATE EVERY PORT" in llm.system
