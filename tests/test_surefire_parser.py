"""The deterministic functional gate parses real surefire XML correctly."""

from __future__ import annotations

from aicoder.mcp_servers.lib import surefire

_SUITE = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.example.FooTest" tests="3" failures="1" errors="0" skipped="1">
  <testcase name="ok" classname="com.example.FooTest" time="0.01"/>
  <testcase name="bad" classname="com.example.FooTest" time="0.02">
    <failure message="expected true but was false">java.lang.AssertionError at Foo.java:42</failure>
  </testcase>
  <testcase name="ignored" classname="com.example.FooTest"><skipped/></testcase>
</testsuite>
"""


def test_parse_counts_and_failed_tests(tmp_path) -> None:
    reports = tmp_path / "target" / "surefire-reports"
    reports.mkdir(parents=True)
    (reports / "TEST-com.example.FooTest.xml").write_text(_SUITE, encoding="utf-8")

    s = surefire.parse_reports(tmp_path)

    assert s["tests"] == 3
    assert s["failures"] == 1
    assert s["errors"] == 0
    assert s["skipped"] == 1
    assert "com.example.FooTest.bad" in s["failed_tests"]
    assert "expected true but was false" in s["messages"]


def test_empty_when_no_reports(tmp_path) -> None:
    s = surefire.parse_reports(tmp_path)
    assert s["tests"] == 0 and s["failed_tests"] == []
