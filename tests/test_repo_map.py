"""Repo Map + zoom-in work against the REAL MSFW sample-service.

Read-only and fast (small module). Skips cleanly if MSFW isn't checked out here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aicoder.mcp_servers.lib import repo_map

_SAMPLE = Path("C:/Users/phams/IdeaProjects/msfw/sample-service")
pytestmark = pytest.mark.skipif(not _SAMPLE.exists(), reason="MSFW sample-service not present")


def test_repo_map_lists_types_and_signatures_only() -> None:
    text = repo_map.build_repo_map(_SAMPLE)
    # known symbols from the sample service
    assert "Order" in text
    assert "OrderService" in text
    # skeleton hygiene: junk and build output excluded
    assert "._" not in text
    assert "/target/" not in text


def test_get_symbol_returns_type_source() -> None:
    rel = "src/main/java/com/example/sample/domain/Order.java"
    src = repo_map.get_symbol(_SAMPLE, rel, "Order")
    assert src is not None
    assert "class Order" in src


def test_get_symbol_missing_returns_none() -> None:
    rel = "src/main/java/com/example/sample/domain/Order.java"
    assert repo_map.get_symbol(_SAMPLE, rel, "NoSuchType") is None
