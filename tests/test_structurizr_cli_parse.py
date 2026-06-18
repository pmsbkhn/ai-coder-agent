"""The only test that proves the generated DSL parses against the REAL Structurizr CLI.

Docker-gated: skipped unless the pinned image is present (or AAC_CLI=1 forces it). Everything
else about the generator is covered by pure-Python tests; this guards against the class of bug
the pure-Python validator cannot see (anything the CLI's own parser rejects). It deliberately
pins a dated tag — `structurizr/cli:latest` is a deprecation no-op stub that exits 0 without
running the CLI, so it would make this test pass while validating nothing."""

from __future__ import annotations

import os
import subprocess

import pytest

from aicoder.application.design_structurizr import render_structurizr
from tests.test_design_structurizr import _RICH

_TAG = "structurizr/cli:2025.11.09"


def _cli_available() -> bool:
    if os.environ.get("AAC_CLI") == "1":
        return True
    try:
        r = subprocess.run(["docker", "image", "inspect", _TAG],
                           capture_output=True, timeout=30)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


pytestmark = pytest.mark.skipif(
    not _cli_available(),
    reason=f"{_TAG} not available locally (set AAC_CLI=1 or `docker pull {_TAG}`)",
)


def _run_cli(workdir: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "run", "--rm", "-v", f"{workdir}:/work", "-w", "/work", _TAG, *args],
        capture_output=True, text=True, timeout=300,
    )


def test_generated_workspace_validates_and_exports(tmp_path) -> None:
    files = render_structurizr(_RICH, "build escrow marketplace", with_ci=True)
    for rel, content in files.items():
        fp = tmp_path / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)
    ws = "docs/design/structurizr/workspace.dsl"

    validate = _run_cli(str(tmp_path), "validate", "-workspace", ws)
    assert validate.returncode == 0, validate.stdout + validate.stderr

    (tmp_path / "build").mkdir(exist_ok=True)
    export = _run_cli(str(tmp_path), "export", "-workspace", ws, "-format", "mermaid",
                      "-output", "build")
    assert export.returncode == 0, export.stdout + export.stderr
    # the two saga dynamic views must have rendered
    mmd = {p.name for p in (tmp_path / "build").glob("*.mmd")}
    assert any("SettleOrder" in n for n in mmd)
