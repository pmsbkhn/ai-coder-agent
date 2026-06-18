"""Step-6 oracle-adequacy rules: L10 (no-assertion locked test) and L11 (impossible spend)
are HARD (lint_design, drive heal); O1 (perf with no timing) and O2 (substring-only oracle)
are ADVISORY (lint_oracle). High precision — a sound oracle lints clean."""

from __future__ import annotations

from aicoder.application.design_lint import lint_design, lint_oracle
from aicoder.domain.models import DesignSpec, ProposedTest, TechSpec


def _design(tests: list[ProposedTest]) -> DesignSpec:
    return DesignSpec(summary="loyalty",
                      tech_specs=[TechSpec(bounded_context="Loyalty", summary="points",
                                           test_plan=tests)])


def _codes(issues: list[str]) -> set[str]:
    return {i.split(" ", 1)[0] for i in issues}


def test_l10_flags_locked_test_with_no_assertion() -> None:
    t = ProposedTest(id="TC-LOY-01", kind="domain", spec="earn",
                     path="X.java", content="class X { @Test void t() { svc.earn(e); } }")
    assert "L10" in _codes(lint_design(_design([t])))


def test_l10_clean_when_test_asserts() -> None:
    t = ProposedTest(id="TC-LOY-01", kind="domain", spec="earn", path="X.java",
                     content="class X { @Test void t() { svc.earn(e); assertEquals(40, acc.balance()); } }")
    assert "L10" not in _codes(lint_design(_design([t])))
    # a fitness case may legitimately have no assertion body
    f = ProposedTest(id="TC-LOY-09", kind="fitness", spec="rule", content="// arch rule")
    assert "L10" not in _codes(lint_design(_design([f])))


def test_l11_flags_spending_more_than_balance() -> None:
    t = ProposedTest(id="TC-LOY-04", kind="domain",
                     spec="Given a buyer with 2000 points, when redeem is called, then balance "
                          "reduces by 5000 points and becomes negative.")
    assert "L11" in _codes(lint_design(_design([t])))


def test_l11_clean_when_spend_within_balance_or_ambiguous() -> None:
    ok = ProposedTest(id="TC-LOY-05", kind="domain",
                      spec="Given a buyer with 300 points, when redeem requests it, then it spends 200 points.")
    assert "L11" not in _codes(lint_design(_design([ok])))
    # two balances mentioned -> ambiguous -> skipped (precision over recall)
    amb = ProposedTest(id="TC-LOY-06", kind="domain",
                       spec="A buyer with 2000 points and an account with 100 points spends 5000 points.")
    assert "L11" not in _codes(lint_design(_design([amb])))


def test_o1_flags_perf_case_without_timing() -> None:
    perf = ProposedTest(id="TC-LOY-09", kind="fitness",
                        title="Redeem latency under 150 ms (p95)",
                        spec="Benchmark redeem; ensure p95 <= 150 ms.")  # no executable timing
    assert "O1" in _codes(lint_oracle(_design([perf])))
    timed = ProposedTest(id="TC-LOY-09", kind="fitness", title="Redeem p95 latency",
                         spec="p95 < 150 ms", path="P.java",
                         content="long start=System.nanoTime(); svc.redeem(r); assertTrue(elapsedMs < 150);")
    assert "O1" not in _codes(lint_oracle(_design([timed])))


def test_o2_flags_substring_only_oracle() -> None:
    weak = ProposedTest(id="TC-LOY-07", kind="adapter", spec="notify", path="N.java",
                        content="class N { @Test void t() { assertTrue(msg.contains(\"20 points\")); } }")
    assert "O2" in _codes(lint_oracle(_design([weak])))
    strong = ProposedTest(id="TC-LOY-07", kind="adapter", spec="notify", path="N.java",
                          content="class N { @Test void t() { assertEquals(20, n.newBalance()); "
                                  "assertTrue(msg.contains(\"points\")); } }")
    assert "O2" not in _codes(lint_oracle(_design([strong])))


def test_sound_oracle_lints_clean() -> None:
    t = ProposedTest(id="TC-LOY-01", kind="domain",
                     spec="Given a buyer with 1000 points, when redeem spends 500 points, balance is 500.",
                     path="X.java",
                     content="class X { @Test void t() { svc.redeem(r); assertEquals(500, acc.balance()); } }")
    d = _design([t])
    assert not (_codes(lint_design(d)) & {"L10", "L11"})
    assert lint_oracle(d) == []
