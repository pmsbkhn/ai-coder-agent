"""Requirements intake — parse a structured requirements YAML into a RequirementSpec.

This is the seam that replaces a vague prose prompt with a human-authored contract
(User Stories + acceptance criteria + measurable NFRs). It mirrors `profile.py`: the
YAML lives outside the core, the loader sits in the application layer, and the domain
model (`RequirementSpec`) stays pure (no yaml import there — enforced by import-linter).

A `meta.title` block is accepted as an alias for a top-level `title` so the file can
carry light metadata without polluting the domain model.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from aicoder.domain.models import RequirementSpec


def load_requirement_spec(path: str | Path) -> RequirementSpec:
    """Parse a requirements YAML into a validated RequirementSpec."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"requirements file {path} must be a YAML mapping")
    # Accept `meta: {title: ...}` as an alias for a top-level `title`.
    meta = data.pop("meta", None)
    if "title" not in data and isinstance(meta, dict) and meta.get("title"):
        data["title"] = meta["title"]
    return RequirementSpec.model_validate(data)


def render_requirement_section(spec: RequirementSpec) -> str:
    """Render a RequirementSpec as an explicit, ID-labeled prompt section — shared by
    the Analyst and Designer so each AC-/NFR- id is visible and referenceable (the
    anchors downstream artifacts trace back to). Pure string formatting, no I/O."""
    lines: list[str] = ["# Requirements (structured — BINDING; do not widen or drop)"]
    if spec.title:
        lines.append(f"_{spec.title}_")
    lines.append("\n## User Stories")
    for us in spec.stories:
        head = " ".join(p for p in [us.id, f"— {us.title}" if us.title else ""] if p)
        if us.priority:
            head += f" [{us.priority}]"
        lines.append(f"- **{head}**")
        if us.as_a or us.i_want or us.so_that:
            lines.append(f"  - As a {us.as_a}, I want {us.i_want}, so that {us.so_that}.")
        for ac in us.acceptance:
            lines.append(f"  - {ac.id}: {ac.as_text()}")
    lines.append("\n## Non-functional requirements (each must be addressed by the design)")
    if spec.nfrs:
        for n in spec.nfrs:
            extra = "; ".join(
                x for x in [
                    f"measure: {n.measurement}" if n.measurement else "",
                    f"source: {n.source}" if n.source else "",
                    f"scope: {n.scope}" if n.scope else "",
                ] if x
            )
            lines.append(f"- {n.id} [{n.category.value}] {n.metric}" + (f" ({extra})" if extra else ""))
    else:
        lines.append("- (none)")
    return "\n".join(lines)
