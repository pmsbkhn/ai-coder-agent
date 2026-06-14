"""ApprovalPort implementations — the human deploy gate (M6).

DENY BY DEFAULT: the agent never deploys on its own. EnvApproval (the default)
proceeds only when AICODER_DEPLOY_APPROVE=1 is explicitly set — suitable for a
human flipping a switch or a CI step gating on a manual approval. InteractiveApproval
prompts a human on stdin. AutoDenyApproval always holds (e.g. unattended runs).
"""

from __future__ import annotations

import os
import sys

from aicoder.application.ports.outbound import ApprovalPort


class AutoDenyApproval(ApprovalPort):
    def request_approval(self, summary: str) -> bool:
        return False


class EnvApproval(ApprovalPort):
    """Approve only if AICODER_DEPLOY_APPROVE is truthy (1/true/yes) — read at
    request time, so the value is the operator's explicit, current decision."""

    def request_approval(self, summary: str) -> bool:
        return os.environ.get("AICODER_DEPLOY_APPROVE", "").strip().lower() in ("1", "true", "yes")


class InteractiveApproval(ApprovalPort):
    def request_approval(self, summary: str) -> bool:
        if not sys.stdin or not sys.stdin.isatty():
            return False  # no human attached -> hold
        reply = input(f"\n[approval] Deploy this change? {summary}\n  proceed? [y/N] ").strip().lower()
        return reply in ("y", "yes")
