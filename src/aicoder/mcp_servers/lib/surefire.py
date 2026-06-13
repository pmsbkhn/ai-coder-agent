"""Pure surefire-report parser — the DETERMINISTIC functional gate.

No LLM, no MCP. Reads Maven's `target/surefire-reports/*.xml` and returns plain
counts + failed-test ids + messages. Unit-tested against fixture XML so the gate
is trustworthy independent of any model.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


def _iter_report_files(root: Path, module: str | None) -> list[Path]:
    base = root / module if module else root
    return [
        p
        for p in sorted(base.rglob("surefire-reports/*.xml"))
        if not p.name.startswith("._")
    ]


def parse_files(files: list[Path]) -> dict:
    tests = failures = errors = skipped = 0
    failed_tests: list[str] = []
    messages: list[str] = []

    for f in files:
        try:
            root = ET.fromstring(f.read_text(encoding="utf-8", errors="replace"))
        except ET.ParseError:
            continue
        # The root may be <testsuite> or <testsuites> wrapping several suites.
        suites = [root] if root.tag == "testsuite" else root.iter("testsuite")
        for suite in suites:
            tests += int(suite.get("tests", 0))
            failures += int(suite.get("failures", 0))
            errors += int(suite.get("errors", 0))
            skipped += int(suite.get("skipped", 0))
            for case in suite.iter("testcase"):
                problem = case.find("failure")
                if problem is None:
                    problem = case.find("error")
                if problem is not None:
                    cls = case.get("classname", "")
                    name = case.get("name", "")
                    failed_tests.append(f"{cls}.{name}" if cls else name)
                    msg = problem.get("message") or (problem.text or "").strip()
                    if msg:
                        messages.append(f"{cls}.{name}: {msg}")

    return {
        "tests": tests,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "failed_tests": failed_tests,
        "messages": "\n".join(messages),
    }


def parse_reports(repo_root: str | Path, module: str | None = None) -> dict:
    """Aggregate every surefire report under repo_root (optionally one module)."""
    return parse_files(_iter_report_files(Path(repo_root), module))
