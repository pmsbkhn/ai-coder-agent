"""MavenBuildTool — BuildToolPort over the Maven MCP server.

Turns the raw, parsed surefire numbers into a VerificationResult. The functional
verdict is purely deterministic; arch_passed stays True until ArchUnit lands in M4.
Going beyond MSFW = a sibling adapter (GradleBuildTool, NpmBuildTool) behind the
same BuildToolPort — no core change.
"""

from __future__ import annotations

import hashlib

from aicoder.adapters.mcp_gateway import raise_for_response
from aicoder.application.ports.outbound import MCPGatewayPort
from aicoder.domain.models import ToolRequest, VerificationResult


class MavenBuildTool:
    def __init__(self, gateway: MCPGatewayPort) -> None:
        self._gateway = gateway

    def run_tests(
        self, module: str | None = None, test: str | None = None, workdir: str | None = None
    ) -> VerificationResult:
        resp = self._gateway.execute_tool_call(
            ToolRequest(
                server="maven",
                method="run_tests",
                params={"module": module or "", "test": test or "", "workdir": workdir or ""},
            )
        )
        data = raise_for_response(resp)

        failures = int(data.get("failures", 0))
        errors = int(data.get("errors", 0))
        exit_code = int(data.get("exit_code", 1))
        failed_tests = list(data.get("failed_tests", []))

        functional_passed = exit_code == 0 and failures == 0 and errors == 0
        arch_passed = True  # ArchUnit gate arrives in M4

        # Maven prints COMPILER errors to stdout (not stderr, not surefire), so
        # without this the Coder gets no feedback on the most common failure —
        # a compile break — and self-healing goes blind. Pull the [ERROR] lines.
        stdout = data.get("stdout_tail", "")
        compiler_errors = "\n".join(
            ln for ln in stdout.splitlines() if "[ERROR]" in ln or "BUILD FAILURE" in ln
        )
        evidence = "\n".join(
            part
            for part in (data.get("messages", ""), compiler_errors, data.get("stderr_tail", ""))
            if part
        ).strip()

        return VerificationResult(
            passed=functional_passed and arch_passed,
            functional_passed=functional_passed,
            arch_passed=arch_passed,
            failed_tests=failed_tests,
            evidence=evidence,
            error_signature=None if functional_passed else _signature(failed_tests, evidence),
        )


def _signature(failed_tests: list[str], evidence: str) -> str:
    """Stable hash of a failure — drives the no-progress breaker (M3)."""
    h = hashlib.sha1()
    h.update("|".join(sorted(failed_tests)).encode("utf-8"))
    h.update(evidence[:500].encode("utf-8", "replace"))
    return h.hexdigest()[:12]
