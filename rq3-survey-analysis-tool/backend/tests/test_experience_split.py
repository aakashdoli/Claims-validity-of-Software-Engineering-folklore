"""The two-group experience comparison.

The split is at ten years because that is the only band boundary the survey
data offers. These tests pin that: no five-year cut exists anywhere, and the
bands are combined exactly as specified.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from rq3.analysis.experience import assign_groups, compare

BANDS = ["Less than 1 year", "1 to 3 years", "4 to 9 years", "10+ years"]


def _responses(rows: list[tuple[str, list[str]]], claim_ids: list[str]) -> pd.DataFrame:
    """rows = (experience band, answers for each claim)"""
    return pd.DataFrame([
        {"respondent_id": f"R{i:04d}", "experience": band, "role": "Developer",
         **dict(zip(claim_ids, answers))}
        for i, (band, answers) in enumerate(rows)
    ])


# ---------------------------------------------------------------------------
# The split itself
# ---------------------------------------------------------------------------

def test_the_three_lower_bands_combine_into_group_1(cfg):
    exp = pd.Series(BANDS)
    got = assign_groups(exp, cfg)
    assert list(got) == ["Under 10 years", "Under 10 years", "Under 10 years",
                         "10+ years"]


def test_no_five_year_cut_exists_anywhere_in_the_config(cfg):
    """A 5-year split is impossible: no band boundary falls there."""
    spec = cfg.get("experience_split")
    bands = spec["group_1"]["bands"] + spec["group_2"]["bands"]
    assert bands == BANDS
    # "4 to 9 years" straddles five, so it cannot be divided.
    assert "4 to 9 years" in spec["group_1"]["bands"]
    assert not any("5" in b for b in bands)


def test_unknown_band_is_left_unassigned_not_guessed(cfg):
    got = assign_groups(pd.Series(["10+ years", "Sabbatical", None]), cfg)
    assert got.iloc[0] == "10+ years"
    assert pd.isna(got.iloc[1]) or got.iloc[1] is None
    assert pd.isna(got.iloc[2]) or got.iloc[2] is None


def test_group_sizes_match_the_real_survey(cfg):
    """153 under ten years, 598 at ten or more — the expected split."""
    from rq3.claims import load_claims
    from rq3.decode import decode_export
    src = cfg.resolve_path("dataset.input_file")
    if not src.exists():
        pytest.skip("configured export not present")
    decoded = decode_export(src, load_claims(cfg), cfg)
    got = assign_groups(decoded.responses["experience"], cfg)
    assert len(got) == 751
    assert int((got == "Under 10 years").sum()) == 153
    assert int((got == "10+ years").sum()) == 598


# ---------------------------------------------------------------------------
# The test itself
# ---------------------------------------------------------------------------

def test_mann_whitney_matches_scipy_on_the_two_groups(cfg):
    claim = "CLM-000001"
    rows = ([("4 to 9 years", ["2"]) for _ in range(30)]
            + [("10+ years", ["5"]) for _ in range(40)])
    fam = compare(_responses(rows, [claim]), [claim], cfg)
    r = fam.results[0]
    expected = stats.mannwhitneyu(np.full(30, 2.0), np.full(40, 5.0),
                                  alternative="two-sided", method="asymptotic")
    assert r.group_1_n == 30 and r.group_2_n == 40
    assert r.u_statistic == pytest.approx(expected.statistic)
    assert r.p_raw == pytest.approx(expected.pvalue)


def test_idk_is_excluded_from_the_ranked_data(cfg):
    claim = "CLM-000001"
    rows = ([("1 to 3 years", ["2"]) for _ in range(20)]
            + [("1 to 3 years", ["IDK"]) for _ in range(15)]
            + [("10+ years", ["4"]) for _ in range(25)]
            + [("10+ years", ["IDK"]) for _ in range(30)])
    r = compare(_responses(rows, [claim]), [claim], cfg).results[0]
    assert r.group_1_n == 20 and r.group_1_idk == 15
    assert r.group_2_n == 25 and r.group_2_idk == 30


def test_a_group_below_the_size_floor_is_not_tested(cfg):
    claim = "CLM-000001"
    rows = ([("1 to 3 years", ["3"]) for _ in range(5)]
            + [("10+ years", ["4"]) for _ in range(40)])
    r = compare(_responses(rows, [claim]), [claim], cfg).results[0]
    assert r.tested is False
    assert r.p_raw is None
    assert "below the minimum" in r.reason


# ---------------------------------------------------------------------------
# One BH family of 50, and effect size only where it survives
# ---------------------------------------------------------------------------

def _family(cfg, n_claims: int = 50, n_different: int = 3):
    claims = [f"CLM-{i:06d}" for i in range(n_claims)]
    rng = np.random.default_rng(7)
    rows = []
    for band, n in (("4 to 9 years", 60), ("10+ years", 60)):
        for _ in range(n):
            answers = []
            for j in range(n_claims):
                if j < n_different:
                    answers.append("5" if band == "10+ years" else "1")
                else:
                    answers.append(str(rng.integers(1, 6)))
            rows.append((band, answers))
    return compare(_responses(rows, claims), claims, cfg)


def test_one_bh_family_across_all_fifty_claims(cfg):
    fam = _family(cfg)
    assert len(fam.results) == 50
    assert fam.n_tested == 50
    assert fam.method == "fdr_bh"
    # Every tested claim gets a corrected p; none is left raw-only.
    assert all(r.p_corrected is not None for r in fam.results if r.tested)


def test_effect_size_only_where_the_corrected_p_survives(cfg):
    fam = _family(cfg)
    for r in fam.results:
        if r.significant_after_correction:
            assert r.effect is not None, f"{r.claim_id} significant but no effect size"
            assert r.effect.formula.startswith("Kerby")
        else:
            assert r.effect is None, f"{r.claim_id} not significant but carries an effect size"


def test_significance_is_judged_on_the_corrected_p_not_the_raw_one(cfg):
    fam = _family(cfg)
    for r in fam.results:
        if r.p_corrected is None:
            continue
        assert r.significant_after_correction == (r.p_corrected <= fam.alpha)
    assert fam.n_significant_corrected <= fam.n_significant_raw
