"""LLMCoder produces validated whole-file edits (hermetic, no network)."""

from __future__ import annotations

from aicoder.adapters.coder_llm import LLMCoder
from aicoder.domain.models import CodeChange, Task


class FakeLLM:
    model = "fake"

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.last_user = ""

    def complete_json(self, *, system, user, json_schema, tool_name="emit") -> dict:
        self.last_user = user
        return self._payload

    def complete_text(self, *, system, user, max_tokens=2048) -> str:  # pragma: no cover
        return ""


def test_coder_returns_full_file_edits() -> None:
    payload = {
        "edits": [{"path": "A.java", "content": "class A { int x; }"}],
        "notes": "added field",
    }
    coder = LLMCoder(FakeLLM(payload))
    change = coder.apply_task(
        Task(id="t1", description="add field x", target_files=["A.java"]),
        files={"A.java": "class A { }"},
    )
    assert isinstance(change, CodeChange)
    assert change.edits[0].path == "A.java"
    assert "int x" in change.edits[0].content


def test_coder_injects_error_context_on_retry() -> None:
    fake = FakeLLM({"edits": [], "notes": "n"})
    coder = LLMCoder(fake)
    coder.apply_task(
        Task(id="t1", description="fix it"),
        files={},
        error_context="java: cannot find symbol 'x'",
    )
    assert "Previous attempt failed" in fake.last_user
    assert "cannot find symbol" in fake.last_user
