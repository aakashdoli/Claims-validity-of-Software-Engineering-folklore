"""The three-bucket classification and the two-group experience comparison.

Every number here is hand-calculable from the counts in the fixture.
"""

from __future__ import annotations

import pandas as pd
import pytest

from rq3.analysis.buckets import (CLEAR_DIRECTION, IDK_DOMINANT, MIXED,
                                  classify, role_breakdown)
from rq3.analysis.descriptives import describe_claim


def _series(counts: dict[str, int]) -> pd.Series:
    out: list[str] = []
    for value, n in counts.items():
        out.extend([value] * n)
    return pd.Series(out)


def _bucket(counts: dict[str, int], cfg):
    return classify(describe_claim("C1", _series(counts), cfg), cfg)


# ---------------------------------------------------------------------------
# Denominators — the distinction the whole module rests on
# ---------------------------------------------------------------------------

def test_the_two_denominators_are_different_numbers(cfg):
    """80 on the scale, 20 IDK: directional = 80, full sample = 100."""
    b = _bucket({"4": 50, "3": 30, "IDK": 20}, cfg)
    assert b.full_sample_n == 100
    assert b.directional_n == 80
    assert b.idk_n == 20
    assert b.idk_rate == pytest.approx(0.20)          # 20/100, full sample
    assert b.pct_agree == pytest.approx(50 / 80)      # 50/80, directional
    assert b.pct_neutral == pytest.approx(30 / 80)


def test_idk_never_enters_the_directional_denominator(cfg):
    # 40 IDK of 140 = 28.6%, just under the dominance threshold, so the
    # directional shares are computed — and they divide by 100, not 140.
    b = _bucket({"5": 60, "1": 40, "IDK": 40}, cfg)
    assert b.full_sample_n == 140
    assert b.directional_n == 100
    assert b.pct_agree + b.pct_disagree + b.pct_neutral == pytest.approx(1.0)
    assert b.pct_agree == pytest.approx(0.60)


# ---------------------------------------------------------------------------
# Majority rule
# ---------------------------------------------------------------------------

def test_majority_agreed(cfg):
    # 60/100 directional agree -> above 0.50
    b = _bucket({"4": 40, "5": 20, "3": 20, "1": 20}, cfg)
    assert b.bucket == CLEAR_DIRECTION
    assert b.majority_agreed is True
    assert b.majority_disagreed is False
    assert b.majority_direction == "agreed"
    assert b.belief_label == "Majority agreed"
    assert b.pct_agree == pytest.approx(0.60)


def test_majority_disagreed(cfg):
    b = _bucket({"1": 40, "2": 21, "3": 19, "5": 20}, cfg)
    assert b.bucket == CLEAR_DIRECTION
    assert b.majority_disagreed is True
    assert b.belief_label == "Majority disagreed"
    assert b.pct_disagree == pytest.approx(0.61)


def test_exactly_fifty_percent_is_mixed_not_a_majority(cfg):
    """The rule is strictly greater than, so 50/50 is not a majority."""
    b = _bucket({"4": 50, "1": 50}, cfg)
    assert b.pct_agree == pytest.approx(0.50)
    assert b.bucket == MIXED
    assert b.majority_agreed is False
    assert b.majority_direction == "none"


def test_neutral_counts_toward_the_denominator_but_neither_side(cfg):
    """49 agree / 49 disagree / 2 neutral — neutral blocks both majorities."""
    b = _bucket({"4": 49, "1": 49, "3": 2}, cfg)
    assert b.directional_n == 100
    assert b.pct_agree == pytest.approx(0.49)
    assert b.pct_disagree == pytest.approx(0.49)
    assert b.pct_neutral == pytest.approx(0.02)
    assert b.bucket == MIXED


def test_a_wall_of_neutral_is_mixed(cfg):
    b = _bucket({"3": 90, "4": 5, "1": 5}, cfg)
    assert b.bucket == MIXED
    assert "neither side passed" in b.reason


# ---------------------------------------------------------------------------
# IDK dominance — checked FIRST, short-circuits the majority rule
# ---------------------------------------------------------------------------

def test_idk_dominant_at_exactly_thirty_percent(cfg):
    """>= 0.30 of the FULL sample. 30/100 flags."""
    b = _bucket({"4": 70, "IDK": 30}, cfg)
    assert b.idk_rate == pytest.approx(0.30)
    assert b.bucket == IDK_DOMINANT
    assert b.majority_agreed is None          # never computed
    assert b.pct_agree is None
    assert "no majority is computed" in b.reason


def test_just_below_the_idk_threshold_is_classified_normally(cfg):
    b = _bucket({"4": 71, "IDK": 29}, cfg)
    assert b.idk_rate == pytest.approx(0.29)
    assert b.bucket == CLEAR_DIRECTION
    assert b.majority_agreed is True


def test_idk_dominance_beats_an_overwhelming_majority(cfg):
    """Order matters: even 100% agreement among answerers does not rescue it."""
    b = _bucket({"5": 60, "IDK": 40}, cfg)
    assert b.bucket == IDK_DOMINANT
    assert b.majority_direction is None


def test_idk_threshold_uses_the_full_sample_not_the_directional_one(cfg):
    """40 IDK of 140 = 28.6% of the full sample — below 30%, so not dominant.

    Against the directional denominator it would be 40%, which is exactly the
    error this test exists to catch.
    """
    b = _bucket({"4": 100, "IDK": 40}, cfg)
    assert b.full_sample_n == 140
    assert b.idk_rate == pytest.approx(40 / 140)
    assert b.bucket == CLEAR_DIRECTION


def test_thresholds_are_configurable(cfg_factory):
    strict = cfg_factory(**{"belief.idk_dominance.threshold": 0.20})
    assert _bucket({"4": 75, "IDK": 25}, strict).bucket == IDK_DOMINANT
    loose = cfg_factory(**{"belief.majority.threshold": 0.70})
    assert _bucket({"4": 60, "1": 40}, loose).bucket == MIXED


def test_no_directional_answers_at_all(cfg):
    b = _bucket({"IDK": 50}, cfg)
    assert b.bucket == IDK_DOMINANT          # 100% IDK
    b2 = classify(describe_claim("C1", pd.Series([], dtype=object), cfg), cfg)
    assert b2.directional_n == 0


# ---------------------------------------------------------------------------
# Role breakdown — descriptive only
# ---------------------------------------------------------------------------

def test_role_breakdown_is_descriptive_and_totals_correctly(cfg):
    answers = pd.Series(["4"] * 30 + ["1"] * 10 + ["IDK"] * 10)
    roles = pd.Series(["Developer"] * 25 + ["Architect"] * 25)
    rows = role_breakdown(answers, roles, cfg)
    assert {r["role"] for r in rows} == {"Developer", "Architect"}
    assert sum(r["n_total"] for r in rows) == 50
    assert sum(r["directional_n"] for r in rows) == 40
    assert sum(r["idk_n"] for r in rows) == 10
    # No p-value, no test statistic anywhere in the output.
    assert all("p_value" not in r and "statistic" not in r for r in rows)


def test_role_breakdown_keeps_respondents_with_no_role(cfg):
    answers = pd.Series(["4"] * 10)
    roles = pd.Series(["Developer"] * 6 + [None] * 4)
    rows = role_breakdown(answers, roles, cfg)
    assert "(not recorded)" in {r["role"] for r in rows}
    assert sum(r["n_total"] for r in rows) == 10
