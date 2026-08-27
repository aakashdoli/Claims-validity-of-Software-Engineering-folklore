"""Integration tests against the real BTHSurvey export.

These assert the properties the thesis depends on: the decoding is faithful to
the raw file, the run is deterministic, and nothing is ever silently dropped.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from rq3.claims import load_claims
from rq3.decode import decode_export
from rq3.pipeline import (comparisons_table, export_all, matrix_table,
                          results_table, run)


@pytest.fixture(scope="module")
def decoded_real(request):
    from rq3.config import load_config
    from tests.conftest import REAL_EXPORT
    if not REAL_EXPORT.exists():
        pytest.skip("real export not present")
    cfg = load_config()
    return decode_export(REAL_EXPORT, load_claims(cfg), cfg), cfg


@pytest.fixture(scope="module")
def run_real(request):
    from rq3.config import load_config
    from tests.conftest import REAL_EXPORT
    if not REAL_EXPORT.exists():
        pytest.skip("real export not present")
    cfg = load_config()
    return run(cfg, input_file=REAL_EXPORT), cfg


# ---------------------------------------------------------------------------
# Decoding fidelity
# ---------------------------------------------------------------------------

def test_decoded_row_count_matches_the_raw_sheet(decoded_real, real_export):
    decoded, _ = decoded_real
    raw = pd.read_excel(real_export, sheet_name="Data")
    assert decoded.responses.shape[0] == raw.shape[0]
    assert decoded.responses["respondent_id"].nunique() == raw.shape[0]


def test_every_claim_column_holds_only_known_values(decoded_real):
    decoded, cfg = decoded_real
    allowed = {str(v) for v in cfg.likert_values} | {"IDK"}
    for cid in decoded.claim_columns:
        values = set(decoded.responses[cid].dropna().astype(str))
        assert values <= allowed, f"{cid} has unexpected values {values - allowed}"


def test_answer_counts_match_the_raw_codes(decoded_real, real_export):
    """Decoding must not shift a single answer."""
    decoded, cfg = decoded_real
    raw = pd.read_excel(real_export, sheet_name="Data")
    raw_vars = [c for c in raw.columns if c.startswith("VAR")
                and c[3:].isdigit() and 1 <= int(c[3:]) <= len(decoded.claim_columns)]
    for cid, var in zip(decoded.claim_columns, sorted(raw_vars)):
        for code in cfg.likert_values:
            assert (decoded.responses[cid] == str(code)).sum() == (raw[var] == code).sum()
        assert (decoded.responses[cid] == "IDK").sum() == (raw[var] == cfg.idk_code).sum()


def test_country_dummies_collapse_to_one_selection(decoded_real, real_export):
    decoded, cfg = decoded_real
    raw = pd.read_excel(real_export, sheet_name="Data")
    dummies = [c for c in raw.columns if c.startswith("VAR56_")]
    selected = (raw[dummies] == 1).sum(axis=1)
    assert (selected <= 1).all(), "a respondent picked more than one country"
    assert decoded.responses["country"].notna().sum() == int((selected == 1).sum())


def test_missing_code_becomes_missing_not_a_category(decoded_real, real_export):
    decoded, cfg = decoded_real
    raw = pd.read_excel(real_export, sheet_name="Data")
    # VAR55 (company size) carries 999s in this export.
    assert (raw["VAR55"] == cfg.missing_code).sum() > 0
    assert decoded.responses["company_size"].isna().sum() == int(
        (raw["VAR55"] == cfg.missing_code).sum())
    assert not any(str(cfg.missing_code) in str(v)
                   for v in decoded.responses["company_size"].dropna().unique())


def test_demographic_columns_are_named_not_var_codes(decoded_real):
    decoded, _ = decoded_real
    assert set(decoded.demographic_columns) == {
        "experience", "role", "team_size", "industry", "company_size", "country"}


def test_survey_wording_is_captured_for_every_claim(decoded_real):
    decoded, _ = decoded_real
    assert len(decoded.survey_text) == len(decoded.claim_columns)
    assert all(len(t) > 20 for t in decoded.survey_text.values())


def test_decoder_refuses_a_claim_count_mismatch(decoded_real, real_export):
    """Guard against a re-export silently mapping to the wrong claim IDs."""
    from rq3.decode import DecodeError
    decoded, cfg = decoded_real
    truncated = load_claims(cfg).iloc[:10]
    with pytest.raises(DecodeError, match="Refusing to guess"):
        decode_export(real_export, truncated, cfg)


# ---------------------------------------------------------------------------
# Completeness — nothing silently missing
# ---------------------------------------------------------------------------

def test_every_claim_has_descriptives(run_real):
    result, _ = run_real
    assert len(result.descriptives) == len(result.claims)
    assert {d.claim_id for d in result.descriptives} == set(result.claims["claim_id"])


def test_every_claim_x_variable_pair_is_present(run_real):
    result, cfg = run_real
    variables = [v for v in cfg.get("comparisons.variables")]
    expected = {(c, v) for c in result.claims["claim_id"] for v in variables}
    actual = {(c.claim_id, c.variable) for c in result.comparisons}
    assert actual == expected


def test_every_comparison_either_has_a_p_value_or_a_reason(run_real):
    result, _ = run_real
    for c in result.comparisons:
        if c.p_value is None:
            assert c.excluded and c.exclusion_reason, f"{c.claim_id}/{c.variable}"
        else:
            assert c.p_adjusted is not None
            assert c.significant_adjusted is not None


def test_every_tested_comparison_has_an_effect_size(run_real):
    result, _ = run_real
    for c in result.comparisons:
        if c.p_value is None:
            continue
        assert (c.effect is not None) or (c.omnibus_effect is not None)


def test_every_claim_is_placed_in_the_matrix(run_real):
    result, _ = run_real
    placed = [cid for cell in result.matrix.cells for cid in cell.claim_ids]
    assert sorted(placed) == sorted(result.claims["claim_id"])


def test_every_excluded_subgroup_is_logged(run_real):
    """Both exclusion kinds are logged, each under its own scope."""
    result, _ = run_real
    by_scope = {"below_min_size": "subgroup", "unassigned": "unassigned"}
    logged = {(e.scope, e.claim_id, e.variable, e.group) for e in result.exclusions}
    for c in result.comparisons:
        for g in c.groups:
            if g.included:
                continue
            assert g.excluded_kind in by_scope, f"{c.claim_id}/{c.variable}/{g.group}"
            key = (by_scope[g.excluded_kind], c.claim_id, c.variable, g.group)
            assert key in logged


def test_subgroup_counts_reconcile_with_the_overall_counts(run_real, cfg):
    """The reconciliation the claim page asserts must hold for every claim.

    Demographics were optional, so respondents who skipped one are carried as
    an explicit "(not recorded)" row rather than dropped — otherwise the
    subgroup totals would fall short of the overall totals on 5 of the 6
    variables and the page's own arithmetic would not add up.
    """
    result, _ = run_real
    overall = {d.claim_id: d for d in result.descriptives}
    for c in result.comparisons:
        if not c.groups:
            continue
        o = overall[c.claim_id]
        for point in cfg.likert_values:
            assert sum(g.frequencies[point] for g in c.groups) == o.frequencies[point], \
                f"{c.claim_id}/{c.variable} disagrees on answer {point}"
        assert sum(g.n_idk for g in c.groups) == o.n_idk
        assert sum(g.n_total for g in c.groups) == o.n_total
        assert sum(g.n_valid for g in c.groups) == o.n_valid


def test_unassigned_rows_never_enter_a_test(run_real):
    from rq3.analysis.comparisons import UNASSIGNED_LABEL
    result, _ = run_real
    for c in result.comparisons:
        for g in c.groups:
            if g.group == UNASSIGNED_LABEL:
                assert g.included is False
                assert g.rank_sum is None


def test_pairwise_only_runs_after_a_significant_omnibus(run_real):
    result, cfg = run_real
    if not bool(cfg.get("comparisons.pairwise_requires_significant_omnibus")):
        pytest.skip("gate disabled in config")
    for c in result.comparisons:
        if c.pairwise:
            assert c.test == "kruskal_wallis"
            assert c.significant_adjusted is True


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------

def test_two_runs_produce_identical_numbers(real_export, cfg):
    a = run(cfg, input_file=real_export)
    b = run(cfg, input_file=real_export)
    assert results_table(a, cfg).equals(results_table(b, cfg))
    assert comparisons_table(a).equals(comparisons_table(b))
    assert matrix_table(a).equals(matrix_table(b))
    assert a.manifest.input_sha256 == b.manifest.input_sha256


def test_manifest_records_provenance(run_real):
    result, _ = run_real
    m = result.manifest
    assert len(m.input_sha256) == 64
    assert m.n_respondents > 0
    assert m.n_claims == 50
    assert m.config["belief"]["threshold"] == 3.5
    assert m.library_versions["scipy"]
    assert m.run_id.endswith(m.input_sha256[:8])


def test_exports_carry_the_caveats_and_are_readable(run_real, tmp_path):
    result, cfg = run_real
    paths = export_all(result, cfg, out_dir=tmp_path)
    for name in ("claim_results.csv", "subgroup_comparisons.csv",
                 "belief_evidence_matrix.csv", "exclusions.csv"):
        text = open(paths[name], encoding="utf-8").read()
        assert "sampling_caveat" in text
        assert "input_sha256" in text
        assert not pd.read_csv(paths[name], comment="#").empty
    full = json.loads(open(paths["full_run.json"], encoding="utf-8").read())
    assert full["manifest"]["config"]["comparisons"]["min_subgroup_size"] == 10
    assert full["caveats"]["sampling_caveat"]
    assert len(full["descriptives"]) == 50


def test_results_table_has_one_row_per_claim(run_real):
    result, cfg = run_real
    table = results_table(result, cfg)
    assert len(table) == 50
    assert table["q_number"].tolist() == list(range(1, 51))
    assert table["claim_id"].is_unique
