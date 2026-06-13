"""Architectural fitness functions for the AGENT ITSELF.

Self-contained (pure stdlib AST walk) so they run with no external services and
no import-linter install. They are the executable form of TC-ARCH-01 / TC-ARCH-02:
the agent must not violate its own hexagonal boundaries.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "aicoder"

# Infrastructure SDKs the pure layers must never import.
FORBIDDEN_INFRA = {
    "openai", "anthropic", "chromadb", "neo4j", "psycopg", "psycopg2",
    "mcp", "langgraph", "langchain", "sqlalchemy", "httpx", "requests",
}


def _imported_roots(py_file: Path) -> set[str]:
    """Top-level module names imported by a file."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def _py_files(package: str) -> list[Path]:
    return sorted((SRC / package).rglob("*.py"))


def test_tc_arch_01_domain_is_pure() -> None:
    """TC-ARCH-01: domain imports neither infrastructure SDKs nor upper layers."""
    forbidden = FORBIDDEN_INFRA | {"yaml"}
    for f in _py_files("domain"):
        roots = _imported_roots(f)
        bad = roots & forbidden
        assert not bad, f"domain/{f.name} imports forbidden module(s): {sorted(bad)}"
        assert "aicoder.application" not in _full_imports(f), (
            f"domain/{f.name} must not import the application layer"
        )
        assert "aicoder.adapters" not in _full_imports(f), (
            f"domain/{f.name} must not import the adapters layer"
        )


def test_tc_arch_02_application_uses_ports_not_sdks() -> None:
    """TC-ARCH-02: the application core binds to no concrete SDK and no adapter."""
    for f in _py_files("application"):
        roots = _imported_roots(f)
        bad = roots & FORBIDDEN_INFRA
        assert not bad, f"application/{f.name} imports forbidden SDK(s): {sorted(bad)}"
        assert "aicoder.adapters" not in _full_imports(f), (
            f"application/{f.name} must not import the adapters layer (depend on ports)"
        )


def _full_imports(py_file: Path) -> set[str]:
    """Fully-qualified module names (for intra-package layer checks)."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
    return names
