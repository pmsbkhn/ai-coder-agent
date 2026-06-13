"""LLMCoder — CoderPort backed by a provider-agnostic LLMClient.

Emits whole-file contents (validated as a CodeChange). On a healing retry the
distilled prior error is injected so the model can correct course. Whole-file
output + schema validation keeps this reliable even on weaker local models.
"""

from __future__ import annotations

from aicoder.adapters.llm.base import LLMClient
from aicoder.adapters.llm.structured import generate_structured
from aicoder.domain.models import CodeChange, Task

_SYSTEM = """You are the Coder of an autonomous agent on an MSFW project
(Java 21 / Spring Boot 4, strict Hexagonal / Ports & Adapters, DDD).

You are given one task, the CURRENT content of the relevant files, and possibly
the prior failure. Produce the FULL new content of every file you change.

Rules:
- Return complete file bodies, never diffs or ellipses.
- Touch only what the task needs; preserve unrelated code exactly.
- Respect MSFW conventions (pure domain, ports/adapters, reuse framework blocks).
- If you must create a new file, include its full path and content.
"""


class LLMCoder:
    def __init__(self, client: LLMClient, *, max_file_chars: int = 16000) -> None:
        self._client = client
        self._cap = max_file_chars

    def apply_task(
        self, task: Task, files: dict[str, str], error_context: str = ""
    ) -> CodeChange:
        files_block = "\n\n".join(
            f"--- {path} ---\n{content[: self._cap]}" for path, content in files.items()
        ) or "(no existing files provided)"

        user = (
            f"# Task\n{task.description}\n"
            f"Target files: {', '.join(task.target_files) or '(decide from context)'}\n"
            f"Constraints: {'; '.join(task.constraints) or '(none)'}\n\n"
            f"# Current files\n{files_block}"
        )
        if error_context:
            user += f"\n\n# Previous attempt failed — fix this\n{error_context}"

        return generate_structured(
            self._client, system=_SYSTEM, user=user, model_cls=CodeChange, retries=1
        )
