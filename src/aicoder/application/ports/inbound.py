"""Inbound ports — how the outside world drives the Orchestrator."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aicoder.domain.models import VerificationResult


@runtime_checkable
class RequirementPort(Protocol):
    def submit_requirement(self, prompt: str, idempotency_key: str | None = None) -> str:
        """Accept a user requirement. Returns the session id.

        The idempotency_key lets a duplicate submission short-circuit instead of
        burning Planner tokens twice (TC-CORE-02).
        """
        ...


@runtime_checkable
class FeedbackPort(Protocol):
    def process_verification_result(self, session_id: str, result: VerificationResult) -> None:
        """Feed a Verifier verdict back into the loop to decide continue/stop."""
        ...
