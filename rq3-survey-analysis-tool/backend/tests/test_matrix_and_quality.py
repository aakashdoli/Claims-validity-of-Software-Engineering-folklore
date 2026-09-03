"""Stage 5 (belief-evidence matrix), Stage 6 (comments) and quality screening."""

from __future__ import annotations

import pandas as pd
import pytest

from rq3.analysis.buckets import (CLEAR_DIRECTION, IDK_DOMINANT, MIXED,
                                  classify_all)
from rq3.analysis.comments import collect_comments
from rq3.analysis.descriptives import describe_claim
from rq3.analysis.matrix import (MAJORITY_AGREED, MAJORITY_DISAGREED,
                                 build_matrix)


def _claims(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame([
        {"q_number": i + 1, "claim_id": cid, "claim_type": "NORMATIVE",
         "book": "b", "source_text": "s",
         "evidence_label": label, "evidence_strength": "", "evidence_notes": ""}
        for i, (cid, label) in enumerate(rows)
    ])


def _series(counts: dict[str, int]) -> pd.Series:
    out: list[str] = []
    for value, n in counts.items():
        out.extend([value] * n)
    return pd.Series(out)


def _matrix(specs: list[tuple[str, dict[str, int], str]], cfg):
    """specs = (claim_id, answer counts, evidence label)"""
    ds = [describe_claim(cid, _series(counts), cfg) for cid, counts, _ in specs]
    claims = _claims([(cid, label) for cid, _, label in specs])
    return build_matrix(classify_all(ds, cfg), claims, cfg)


AGREE = {"4": 70, "1": 30}       # 70% agree  -> Majority agreed
DISAGREE = {"1": 70, "4": 30}    # 70% disagree -> Majority disagreed
NO_MAJORITY = {"4": 45, "1": 45, "3": 10}
IDK_HEAVY = {"4": 60, "IDK": 40}  # 40% of full sample -> idk_dominant


# ---------------------------------------------------------------------------
# Only clear_direction claims enter the matrix
# ---------------------------------------------------------------------------

def test_the_matrix_is_two_by_three(cfg):
    m = _matrix([("C1", AGREE, "SUPPORTED"), ("C2", DISAGREE, "CONTRADICTED"),
                 ("C3", AGREE, "NO EVIDENCE FOUND")], cfg)
    assert m.belief_classes == [MAJORITY_AGREED, MAJORITY_DISAGREED]
    assert m.evidence_labels == ["SUPPORTED", "CONTRADICTED", "NO EVIDENCE FOUND"]


@pytest.mark.parametrize("counts,label,expected", [
    (AGREE, "CONTRADICTED", "mismatch"),
    (DISAGREE, "SUPPORTED", "mismatch"),
    (AGREE, "SUPPORTED", "match"),
    (DISAGREE, "CONTRADICTED", "match"),
    (AGREE, "NO EVIDENCE FOUND", "not_scored"),
    (DISAGREE, "NO EVIDENCE FOUND", "not_scored"),
])
def test_verdict_rules(cfg, counts, label, expected):
    k = _matrix([("C1", counts, label)], cfg).classifications[0]
    assert k.verdict_status == expected
    assert k.mismatch is (expected == "mismatch")


def test_mixed_and_idk_dominant_are_excluded_from_the_grid(cfg):
    m = _matrix([("C1", AGREE, "SUPPORTED"),
                 ("C2", NO_MAJORITY, "CONTRADICTED"),
                 ("C3", IDK_HEAVY, "SUPPORTED")], cfg)
    assert m.bucket_counts == {CLEAR_DIRECTION: 1, MIXED: 1, IDK_DOMINANT: 1}
    placed = [cid for c in m.cells for cid in c.claim_ids]
    assert placed == ["C1"]
    assert m.excluded_mixed == ["C2"]
    assert m.excluded_idk_dominant == ["C3"]
    # Excluded, but still reported — never dropped.
    assert {c.claim_id for c in m.classifications} == {"C1", "C2", "C3"}
    assert all(c.verdict_status == "excluded" for c in m.classifications
               if not c.in_matrix)


def test_excluded_claims_carry_a_reason(cfg):
    m = _matrix([("C1", NO_MAJORITY, "SUPPORTED"),
                 ("C2", IDK_HEAVY, "SUPPORTED")], cfg)
    by_id = {c.claim_id: c for c in m.classifications}
    assert "NO MAJORITY" in by_id["C1"].verdict
    assert "NOT CLASSIFIED" in by_id["C2"].verdict
    assert "don't know" in by_id["C2"].verdict


def test_no_evidence_found_is_excluded_from_the_scoring_counts(cfg):
    m = _matrix([("C1", AGREE, "SUPPORTED"),        # match
                 ("C2", DISAGREE, "SUPPORTED"),     # mismatch
                 ("C3", AGREE, "NO EVIDENCE FOUND"),
                 ("C4", DISAGREE, "NO EVIDENCE FOUND")], cfg)
    assert (m.n_match, m.n_mismatch, m.n_not_scored, m.n_scored) == (1, 1, 2, 2)
    cells = [c for c in m.cells if c.evidence_label == "NO EVIDENCE FOUND"]
    assert sorted(i for c in cells for i in c.claim_ids) == ["C3", "C4"]


def test_percentages_reach_the_classification(cfg):
    k = _matrix([("C1", AGREE, "SUPPORTED")], cfg).classifications[0]
    assert k.pct_agree == pytest.approx(0.70)
    assert k.pct_disagree == pytest.approx(0.30)
    assert k.directional_n == 100
    assert k.belief_label == MAJORITY_AGREED
    assert "70%" in k.verdict


def test_strength_qualifier_travels_without_changing_the_verdict(cfg):
    claims = _claims([("C1", "SUPPORTED")])
    claims["evidence_strength"] = "weak evidence"
    ds = [describe_claim("C1", _series(DISAGREE), cfg)]
    k = build_matrix(classify_all(ds, cfg), claims, cfg).classifications[0]
    assert k.evidence_strength == "weak evidence"
    assert k.verdict_status == "mismatch"
    assert "weak evidence" in k.verdict


def test_pending_only_appears_when_a_matrix_claim_needs_it(cfg):
    labelled = _matrix([("C1", AGREE, "SUPPORTED")], cfg)
    assert "PENDING" not in labelled.evidence_labels
    unlabelled = _matrix([("C1", AGREE, "PENDING")], cfg)
    assert unlabelled.evidence_labels[-1] == "PENDING"
    assert unlabelled.n_pending_evidence == 1


def test_every_claim_appears_once_or_is_explicitly_excluded(cfg):
    m = _matrix([("C1", AGREE, "SUPPORTED"), ("C2", DISAGREE, "CONTRADICTED"),
                 ("C3", NO_MAJORITY, "SUPPORTED"), ("C4", IDK_HEAVY, "SUPPORTED")], cfg)
    placed = [cid for c in m.cells for cid in c.claim_ids]
    assert sorted(placed) == ["C1", "C2"]
    assert len(placed) == len(set(placed))
    excluded = set(m.excluded_mixed) | set(m.excluded_idk_dominant)
    assert sorted(set(placed) | excluded) == ["C1", "C2", "C3", "C4"]


# ---------------------------------------------------------------------------
# Stage 6 — comment prioritisation
# ---------------------------------------------------------------------------

def test_comment_priority_ranks_the_interesting_claims_first(cfg):
    split = _series({"1": 30, "2": 30, "3": 10, "4": 30, "5": 30})
    plain = _series({"4": 130})
    ds = [describe_claim("C_PLAIN", plain, cfg), describe_claim("C_SPLIT", split, cfg)]
    claims = _claims([("C_PLAIN", "SUPPORTED"), ("C_SPLIT", "SUPPORTED")])
    m = build_matrix(classify_all(ds, cfg), claims, cfg)
    comments = pd.DataFrame([
        {"respondent_id": "R1", "claim_id": "C_SPLIT", "answer": "1", "comment": "depends"},
        {"respondent_id": "R2", "claim_id": "C_PLAIN", "answer": "4", "comment": "sure"},
    ])
    out = collect_comments(comments, ds, [], m, cfg)
    assert out[0].claim_id == "C_SPLIT"
    assert out[0].priority_score > out[1].priority_score


def test_claims_without_comments_still_appear(cfg):
    ds = [describe_claim("C1", _series({"4": 100}), cfg)]
    m = build_matrix(classify_all(ds, cfg), _claims([("C1", "SUPPORTED")]), cfg)
    out = collect_comments(pd.DataFrame(
        columns=["respondent_id", "claim_id", "answer", "comment"]), ds, [], m, cfg)
    assert len(out) == 1 and out[0].n_comments == 0


# ---------------------------------------------------------------------------
# Quality screening
# ---------------------------------------------------------------------------

def _decoded(rows: list[dict], claim_ids: list[str]):
    from rq3.decode import DecodedSurvey
    from pathlib import Path
    return DecodedSurvey(
        source_file=Path("test.xlsx"),
        responses=pd.DataFrame(rows),
        comments=pd.DataFrame(columns=["respondent_id", "claim_id", "answer", "comment"]),
        claim_columns=claim_ids,
        demographic_columns=["role"],
        survey_text={c: "" for c in claim_ids},
        consent_column="VAR00_1",
        duration_column=None,
    )


def test_straightliner_is_flagged_not_excluded(cfg):
    from rq3.quality import screen
    claim_ids = [f"C{i}" for i in range(50)]
    rows = [
        {"respondent_id": "R1", "consented": True, "role": "Developer",
         **{c: "IDK" for c in claim_ids}},
        {"respondent_id": "R2", "consented": True, "role": "Developer",
         **{c: str((i % 5) + 1) for i, c in enumerate(claim_ids)}},
    ]
    report = screen(_decoded(rows, claim_ids), cfg)
    assert report.n_respondents == 2          # nothing removed
    assert report.n_flagged == 1
    flagged = report.flagged[0]
    assert flagged.respondent_id == "R1"
    assert flagged.distinct_values == 1
    assert any("straightlining" in f for f in flagged.flags)


def test_speeding_check_reports_unavailable_when_no_duration_column(cfg):
    from rq3.quality import screen
    claim_ids = ["C0"]
    rows = [{"respondent_id": "R1", "consented": True, "role": "Developer", "C0": "3"}]
    report = screen(_decoded(rows, claim_ids), cfg)
    assert report.speeding_check.startswith("unavailable")


def test_duplicate_answer_patterns_are_detected(cfg):
    from rq3.quality import screen
    claim_ids = [f"C{i}" for i in range(10)]
    pattern = {c: str((i % 4) + 1) for i, c in enumerate(claim_ids)}
    rows = [{"respondent_id": f"R{n}", "consented": True, "role": "Developer", **pattern}
            for n in range(2)]
    report = screen(_decoded(rows, claim_ids), cfg)
    assert report.duplicate_pattern_groups == [["R0", "R1"]]


def test_modal_dominance_flag(cfg):
    from rq3.quality import screen
    claim_ids = [f"C{i}" for i in range(50)]
    answers = {c: "4" for c in claim_ids}
    answers["C0"] = "2"          # 49/50 = 98% on one value, 2 distinct values
    rows = [{"respondent_id": "R1", "consented": True, "role": "Developer", **answers}]
    report = screen(_decoded(rows, claim_ids), cfg)
    assert any("modal dominance" in f for f in report.flagged[0].flags)
