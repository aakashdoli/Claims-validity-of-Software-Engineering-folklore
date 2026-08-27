"""Every statistical function checked against a hand-calculable example."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from rq3.analysis.comparisons import ComparisonResult, compare_claim
from rq3.analysis.correction import apply_bh, apply_bh_pairwise
from rq3.analysis.descriptives import (count_idk, describe_claim,
                                       sarle_bimodality_coefficient, valid_scores)
from rq3.analysis.effects import epsilon_squared, rank_biserial


# ---------------------------------------------------------------------------
# The IDK rule
# ---------------------------------------------------------------------------

def test_idk_is_never_treated_as_a_number():
    s = pd.Series(["1", "5", "IDK", "IDK", "3", None])
    assert list(valid_scores(s)) == [1.0, 5.0, 3.0]
    assert count_idk(s) == 2


def test_idk_excluded_from_median_but_rate_reported(cfg):
    # 6 valid answers (median 3.5) plus 4 IDK out of 10 respondents.
    s = pd.Series(["1", "2", "3", "4", "5", "5", "IDK", "IDK", "IDK", "IDK"])
    d = describe_claim("CLM-X", s, cfg)
    assert d.n_total == 10
    assert d.n_valid == 6
    assert d.n_idk == 4
    assert d.idk_rate == pytest.approx(0.4)
    assert d.median == pytest.approx(3.5)          # median of 1,2,3,4,5,5
    assert sum(d.percentages.values()) == pytest.approx(100.0)


def test_claim_with_only_idk_is_explicitly_excluded_not_missing(cfg):
    d = describe_claim("CLM-X", pd.Series(["IDK"] * 40), cfg)
    assert d.excluded is True
    assert d.median is None
    assert "all IDK" in d.exclusion_reason
    assert d.idk_rate == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Stage 1 — bimodality
# ---------------------------------------------------------------------------

def test_bimodality_flag_on_a_clearly_split_claim(cfg):
    # 40% at 1-2, 40% at 4-5, 20% neutral -> meets 25/25/20 thresholds exactly.
    s = pd.Series(["1"] * 20 + ["2"] * 20 + ["3"] * 20 + ["4"] * 20 + ["5"] * 20)
    d = describe_claim("CLM-X", s, cfg)
    assert d.bimodal is True
    assert "bimodal:" in d.bimodality_reason


def test_bimodality_not_flagged_when_middle_is_too_heavy(cfg):
    # Same tails, but 21% neutral -> above max_middle_pct = 20.
    s = pd.Series(["1"] * 30 + ["2"] * 10 + ["3"] * 21 + ["4"] * 10 + ["5"] * 29)
    d = describe_claim("CLM-X", s, cfg)
    assert d.neutral_pct > 20.0
    assert d.bimodal is False


def test_bimodality_not_assessed_below_min_valid_n(cfg):
    s = pd.Series(["1"] * 5 + ["5"] * 5)          # min_valid_n is 30
    d = describe_claim("CLM-X", s, cfg)
    assert d.bimodal is False
    assert "not assessed" in d.bimodality_reason


def test_unimodal_central_claim_is_not_flagged(cfg):
    s = pd.Series(["3"] * 60 + ["2"] * 20 + ["4"] * 20)
    assert describe_claim("CLM-X", s, cfg).bimodal is False


def test_bimodality_thresholds_are_configurable(cfg_factory):
    s = pd.Series(["1"] * 20 + ["2"] * 20 + ["3"] * 20 + ["4"] * 20 + ["5"] * 20)
    strict = cfg_factory(**{"descriptives.bimodality.max_middle_pct": 10.0})
    assert describe_claim("CLM-X", s, strict).bimodal is False


def test_sarle_moments_match_scipy(cfg):
    """The hand-written skew/kurtosis inside BC must equal scipy's vetted ones."""
    rng = np.random.default_rng(7)
    x = rng.integers(1, 6, size=400).astype(float)
    n = x.size
    m, sd = x.mean(), x.std(ddof=1)
    z = (x - m) / sd
    skew = (z ** 3).sum() * n / ((n - 1) * (n - 2))
    g2 = ((z ** 4).sum() * n * (n + 1) / ((n - 1) * (n - 2) * (n - 3))
          - 3 * (n - 1) ** 2 / ((n - 2) * (n - 3)))
    assert skew == pytest.approx(stats.skew(x, bias=False))
    assert g2 == pytest.approx(stats.kurtosis(x, bias=False))
    expected = (skew ** 2 + 1) / (g2 + 3 * (n - 1) ** 2 / ((n - 2) * (n - 3)))
    assert sarle_bimodality_coefficient(x) == pytest.approx(expected)


def test_sarle_separates_split_from_peaked_distributions():
    split = np.array([1.0] * 50 + [5.0] * 50)
    peaked = np.array([3.0] * 80 + [2.0] * 10 + [4.0] * 10)
    assert sarle_bimodality_coefficient(split) > 0.555
    assert sarle_bimodality_coefficient(peaked) < 0.555


# ---------------------------------------------------------------------------
# Stage 2 — tests and the subgroup-size floor
# ---------------------------------------------------------------------------

def test_kruskal_wallis_h_matches_hand_calculation():
    """A = 1,1,2  B = 3,3,4  C = 5,5,5  (no cross-group ties on the extremes).

    Pooled ranks: 1,1 -> 1.5, 1.5 ; 2 -> 3 ; 3,3 -> 4.5, 4.5 ; 4 -> 6 ;
                  5,5,5 -> 8, 8, 8
    R_A = 1.5 + 1.5 + 3 = 6 ; R_B = 4.5 + 4.5 + 6 = 15 ; R_C = 24
    H_raw = 12/(9*10) * (6^2/3 + 15^2/3 + 24^2/3) - 3*10 = 7.2
    tie correction C = 1 - sum(t^3 - t)/(n^3 - n)
                     = 1 - ((8-2)+(8-2)+(27-3))/(729-9) = 1 - 36/720 = 0.95
    H = 7.2 / 0.95 = 7.578947...
    """
    a, b, c = [1, 1, 2], [3, 3, 4], [5, 5, 5]
    res = stats.kruskal(a, b, c)
    assert res.statistic == pytest.approx(7.2 / 0.95)


def test_epsilon_squared_matches_hand_calculation(cfg):
    e = epsilon_squared(7.2, n=9, k_groups=3, cfg=cfg)
    assert e.epsilon_squared == pytest.approx((7.2 - 3 + 1) / (9 - 3))
    assert e.magnitude == "large"


def test_subgroup_below_floor_is_excluded_with_a_reason(cfg_factory):
    cfg = cfg_factory(**{"comparisons.min_subgroup_size": 10})
    answers = pd.Series(["3"] * 12 + ["4"] * 12 + ["5"] * 5)
    groups = pd.Series(["a"] * 12 + ["b"] * 12 + ["tiny"] * 5)
    result, exclusions = compare_claim("CLM-X", answers, groups, "role", cfg)
    assert result.test == "mann_whitney_u"        # only a and b survived
    tiny = [g for g in result.groups if g.group == "tiny"][0]
    assert tiny.included is False
    assert "below min_subgroup_size=10" in tiny.exclusion_reason
    assert any(e.group == "tiny" and e.scope == "subgroup" for e in exclusions)


def test_floor_of_three_is_not_used(cfg):
    """Regression guard: the old pipeline's floor of 3 was a known bug."""
    assert cfg.min_subgroup_size >= 10


def test_comparison_with_too_few_surviving_groups_is_reported_not_dropped(cfg_factory):
    cfg = cfg_factory(**{"comparisons.min_subgroup_size": 10})
    answers = pd.Series(["3"] * 12 + ["4"] * 5)
    groups = pd.Series(["big"] * 12 + ["small"] * 5)
    result, exclusions = compare_claim("CLM-X", answers, groups, "role", cfg)
    assert result.excluded is True
    assert result.test is None
    assert result.p_value is None
    assert "need at least" in result.exclusion_reason
    assert any(e.scope == "comparison" for e in exclusions)


def test_constant_answers_are_excluded_rather_than_crashing(cfg_factory):
    cfg = cfg_factory(**{"comparisons.min_subgroup_size": 10})
    answers = pd.Series(["4"] * 40)
    groups = pd.Series(["a"] * 20 + ["b"] * 20)
    result, exclusions = compare_claim("CLM-X", answers, groups, "role", cfg)
    assert result.excluded is True
    assert "no variance" in result.exclusion_reason


def test_idk_answers_do_not_enter_the_ranking(cfg_factory):
    cfg = cfg_factory(**{"comparisons.min_subgroup_size": 10})
    a_answers = ["5"] * 10 + ["IDK"] * 20
    b_answers = ["1"] * 10 + ["IDK"] * 20
    answers = pd.Series(a_answers + b_answers)
    groups = pd.Series(["a"] * 30 + ["b"] * 30)
    result, _ = compare_claim("CLM-X", answers, groups, "role", cfg)
    a = [g for g in result.groups if g.group == "a"][0]
    assert a.n_total == 30 and a.n_valid == 10 and a.n_idk == 20
    assert a.idk_rate == pytest.approx(20 / 30)
    # all 10 vs 10 pairs favour 'a': r = +1.0
    assert result.effect.r == pytest.approx(1.0)
    assert result.effect.total_pairs == 100


# ---------------------------------------------------------------------------
# Stage 4 — Benjamini-Hochberg
# ---------------------------------------------------------------------------

def _fake(variable: str, pvals: list[float]) -> list[ComparisonResult]:
    return [ComparisonResult(claim_id=f"C{i}", variable=variable, test="mann_whitney_u",
                             statistic=1.0, p_value=p) for i, p in enumerate(pvals)]


def test_bh_matches_hand_calculation(cfg):
    """p = [.001, .2, .5, .7, .9], m = 5.

    adjusted_j = min over k >= j of (m/k) * p_k, made monotone:
      j=1: 5/1(.001) = .005   j=2: 5/2(.2) = .5   j=3: 5/3(.5) = .8333
      j=4: 5/4(.7) = .875     j=5: 5/5(.9) = .9
    -> [.005, .5, .8333, .875, .9]; only the first is <= alpha = .05
    """
    results = _fake("experience", [0.001, 0.2, 0.5, 0.7, 0.9])
    summaries = apply_bh(results, cfg)
    adj = [r.p_adjusted for r in results]
    assert adj == pytest.approx([0.005, 0.5, 5 / 3 * 0.5, 0.875, 0.9])
    assert [r.significant_adjusted for r in results] == [True, False, False, False, False]
    assert summaries[0].n_significant_raw == 1
    assert summaries[0].n_significant_adjusted == 1


def test_bh_is_applied_per_variable_family_not_pooled(cfg):
    """One family of 5 strong p-values must not be diluted by another family."""
    strong = _fake("experience", [0.001, 0.002, 0.003, 0.004, 0.005])
    weak = _fake("role", [0.6, 0.7, 0.8, 0.9, 0.95])
    summaries = apply_bh(strong + weak, cfg)
    by_var = {s.variable: s for s in summaries}
    assert by_var["experience"].n_tests == 5      # family size is 5, not 10
    assert by_var["experience"].n_significant_adjusted == 5
    assert by_var["role"].n_significant_adjusted == 0
    # Largest experience p-value: 5/5 * 0.005 = 0.005, not 10/10 * 0.005.
    assert strong[-1].p_adjusted == pytest.approx(0.005)


def test_bh_ignores_excluded_comparisons_when_sizing_the_family(cfg):
    results = _fake("experience", [0.001, 0.04])
    results.append(ComparisonResult(claim_id="C9", variable="experience", test=None,
                                    statistic=None, p_value=None, excluded=True,
                                    exclusion_reason="too few subgroups"))
    summaries = apply_bh(results, cfg)
    assert summaries[0].n_tests == 2          # not 3
    assert summaries[0].n_excluded == 1
    assert results[1].p_adjusted == pytest.approx(0.04)   # 2/2 * 0.04
    assert results[2].p_adjusted is None


def test_raw_p_value_is_always_kept_alongside_the_adjusted_one(cfg):
    results = _fake("role", [0.03, 0.9])
    apply_bh(results, cfg)
    assert results[0].p_value == 0.03
    assert results[0].p_adjusted == pytest.approx(0.06)   # 2/1 * 0.03
    assert results[0].significant_adjusted is False       # visible, not hidden


def test_pairwise_correction_is_scoped_to_the_claim(cfg):
    from rq3.analysis.comparisons import PairwiseResult
    pw = [PairwiseResult("a", "b", 20, 20, 1.0, 0.01),
          PairwiseResult("a", "c", 20, 20, 1.0, 0.30)]
    apply_bh_pairwise(pw, cfg)
    assert pw[0].p_adjusted == pytest.approx(0.02)   # 2/1 * 0.01
    assert pw[1].p_adjusted == pytest.approx(0.30)   # 2/2 * 0.30
    assert [p.significant_adjusted for p in pw] == [True, False]


# ---------------------------------------------------------------------------
# Stage 3 — effect-size interpretation bands
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("r,expected", [
    (0.48, "large"), (0.47, "medium"), (0.33, "medium"),
    (0.32, "small"), (0.14, "small"), (0.13, "negligible"), (0.0, "negligible"),
])
def test_romano_thresholds(cfg, r, expected):
    """Romano et al. (2006): >.47 large, .33-.47 medium, .14-.33 small."""
    from rq3.analysis.effects import _magnitude
    assert _magnitude(abs(r), cfg) == expected


def test_effect_size_is_computed_for_non_significant_comparisons_too(cfg_factory):
    cfg = cfg_factory(**{"comparisons.min_subgroup_size": 10})
    answers = pd.Series(["3"] * 10 + ["4"] * 10 + ["3"] * 10 + ["4"] * 10)
    groups = pd.Series(["a"] * 20 + ["b"] * 20)
    result, _ = compare_claim("CLM-X", answers, groups, "role", cfg)
    assert result.p_value > 0.05          # identical distributions
    assert result.effect is not None      # effect size still reported
    assert result.effect.r == pytest.approx(0.0)
