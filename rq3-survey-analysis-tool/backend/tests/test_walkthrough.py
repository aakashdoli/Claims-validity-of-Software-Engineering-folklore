"""The claim page's calculation walkthrough must BE the computation.

Every number the claim detail page shows as "working" is rebuilt here from the
rank sums by hand and asserted equal to what scipy returns. If the walkthrough
and the reported statistic could ever disagree, these tests fail — which is the
whole point: an examiner following the page by hand has to land on the published
number.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from rq3.analysis.comparisons import compare_claim
from rq3.analysis.correction import apply_bh
from rq3.analysis.descriptives import describe_claim


def _frame(groups: dict[str, list[str]]) -> tuple[pd.Series, pd.Series]:
    answers, labels = [], []
    for name, values in groups.items():
        answers.extend(values)
        labels.extend([name] * len(values))
    return pd.Series(answers), pd.Series(labels)


# ---------------------------------------------------------------------------
# Mann-Whitney walkthrough
# ---------------------------------------------------------------------------

def test_mann_whitney_walkthrough_matches_the_worked_example(cfg_factory):
    """The same 10-respondent example, now through the walkthrough builder.

    junior = [1,1,1,1,5], senior = [2,5,5,5,5]
      R₁ = 18, R₂ = 37, R₁+R₂ = 55 = N(N+1)/2
      U₁ = 18 − 5(6)/2 = 3,  U₂ = 37 − 5(6)/2 = 22,  U₁+U₂ = 25 = n₁n₂
    """
    cfg = cfg_factory(**{"comparisons.min_subgroup_size": 5})
    answers, groups = _frame({"junior": list("11115"), "senior": list("25555")})
    result, _ = compare_claim("CLM-TEST", answers, groups, "experience", cfg)

    v = result.working.values
    assert result.working.test == "mann_whitney_u"
    assert v["R1"] == pytest.approx(18.0)
    assert v["R2"] == pytest.approx(37.0)
    assert v["R1"] + v["R2"] == pytest.approx(10 * 11 / 2)
    assert v["U1"] == pytest.approx(3.0)
    assert v["U2"] == pytest.approx(22.0)
    assert v["U1"] + v["U2"] == pytest.approx(25)
    assert v["mu"] == pytest.approx(12.5)
    # The statistic scipy reports is U for the first group.
    assert v["U_reported"] == pytest.approx(result.statistic)


def test_mann_whitney_walkthrough_reproduces_scipys_p(cfg_factory):
    """The displayed z and p must equal scipy's, across many shapes."""
    cfg = cfg_factory(**{"comparisons.min_subgroup_size": 10})
    rng = np.random.default_rng(20260816)
    for _ in range(60):
        a = rng.integers(1, 6, size=int(rng.integers(10, 150)))
        b = rng.integers(1, 6, size=int(rng.integers(10, 150)))
        answers, groups = _frame({"a": [str(x) for x in a], "b": [str(x) for x in b]})
        result, _ = compare_claim("CLM-TEST", answers, groups, "role", cfg)
        if result.excluded:
            continue
        v = result.working.values
        expected = stats.mannwhitneyu(a.astype(float), b.astype(float),
                                      alternative="two-sided", method="asymptotic")
        assert v["U_reported"] == pytest.approx(expected.statistic)
        assert v["p"] == pytest.approx(expected.pvalue, rel=1e-12, abs=1e-15)
        assert v["p"] == pytest.approx(result.p_value, rel=1e-12, abs=1e-15)
        # U from rank sums, and the U₁+U₂ identity, must hold every time.
        assert v["U1"] == pytest.approx(v["R1"] - v["n1"] * (v["n1"] + 1) / 2)
        assert v["U1"] + v["U2"] == pytest.approx(v["n1"] * v["n2"])


def test_mann_whitney_walkthrough_steps_are_readable(cfg_factory):
    cfg = cfg_factory(**{"comparisons.min_subgroup_size": 5})
    answers, groups = _frame({"junior": list("11115"), "senior": list("25555")})
    result, _ = compare_claim("CLM-TEST", answers, groups, "experience", cfg)
    labels = [s["label"] for s in result.working.steps]
    for expected in ("Pooled midranks", "Expected U under H₀",
                     "Tie correction term", "Standard deviation of U",
                     "z with continuity correction", "Two-sided p"):
        assert expected in labels
    assert all(s["formula"] and s["result"] for s in result.working.steps)


# ---------------------------------------------------------------------------
# Kruskal-Wallis walkthrough
# ---------------------------------------------------------------------------

def test_kruskal_walkthrough_matches_hand_calculation(cfg_factory):
    """A = 1,1,2 · B = 3,3,4 · C = 5,5,5 — the hand example from test_statistics.

    R_A = 6, R_B = 15, R_C = 24; ΣRᵢ²/nᵢ = (36+225+576)/3 = 279
    H_raw = 12/(9·10) × 279 − 3(10) = 7.2
    C = 1 − ((8−2)+(8−2)+(27−3))/(729−9) = 1 − 36/720 = 0.95
    H = 7.2 / 0.95 = 7.5789…
    """
    cfg = cfg_factory(**{"comparisons.min_subgroup_size": 3})
    answers, groups = _frame({"A": list("112"), "B": list("334"), "C": list("555")})
    result, _ = compare_claim("CLM-TEST", answers, groups, "role", cfg)

    v = result.working.values
    assert result.working.test == "kruskal_wallis"
    assert v["rank_sums"]["A"] == pytest.approx(6.0)
    assert v["rank_sums"]["B"] == pytest.approx(15.0)
    assert v["rank_sums"]["C"] == pytest.approx(24.0)
    assert v["sum_R2_over_n"] == pytest.approx(279.0)
    assert v["H_uncorrected"] == pytest.approx(7.2)
    assert v["tie_term"] == pytest.approx(36.0)
    assert v["tie_correction"] == pytest.approx(0.95)
    assert v["H"] == pytest.approx(7.2 / 0.95)
    assert v["H"] == pytest.approx(result.statistic)
    assert v["df"] == 2


def test_kruskal_walkthrough_reproduces_scipys_p(cfg_factory):
    cfg = cfg_factory(**{"comparisons.min_subgroup_size": 10})
    rng = np.random.default_rng(4242)
    for _ in range(40):
        k = int(rng.integers(3, 7))
        arrays = [rng.integers(1, 6, size=int(rng.integers(10, 90))) for _ in range(k)]
        answers, groups = _frame({
            f"g{i}": [str(x) for x in arr] for i, arr in enumerate(arrays)})
        result, _ = compare_claim("CLM-TEST", answers, groups, "industry", cfg)
        if result.excluded:
            continue
        v = result.working.values
        expected = stats.kruskal(*[a.astype(float) for a in arrays])
        assert v["H"] == pytest.approx(expected.statistic)
        assert v["p"] == pytest.approx(expected.pvalue, rel=1e-12, abs=1e-15)
        assert v["p"] == pytest.approx(result.p_value, rel=1e-12, abs=1e-15)


# ---------------------------------------------------------------------------
# Subgroup breakdowns must add up to the overall breakdown
# ---------------------------------------------------------------------------

def test_subgroup_frequencies_sum_to_the_overall_frequencies(cfg_factory):
    """Nothing on the claim page may be un-traceable to the raw counts."""
    cfg = cfg_factory(**{"comparisons.min_subgroup_size": 10})
    rng = np.random.default_rng(11)
    values = [str(v) if v <= 5 else "IDK" for v in rng.integers(1, 7, size=300)]
    labels = list(rng.choice(["a", "b", "c", "tiny"], size=300,
                             p=[0.4, 0.35, 0.23, 0.02]))
    answers, groups = pd.Series(values), pd.Series(labels)

    overall = describe_claim("CLM-TEST", answers, cfg)
    result, _ = compare_claim("CLM-TEST", answers, groups, "role", cfg)

    # Every subgroup appears, included or not.
    assert set(g.group for g in result.groups) == set(labels)
    for point in cfg.likert_values:
        assert sum(g.frequencies[point] for g in result.groups) == \
            overall.frequencies[point]
    assert sum(g.n_idk for g in result.groups) == overall.n_idk
    assert sum(g.n_total for g in result.groups) == overall.n_total


def test_respondents_with_no_demographic_answer_get_their_own_row(cfg_factory):
    """Demographics were optional. Those respondents must still add up.

    Without this row the subgroup counts silently fall short of the overall
    counts and the claim page's "totals must equal the overall breakdown"
    reconciliation would be false.
    """
    from rq3.analysis.comparisons import UNASSIGNED_LABEL
    cfg = cfg_factory(**{"comparisons.min_subgroup_size": 10})
    answers = pd.Series(["4"] * 20 + ["2"] * 20 + ["5"] * 7 + ["IDK"] * 3)
    groups = pd.Series(["a"] * 20 + ["b"] * 20 + [None] * 10)

    overall = describe_claim("CLM-TEST", answers, cfg)
    result, exclusions = compare_claim("CLM-TEST", answers, groups, "country", cfg)

    row = next(g for g in result.groups if g.group == UNASSIGNED_LABEL)
    assert row.included is False
    assert row.excluded_kind == "unassigned"
    assert row.n_total == 10 and row.n_valid == 7 and row.n_idk == 3
    assert row.frequencies[5] == 7
    assert row.rank_sum is None
    assert "did not answer the optional" in row.exclusion_reason

    # The reconciliation the page asserts now actually holds.
    for point in cfg.likert_values:
        assert sum(g.frequencies[point] for g in result.groups) == \
            overall.frequencies[point]
    assert sum(g.n_total for g in result.groups) == overall.n_total
    assert sum(g.n_idk for g in result.groups) == overall.n_idk

    # And it is logged under its own scope, not as a size exclusion.
    assert any(e.scope == "unassigned" for e in exclusions)
    assert not any(e.scope == "subgroup" and e.group == UNASSIGNED_LABEL
                   for e in exclusions)
    # The test itself is unaffected: it still ran on the two real subgroups.
    assert result.test == "mann_whitney_u"


def test_unassigned_row_is_absent_when_every_respondent_answered(cfg_factory):
    from rq3.analysis.comparisons import UNASSIGNED_LABEL
    cfg = cfg_factory(**{"comparisons.min_subgroup_size": 10})
    answers = pd.Series(["4"] * 20 + ["2"] * 20)
    groups = pd.Series(["a"] * 20 + ["b"] * 20)
    result, _ = compare_claim("CLM-TEST", answers, groups, "role", cfg)
    assert all(g.group != UNASSIGNED_LABEL for g in result.groups)


def test_excluded_subgroups_still_carry_their_full_breakdown(cfg_factory):
    """A subgroup below the floor is shown, not hidden — counts and all."""
    cfg = cfg_factory(**{"comparisons.min_subgroup_size": 10})
    answers, groups = _frame({"big": ["3"] * 20, "small": ["5", "5", "1"]})
    result, _ = compare_claim("CLM-TEST", answers, groups, "role", cfg)
    small = next(g for g in result.groups if g.group == "small")
    assert small.included is False
    assert small.frequencies == {1: 1, 2: 0, 3: 0, 4: 0, 5: 2}
    assert small.n_valid == 3
    assert small.rank_sum is None      # never ranked: it did not enter the test


def test_included_group_rank_sums_total_the_pooled_rank_sum(cfg_factory):
    cfg = cfg_factory(**{"comparisons.min_subgroup_size": 10})
    answers, groups = _frame({"a": ["2"] * 20 + ["4"] * 10,
                              "b": ["3"] * 15 + ["5"] * 15})
    result, _ = compare_claim("CLM-TEST", answers, groups, "role", cfg)
    included = [g for g in result.groups if g.included]
    n = sum(g.n_valid for g in included)
    assert sum(g.rank_sum for g in included) == pytest.approx(n * (n + 1) / 2)
    for g in included:
        assert g.mean_rank == pytest.approx(g.rank_sum / g.n_valid)


# ---------------------------------------------------------------------------
# BH detail shown on the page
# ---------------------------------------------------------------------------

def test_bh_detail_names_the_family_and_shows_the_critical_value(cfg):
    from rq3.analysis.comparisons import ComparisonResult
    results = [ComparisonResult(claim_id=f"C{i}", variable="industry",
                                test="mann_whitney_u", statistic=1.0, p_value=p)
               for i, p in enumerate([0.001, 0.02, 0.5, 0.9])]
    apply_bh(results, cfg)

    smallest = results[0]
    assert smallest.bh.family == "industry"
    assert smallest.bh.family_size == 4
    assert smallest.bh.rank_in_family == 1
    # BH critical value for rank j in a family of m at alpha: (j/m)·alpha
    assert smallest.bh.critical_value == pytest.approx(1 / 4 * 0.05)
    assert smallest.bh.raw_p == 0.001
    assert smallest.bh.p_adjusted == pytest.approx(smallest.p_adjusted)
    assert smallest.bh.significant is smallest.significant_adjusted

    assert results[3].bh.rank_in_family == 4
    assert results[3].bh.critical_value == pytest.approx(0.05)


def test_bh_detail_ranks_are_a_permutation_of_the_family(cfg):
    from rq3.analysis.comparisons import ComparisonResult
    results = [ComparisonResult(claim_id=f"C{i}", variable="role",
                                test="mann_whitney_u", statistic=1.0, p_value=p)
               for i, p in enumerate([0.4, 0.01, 0.9, 0.05, 0.2])]
    apply_bh(results, cfg)
    assert sorted(r.bh.rank_in_family for r in results) == [1, 2, 3, 4, 5]


# ---------------------------------------------------------------------------
# Bimodality: the observed values, not just the flag
# ---------------------------------------------------------------------------

def test_bimodality_assessment_exposes_every_observed_value(cfg):
    s = pd.Series(["1"] * 20 + ["2"] * 20 + ["3"] * 20 + ["4"] * 20 + ["5"] * 20)
    b = describe_claim("CLM-TEST", s, cfg).bimodality
    assert b.assessed is True
    assert b.n_valid == 100
    assert b.lower_tail_pct == pytest.approx(40.0)
    assert b.middle_pct == pytest.approx(20.0)
    assert b.upper_tail_pct == pytest.approx(40.0)
    assert b.flag is True
    names = [c.name for c in b.checks]
    assert "lower tail (answers 1-2)" in names
    assert "Sarle's bimodality coefficient" in names
    heuristic = [c for c in b.checks if not c.name.startswith("Sarle")]
    assert all(c.passed for c in heuristic)
    for c in b.checks:
        assert c.comparator in {">=", "<=", ">"}


def test_bimodality_checks_report_the_failing_condition(cfg):
    # Same tails, heavier middle -> the middle check is the one that fails.
    s = pd.Series(["1"] * 30 + ["2"] * 10 + ["3"] * 25 + ["4"] * 10 + ["5"] * 25)
    b = describe_claim("CLM-TEST", s, cfg).bimodality
    assert b.flag is False
    failing = [c.name for c in b.checks[:3] if not c.passed]
    assert failing == ["middle (answer 3)"]
    middle = next(c for c in b.checks if c.name == "middle (answer 3)")
    assert middle.observed == pytest.approx(25.0)
    assert middle.threshold == pytest.approx(20.0)


def test_bimodality_not_assessed_is_stated_explicitly(cfg):
    b = describe_claim("CLM-TEST", pd.Series(["1"] * 5 + ["5"] * 5), cfg).bimodality
    assert b.assessed is False
    assert b.checks == []
    assert "not assessed" in b.reason


# ---------------------------------------------------------------------------
# High-IDK flag
# ---------------------------------------------------------------------------

def test_high_idk_flag_uses_the_configured_threshold(cfg):
    # 30 IDK of 100 respondents = 30% >= the 25% default.
    s = pd.Series(["4"] * 70 + ["IDK"] * 30)
    d = describe_claim("CLM-TEST", s, cfg)
    assert d.high_idk is True
    assert d.high_idk_threshold_pct == pytest.approx(25.0)

    s = pd.Series(["4"] * 90 + ["IDK"] * 10)
    assert describe_claim("CLM-TEST", s, cfg).high_idk is False


def test_high_idk_threshold_is_configurable(cfg_factory):
    cfg = cfg_factory(**{"descriptives.high_idk_rate_pct": 50.0})
    s = pd.Series(["4"] * 70 + ["IDK"] * 30)
    assert describe_claim("CLM-TEST", s, cfg).high_idk is False
