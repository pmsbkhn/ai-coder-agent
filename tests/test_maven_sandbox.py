"""Sandbox command construction (M5). Pure — asserts the argv the maven server
builds for the direct vs Docker-isolated build, without running Maven or Docker."""

from __future__ import annotations

from pathlib import Path

from aicoder.mcp_servers.maven_server import _mvn_command


def test_direct_command_is_plain_mvn() -> None:
    cmd = _mvn_command(Path("/wt"), "", "", sandbox="", image="img", m2="/m2")
    assert cmd[-2:] == ["test"] or cmd[1] == "test"
    assert "docker" not in cmd
    assert cmd[0].endswith("mvn") or cmd[0] == "mvn"


def test_sandbox_command_isolates_the_build() -> None:
    cmd = _mvn_command(Path("/wt"), "", "", sandbox="docker",
                       image="maven:3.9-eclipse-temurin-21", m2="/home/u/.m2")
    assert cmd[0] == "docker" and cmd[1] == "run" and "--rm" in cmd
    # no network, worktree + m2 mounted, offline maven
    assert cmd[cmd.index("--network") + 1] == "none"
    assert "-v" in cmd and "/wt:/work" in cmd and "/home/u/.m2:/root/.m2" in cmd
    assert "maven:3.9-eclipse-temurin-21" in cmd
    assert cmd[-3:] == ["mvn", "-o", "test"]


def test_sandbox_command_scopes_module_and_test() -> None:
    cmd = _mvn_command(Path("/wt"), "sample-service", "FooTest",
                       sandbox="docker", image="img", m2="/m2")
    assert cmd[-5:] == ["mvn", "-o", "test", "-pl", "sample-service"] or (
        "-pl" in cmd and "sample-service" in cmd and "-Dtest=FooTest" in cmd
    )
    assert "-Dtest=FooTest" in cmd
