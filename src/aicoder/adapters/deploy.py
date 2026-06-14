"""DeployPort implementation — runs the profile's deploy command (M6).

Deliberately thin: the deploy step is target-specific shell (helm/kubectl/a
script), defined as data in the Project Profile, not code in the core. Runs only
after a green change AND human approval (the orchestrator enforces both).
"""

from __future__ import annotations

import subprocess

from aicoder.application.ports.outbound import DeployPort


class CommandDeploy(DeployPort):
    def deploy(self, workdir: str, command: str) -> dict:
        proc = subprocess.run(
            command, shell=True, cwd=workdir, capture_output=True, text=True,
            encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
        )
        if proc.returncode != 0:
            return {"ok": False, "error": (proc.stderr or proc.stdout or "").strip()[-2000:]}
        return {"ok": True, "output": (proc.stdout or "").strip()[-2000:]}
