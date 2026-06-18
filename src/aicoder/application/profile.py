"""Project Profile — the seam that keeps the core stack-agnostic.

Everything MSFW/Maven-specific is data loaded from profiles/*.yaml, never code in
the core. A new target stack (e.g. a FastAPI service) is a new profile file, not
a code change. The YAML loader lives here in the application layer; the domain
never touches yaml (enforced by import-linter).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class BuildConfig(BaseModel):
    mcp_server: str
    test_command: str
    module_test_command: str | None = None
    single_test_command: str | None = None
    result_parser: str
    reports_glob: str | None = None


class ArchitectureConfig(BaseModel):
    fitness: str                              # e.g. "archunit" | "none"
    package_root: str = ""
    rules: list[str] = Field(default_factory=list)
    # When fitness == "archunit": a glob matched against failing test ids
    # ("{FQCN}.{method}") to tell ARCHITECTURE-rule failures apart from functional
    # ones, so the Verifier can report a dual verdict. Default catches ArchUnit
    # rule classes named *Architecture*Test.
    test_pattern: str = "*Architecture*"


class KnowledgeConfig(BaseModel):
    seed_docs: list[str] = Field(default_factory=list)
    golden_reference: str | None = None


class HealingConfig(BaseModel):
    max_attempts: int = 3
    reset_to_clean: bool = True
    no_progress_breaker: bool = True


class AnalysisConfig(BaseModel):
    # Analysis phase (ADR-08), runs BEFORE design. "off" = fast path, no analysis
    # (default); "always" = analyze every requirement; "auto" = analyze only
    # non-trivial requirements (plan-free complexity tiering, Slice 4 — see
    # application/tiering.py; skips clearly-trivial changes, logs ANALYSIS_SKIPPED).
    # When the Analyst flags a requirement as genuinely ambiguous, the run blocks on
    # the clarification gate (ApprovalPort kind="clarification") unless approved.
    mode: str = "off"


class DesignConfig(BaseModel):
    # Design-first phase (M07), runs BEFORE planning. "off" = fast path, no design
    # (default); "always" = design every requirement; "auto" = design only non-trivial
    # requirements (plan-free complexity tiering, ADR-08 Slice 4 — see
    # application/tiering.py; skips clearly-trivial changes, logs DESIGN_SKIPPED).
    mode: str = "off"
    # Slice 4: when true, a failed adversarial test review auto-blocks the run
    # (before the human gate). Default false = advisory (concerns surfaced to the human).
    review_strict: bool = False
    # Design-heal: how many times the orchestrator may hand the deterministic linter's
    # cross-document consistency + oracle/traceability findings back to the Designer to
    # auto-revise BEFORE the gate (0 = off). Keyed on the linter (objective), not the
    # advisory LLM review. Default 2: a multi-bounded-context design often surfaces several
    # findings at once (a misfiled case + an inverted arrow + a spec-only happy path), and
    # one revise pass rarely clears them all — the loop re-lints and stops early when clean.
    max_design_repairs: int = 2
    # Where the design artifacts (AD + one Tech Spec per bounded context) are written
    # in the target worktree, so they commit alongside the change.
    docs_dir: str = "docs/design"
    # Which design-artifact formats to emit. "markdown" (default) = the SAD-style AD +
    # Tech Specs + Test Cases. Add "structurizr" to ALSO emit Architecture-as-Code: a
    # master workspace.dsl (C4 model + views, ≈ the AD) + per-context .dsl fragments +
    # styles + embedded documentation/ADRs, from the same validated DesignSpec. Add
    # "structurizr-ci" (alongside "structurizr") to ALSO emit a pinned CI workflow
    # (.github/workflows/aac.yml) that validates + exports the DSL on every change.
    formats: list[str] = Field(default_factory=lambda: ["markdown"])


class DeployConfig(BaseModel):
    # Shell command run to deploy a verified change (M6). None = no deploy step.
    # Target-specific (helm/kubectl/a script); runs only after green + human approval.
    command: str | None = None


class TargetConfig(BaseModel):
    repo_path: str
    sandbox_module: str | None = None


class ProjectProfile(BaseModel):
    name: str
    language: str
    target: TargetConfig
    build: BuildConfig
    architecture: ArchitectureConfig
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)
    healing: HealingConfig = Field(default_factory=HealingConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    design: DesignConfig = Field(default_factory=DesignConfig)
    deploy: DeployConfig = Field(default_factory=DeployConfig)
    # Repo-relative globs the agent may READ (they enter the Coder's context) but
    # must NOT WRITE. Used by the eval harness to make pre-written tests an
    # immutable oracle: the agent implements code to pass them, can't edit them.
    # Empty (default) = no restriction, so non-eval profiles behave unchanged.
    protected_globs: list[str] = Field(default_factory=list)
    # Stack/framework DESIGN conventions — reusable domain primitives and house
    # rules the Analyst and Designer must PREFER over re-inventing (e.g. MSFW's
    # StringIdentity for ids, IdempotencyKey, domain.type.Money, the
    # InvalidArgumentException -> HTTP 400 mapping, the domain.saga package). Each
    # entry is one rule, injected verbatim into the Analyst/Designer system prompt so
    # the design reuses framework types instead of churning ad-hoc ones (an
    # IdGeneratorPort, a per-context DomainException). Empty (default) = generic
    # behavior, so framework-free profiles are unchanged. This is prompt-level
    # guidance only; deterministic enforcement stays in the ArchUnit/fitness gate.
    conventions: list[str] = Field(default_factory=list)
    # A concrete WORKED hexagonal exemplar for ONE bounded context (free text) —
    # the canonical port.in (use-case) / domain aggregate / port.out (repository,
    # with EVERY finder the tests call) / adapter layout the Designer should pattern
    # each context on. Injected into the Designer system prompt so per-domain designs
    # are complete and idiomatic (closes the L1/L8 "test calls an undeclared port
    # method" gap). Empty (default) = generic behavior, framework-free profiles
    # unchanged. Prompt-level guidance only.
    design_exemplar: str = ""


def load_profile(path: str | Path) -> ProjectProfile:
    """Parse a profile YAML into a validated ProjectProfile."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return ProjectProfile.model_validate(data)
