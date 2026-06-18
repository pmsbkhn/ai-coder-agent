"""Negative units for the pure-Python Structurizr regression guard (S1–S7). The positive
path (a generated set validates clean) is covered in test_design_structurizr."""

from __future__ import annotations

from aicoder.application.structurizr_lint import validate_structurizr

_WS = "docs/design/structurizr/workspace.dsl"


def _codes(issues: list[str]) -> set[str]:
    return {i.split(" ", 1)[0] for i in issues}


def test_s1_inline_block_flagged() -> None:
    files = {_WS: 'element "Person" { shape Person }\n'}
    assert "S1" in _codes(validate_structurizr(files))


def test_s1_open_brace_as_last_token_is_ok() -> None:
    files = {_WS: 'system = softwareSystem "S" {\n}\n'}
    assert "S1" not in _codes(validate_structurizr(files))


def test_s2_missing_space_around_equals_flagged() -> None:
    files = {_WS: 'foo= component "X" "d" "domain"\n'}
    assert "S2" in _codes(validate_structurizr(files))


def test_s2_autolayout_and_quoted_equals_not_flagged() -> None:
    # an `=` inside a quoted string (e.g. "Pod (replicas=1)") must not trip S2
    files = {_WS: 'a = container "Pod (replicas=1)" "d"\n'}
    assert "S2" not in _codes(validate_structurizr(files))


def test_s3_readme_in_adr_dir_flagged() -> None:
    files = {
        _WS: 'system = softwareSystem "S" {\n!adrs adr\n}\n',
        "docs/design/structurizr/adr/0001-x.md": "# 1. x\n",
        "docs/design/structurizr/adr/README.md": "# readme\n",
    }
    assert "S3" in _codes(validate_structurizr(files))


def test_s4_embed_to_unknown_view_key_flagged() -> None:
    files = {
        _WS: 'systemContext system "SystemContext" {\ninclude *\n}\n',
        "docs/design/structurizr/documentation/01.md": "![x](embed:NoSuchView)\n",
    }
    assert "S4" in _codes(validate_structurizr(files))


def test_s5_undeclared_relationship_endpoint_flagged() -> None:
    files = {_WS: 'a = container "A" "d"\na -> ghost "uses"\n'}
    assert "S5" in _codes(validate_structurizr(files))


def test_s6_duplicate_view_key_flagged() -> None:
    files = {_WS: (
        'container system "Dup" {\ninclude *\n}\n'
        'component a "Dup" {\ninclude *\n}\n'
    )}
    assert "S6" in _codes(validate_structurizr(files))


def test_s7_include_to_missing_file_flagged() -> None:
    files = {_WS: 'system = softwareSystem "S" {\n!include ghost.dsl\n}\n'}
    assert "S7" in _codes(validate_structurizr(files))


def test_clean_minimal_workspace_has_no_findings() -> None:
    files = {_WS: (
        'workspace "W" "r" {\n'
        '  model {\n'
        '    system = softwareSystem "S" {\n'
        '      a = container "A" "d"\n'
        '    }\n'
        '  }\n'
        '  views {\n'
        '    systemContext system "SystemContext" {\n'
        '      include *\n'
        '    }\n'
        '  }\n'
        '}\n'
    )}
    assert validate_structurizr(files) == []
