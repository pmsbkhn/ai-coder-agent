"""ApprovalPort implementations — the human gate for irreversible/outward or
binding actions, by `kind` (M6 deploy, M07 design-first).

DENY BY DEFAULT: the agent never proceeds on its own. EnvApproval (the default)
proceeds only when the kind-specific switch is set — `AICODER_DESIGN_APPROVE=1` /
`AICODER_DEPLOY_APPROVE=1` — so a human (or a CI step) gates each kind
independently. InteractiveApproval prompts a human on stdin. AutoDenyApproval
always holds (unattended runs).
"""

from __future__ import annotations

import os
import sys

from aicoder.application.ports.outbound import ApprovalPort

_TRUTHY = ("1", "true", "yes")


class AutoDenyApproval(ApprovalPort):
    def request_approval(self, kind: str, summary: str) -> bool:
        return False


class EnvApproval(ApprovalPort):
    """Approve only if AICODER_{KIND}_APPROVE is truthy — read at request time, so
    the value is the operator's explicit, current decision for that kind."""

    def request_approval(self, kind: str, summary: str) -> bool:
        var = f"AICODER_{kind.upper()}_APPROVE"
        return os.environ.get(var, "").strip().lower() in _TRUTHY


class InteractiveApproval(ApprovalPort):
    def request_approval(self, kind: str, summary: str) -> bool:
        if not sys.stdin or not sys.stdin.isatty():
            return False  # no human attached -> hold
        reply = input(f"\n[approval:{kind}] {summary}\n  proceed? [y/N] ").strip().lower()
        return reply in ("y", "yes")
