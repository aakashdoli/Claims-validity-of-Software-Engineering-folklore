"""The 10-respondent worked example, hand-calculated end to end.

This is the fixture that was validated by hand against the survey plan:

    junior = [1, 1, 1, 1, 5]      senior = [2, 5, 5, 5, 5]

    pooled sorted: 1 1 1 1 2 5 5 5 5 5   -> median = (2 + 5) / 2 = 3.5
    pooled ranks:  1..4 tie -> 2.5 each; 2 -> rank 5; 5x5 tie -> 8 each
    junior rank sum = 4(2.5) + 8            = 18
    senior rank sum = 5 + 4(8)              = 37     (18 + 37 = 55 = sum 1..10)

    cross-group pairs = 5 x 5 = 25
      favourable   (junior > senior): 5 vs 2                  ->  1
      tied         (junior = senior): 5 vs 5,5,5,5            ->  4
      unfavourable (junior < senior): the rest                -> 20
      U_junior = favourable + tied/2 = 1 + 2                  =  3
      r = f - u = (1 + 2)/25 - (20 + 2)/25 = 0.12 - 0.88      = -0.76

Every number below is checked against those hand calculations, not against
whatever the code happens to return.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from rq3.analysis.comparisons import compare_claim
from rq3.analysis.descriptives import describe_claim, valid_scores
from rq3.analysis.effects import rank_biserial, rank_biserial_from_u

JUNIOR = [1, 1, 1, 1, 5]
SENIOR = [2, 5, 5, 5, 5]

EXPECTED_MEDIAN = 3.5
EXPECTED_JUNIOR_RANK_SUM = 18.0
EXPECTED_SENIOR_RANK_SUM = 37.0
EXPECTED_U = 3.0
EXPECTED_R = -0.76
EXPECTED_FAVOURABLE = 1.0
EXPECTED_TIED = 4.0
EXPECTED_UNFAVOURABLE = 20.0


@pytest.fixture
def frame() -> pd.DataFrame:
    return pd.DataFrame({
        "answer": [str(v) for v in JUNIOR + SENIOR],
        "group": ["junior"] * 5 + ["senior"] * 5,
    })


def test_pooled_median_is_3_5(frame):
    assert float(np.median(valid_scores(frame["answer"]))) == EXPECTED_MEDIAN


def test_rank_sums_match_hand_calculation(frame):
    ranks = stats.rankdata(valid_scores(frame["answer"]))
    assert ranks[:5].sum() == pytest.approx(EXPECTED_JUNIOR_RANK_SUM)
    assert ranks[5:].sum() == pytest.approx(EXPECTED_SENIOR_RANK_SUM)
    assert ranks.sum() == pytest.approx(55.0)  # sum 1..10


def test_mann_whitney_u_matches_hand_calculation():
    res = stats.mannwhitneyu(JUNIOR, SENIOR, alternative="two-sided",
                             method="asymptotic")
    assert res.statistic == pytest.approx(EXPECTED_U)


def test_rank_biserial_pair_counts_and_r(cfg):
    e = rank_biserial(np.array(JUNIOR, dtype=float), np.array(SENIOR, dtype=float), cfg)
    assert e.favourable_pairs == EXPECTED_FAVOURABLE
    assert e.tied_pairs == EXPECTED_TIED
    assert e.unfavourable_pairs == EXPECTED_UNFAVOURABLE
    assert e.total_pairs == 25
    assert e.r == pytest.approx(EXPECTED_R)
    assert e.magnitude == "large"          # |−0.76| > Romano large cut-off 0.47
    assert e.direction == "higher in second group"


def test_rank_biserial_agrees_with_u_identity(cfg):
    """Kerby's simple difference == 2U/(n1 n2) - 1. Two routes, one answer."""
    e = rank_biserial(np.array(JUNIOR, dtype=float), np.array(SENIOR, dtype=float), cfg)
    from_u = rank_biserial_from_u(EXPECTED_U, len(JUNIOR), len(SENIOR), cfg)
    assert e.r == pytest.approx(from_u)


def test_rank_biserial_matches_brute_force_enumeration(cfg):
    """Cross-check the frequency-table shortcut against explicit pair counting."""
    rng = np.random.default_rng(20260815)
    for _ in range(50):
        a = rng.integers(1, 6, size=int(rng.integers(5, 40))).astype(float)
        b = rng.integers(1, 6, size=int(rng.integers(5, 40))).astype(float)
        fav = sum(1 for x in a for y in b if x > y)
        unf = sum(1 for x in a for y in b if x < y)
        tie = a.size * b.size - fav - unf
        e = rank_biserial(a, b, cfg)
        assert e.favourable_pairs == fav
        assert e.unfavourable_pairs == unf
        assert e.tied_pairs == tie
        assert e.r == pytest.approx((fav - unf) / (a.size * b.size))


def test_full_comparison_reproduces_the_worked_example(cfg_factory, frame):
    """The pipeline's own entry point, not just the helpers."""
    cfg = cfg_factory(**{"comparisons.min_subgroup_size": 5})
    result, exclusions = compare_claim("CLM-TEST", frame["answer"], frame["group"],
                                       "experience", cfg)
    assert result.test == "mann_whitney_u"
    assert result.statistic == pytest.approx(EXPECTED_U)
    assert result.effect.r == pytest.approx(EXPECTED_R)
    assert not exclusions
    ranks = {g.group: g.mean_rank for g in result.groups}
    assert ranks["junior"] * 5 == pytest.approx(EXPECTED_JUNIOR_RANK_SUM)
    assert ranks["senior"] * 5 == pytest.approx(EXPECTED_SENIOR_RANK_SUM)


def test_descriptives_of_the_worked_example(cfg, frame):
    d = describe_claim("CLM-TEST", frame["answer"], cfg)
    assert d.n_total == 10
    assert d.n_valid == 10
    assert d.n_idk == 0
    assert d.median == EXPECTED_MEDIAN
    assert d.frequencies == {1: 4, 2: 1, 3: 0, 4: 0, 5: 5}
    assert d.mode == [5]
    assert d.disagree_pct == pytest.approx(50.0)   # four 1s + one 2
    assert d.neutral_pct == pytest.approx(0.0)
    assert d.agree_pct == pytest.approx(50.0)      # five 5s
