"""M6: human-approval-gated deploy. Deploy runs only for a green change, with a
configured command, AND explicit approval — safe (no deploy) by default."""

from __future__ import annotations

from pathlib import Path

from aicoder.adapters.approval import AutoDenyApproval, EnvApproval
from aicoder.adapters.deploy import CommandDeploy
from aicoder.adapters.memory_inmemory import InMemoryMemory
from aicoder.application.orchestrator import Orchestrator
from aicoder.application.profile import load_profile
from aicoder.domain.models import CodeChange, FileEdit, Plan, SessionState, Task, VerificationResult

from tests.test_orchestrator_loop import FakeBuild, FakeCoder, FakeGateway, FakePlanner

_PROFILE = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "msfw.yaml")


def _passed() -> VerificationResult:
    return VerificationResult(passed=True, functional_passed=True, arch_passed=True)


class _Approval:
    def __init__(self, ok: bool) -> None:
        self.ok = ok
        self.asked = False

    def request_approval(self, kind: str, summary: str) -> bool:
        self.asked = True
        return self.ok


class _Deployer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def deploy(self, workdir: str, command: str) -> dict:
        self.calls.append((workdir, command))
        return {"ok": True, "output": "deployed"}


def _orch(profile, approval, deployer, mem):
    plan = Plan(tasks=[Task(id="t1", description="x", target_files=["A.java"])])
    return Orchestrator(
        profile=profile, planner=FakePlanner(plan), coder=FakeCoder(),
        memory=mem, gateway=FakeGateway(), build=FakeBuild([_passed()]),
        approval=approval, deployer=deployer,
    )


def _profile_with_deploy(cmd: str):
    return _PROFILE.model_copy(update={"deploy": _PROFILE.deploy.model_copy(update={"command": cmd})})


def test_no_deploy_command_means_no_gate() -> None:
    mem = InMemoryMemory()
    appr, dep = _Approval(True), _Deployer()
    _orch(_PROFILE, appr, dep, mem).run_requirement("x")  # msfw profile has no deploy.command
    assert appr.asked is False and dep.calls == []


def test_approved_deploy_runs_command() -> None:
    mem = InMemoryMemory()
    appr, dep = _Approval(True), _Deployer()
    session = _orch(_profile_with_deploy("helm upgrade ..."), appr, dep, mem).run_requirement("x")
    assert session.state is SessionState.DONE
    assert dep.calls and dep.calls[0][1] == "helm upgrade ..."
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert "APPROVAL_REQUESTED" in events and "DEPLOYED" in events


def test_denied_deploy_holds_at_the_gate() -> None:
    mem = InMemoryMemory()
    appr, dep = _Approval(False), _Deployer()
    session = _orch(_profile_with_deploy("helm upgrade ..."), appr, dep, mem).run_requirement("x")
    assert session.state is SessionState.DONE       # the change is still done/committed
    assert dep.calls == []                          # but nothing was deployed
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert "APPROVAL_REQUESTED" in events and "DEPLOY_DENIED" in events and "DEPLOYED" not in events


def test_env_approval_denies_by_default_and_real_deploy_runs(tmp_path, monkeypatch) -> None:
    """Real adapters: EnvApproval holds unless AICODER_DEPLOY_APPROVE=1, and
    CommandDeploy actually runs the shell command in the workdir."""
    monkeypatch.delenv("AICODER_DEPLOY_APPROVE", raising=False)
    assert EnvApproval().request_approval("deploy", "x") is False
    assert AutoDenyApproval().request_approval("deploy", "x") is False
    monkeypatch.setenv("AICODER_DEPLOY_APPROVE", "1")
    assert EnvApproval().request_approval("deploy", "x") is True
    # kind-specific: the deploy switch does NOT approve a design request
    assert EnvApproval().request_approval("design", "x") is False

    res = CommandDeploy().deploy(str(tmp_path), "echo deployed > marker.txt")
    assert res["ok"] is True
    assert (tmp_path / "marker.txt").read_text().strip() == "deployed"
