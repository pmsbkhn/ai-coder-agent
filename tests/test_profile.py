"""The MSFW profile loads and validates — the extensibility seam works."""

from __future__ import annotations

from pathlib import Path

from aicoder.application.profile import load_profile

PROFILE = Path(__file__).resolve().parents[1] / "profiles" / "msfw.yaml"


def test_msfw_profile_loads() -> None:
    p = load_profile(PROFILE)
    assert p.name == "msfw"
    assert p.language == "java"
    assert p.build.mcp_server == "maven-server"
    assert p.build.result_parser == "surefire-xml"
    assert p.architecture.fitness == "archunit"
    assert p.healing.max_attempts == 3
    assert "docs/SERVICE_ARCHITECTURE.md" in p.knowledge.seed_docs
