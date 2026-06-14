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
    deploy: DeployConfig = Field(default_factory=DeployConfig)
    # Repo-relative globs the agent may READ (they enter the Coder's context) but
    # must NOT WRITE. Used by the eval harness to make pre-written tests an
    # immutable oracle: the agent implements code to pass them, can't edit them.
    # Empty (default) = no restriction, so non-eval profiles behave unchanged.
    protected_globs: list[str] = Field(default_factory=list)


def load_profile(path: str | Path) -> ProjectProfile:
    """Parse a profile YAML into a validated ProjectProfile."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return ProjectProfile.model_validate(data)
