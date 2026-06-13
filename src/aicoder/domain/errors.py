"""Structured exception hierarchy rooted at DomainException.

Mirrors the MSFW convention (a single typed root). Adapters wrap foreign
errors (JSON-RPC, SDK exceptions) into these so the core never leaks
infrastructure types across a port boundary (TC-INT-05).
"""

from __future__ import annotations


class DomainException(Exception):
    """Root of every error the agent core raises."""


class InvalidStateTransitionException(DomainException):
    """An AgentSession was asked to move between two incompatible states.

    Enforces the linear-saga invariant (TC-CORE-01): e.g. asking the Coder to
    edit code before a plan exists.
    """

    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"Invalid state transition: {current} -> {target}")
        self.current = current
        self.target = target


class CircuitBreakerTrippedException(DomainException):
    """The self-healing loop exhausted its budget (TC-CORE-06)."""


class ToolInvocationError(DomainException):
    """A tool call failed at the MCP boundary.

    Adapters wrap JSON-RPC errors (e.g. -32601 Method not found) into this so a
    missing/stopped MCP server degrades gracefully instead of crashing the core
    (TC-INT-05).
    """

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code
