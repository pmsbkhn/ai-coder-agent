"""MavenBuildTool dual-assessment verdict (M4): functional vs architecture.

The functional verdict is deterministic (parsed surefire). With an arch_test_pattern,
failing architecture-rule tests are scored on a separate axis so the Verifier can say
WHICH gate failed — functional, architecture, or both."""

from __future__ import annotations

from aicoder.adapters.maven_build import MavenBuildTool
from aicoder.domain.models import ToolResponse


class FakeGateway:
    def __init__(self, data: dict) -> None:
        self._data = data

    def execute_tool_call(self, request) -> ToolResponse:
        return ToolResponse(ok=True, result=self._data)


def _result(**kw) -> dict:
    base = {"exit_code": 0, "failures": 0, "errors": 0, "failed_tests": [],
            "messages": "", "stdout_tail": "", "stderr_tail": ""}
    base.update(kw)
    return base


_ARCH = "*Architecture*"


def test_all_green_passes_both_axes() -> None:
    r = MavenBuildTool(FakeGateway(_result()), arch_test_pattern=_ARCH).run_tests()
    assert r.passed and r.functional_passed and r.arch_passed


def test_arch_rule_failure_fails_only_the_arch_axis() -> None:
    data = _result(exit_code=1, failures=1,
                   failed_tests=["com.example.eval.HexagonalArchitectureTest.domainIsPure"])
    r = MavenBuildTool(FakeGateway(data), arch_test_pattern=_ARCH).run_tests()
    assert not r.passed
    assert r.functional_passed is True   # no functional test broke
    assert r.arch_passed is False        # the architecture gate caught it


def test_functional_failure_is_not_charged_to_arch() -> None:
    data = _result(exit_code=1, failures=1, failed_tests=["com.example.eval.SmokeTest.deposit"])
    r = MavenBuildTool(FakeGateway(data), arch_test_pattern=_ARCH).run_tests()
    assert r.functional_passed is False and r.arch_passed is True and not r.passed


def test_compile_failure_is_functional_not_arch() -> None:
    data = _result(exit_code=1, stdout_tail="[ERROR] ...: cannot find symbol")
    r = MavenBuildTool(FakeGateway(data), arch_test_pattern=_ARCH).run_tests()
    assert r.functional_passed is False and r.arch_passed is True


def test_without_pattern_arch_axis_stays_true() -> None:
    """Backward compatible: profiles that don't opt into ArchUnit behave as before —
    an arch-named failure is just a functional failure."""
    data = _result(exit_code=1, failures=1, failed_tests=["X.HexagonalArchitectureTest.y"])
    r = MavenBuildTool(FakeGateway(data)).run_tests()
    assert r.arch_passed is True and r.functional_passed is False
