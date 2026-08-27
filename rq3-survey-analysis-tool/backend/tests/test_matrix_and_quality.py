"""Stage 5 (belief-evidence matrix), Stage 6 (comments) and quality screening."""

from __future__ import annotations

import pandas as pd
import pytest

from rq3.analysis.comments import collect_comments
from rq3.analysis.descriptives import describe_claim
from rq3.analysis.matrix import (BELIEVED, NOT_BELIEVED, UNCLASSIFIED,
                                 build_matrix)


def _claims(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame([
        {"q_number": i + 1, "claim_id": cid, "claim_type": "NORMATIVE",
         "book": "b", "source_text": "s",
         "evidence_label": label, "evidence_notes": ""}
        for i, (cid, label) in enumerate(rows)
    ])


def _series(counts: dict[str, int]) -> pd.Series:
    out: list[str] = []
    for value, n in counts.items():
        out.extend([value] * n)
    return pd.Series(out)


# ---------------------------------------------------------------------------
# Belief classification
# ---------------------------------------------------------------------------

def test_threshold_is_read_from_config_only(cfg):
    assert cfg.belief_threshold == pytest.approx(3.5)


def test_median_at_the_threshold_counts_as_believed(cfg):
    # median exactly 3.5 -> ">= threshold" -> believed
    d = describe_claim("C1", _series({"3": 50, "4": 50}), cfg)
    assert d.median == pytest.approx(3.5)
    m = build_matrix([d], _claims([("C1", "SUPPORTED")]), cfg)
    assert m.classifications[0].belief_class == BELIEVED


def test_median_below_threshold_is_not_believed(cfg):
    d = describe_claim("C1", _series({"3": 60, "4": 40}), cfg)
    assert d.median == pytest.approx(3.0)
    m = build_matrix([d], _claims([("C1", "SUPPORTED")]), cfg)
    assert m.classifications[0].belief_class == NOT_BELIEVED


def test_changing_the_threshold_moves_the_classification(cfg_factory):
    cfg = cfg_factory(**{"belief.threshold": 4.0})
    d = describe_claim("C1", _series({"3": 50, "4": 50}), cfg)   # median 3.5
    m = build_matrix([d], _claims([("C1", "SUPPORTED")]), cfg)
    assert m.classifications[0].belief_class == NOT_BELIEVED
    assert m.threshold == 4.0


def test_borderline_claims_are_flagged_but_still_placed(cfg):
    # median 3.5, distance 0.0 <= borderline_delta 0.2
    d = describe_claim("C1", _series({"3": 50, "4": 50}), cfg)
    m = build_matrix([d], _claims([("C1", "CONTRADICTED")]), cfg)
    k = m.classifications[0]
    assert k.borderline is True
    assert k.belief_class == BELIEVED            # placed, not dropped
    cell = [c for c in m.cells
            if c.belief_class == BELIEVED and c.evidence_label == "CONTRADICTED"][0]
    assert cell.claim_ids == ["C1"]
    assert cell.borderline_claim_ids == ["C1"]   # and marked provisional
    assert m.n_borderline == 1


def test_claim_far_from_threshold_is_not_borderline(cfg):
    d = describe_claim("C1", _series({"5": 100}), cfg)           # median 5.0
    m = build_matrix([d], _claims([("C1", "SUPPORTED")]), cfg)
    assert m.classifications[0].borderline is False
    assert m.classifications[0].distance_from_threshold == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# Mismatch detection — the actual RQ3 finding
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("counts,label,expected", [
    # Scored cells — the four combinations that carry a verdict.
    ({"5": 100}, "CONTRADICTED", "mismatch"),   # believed, evidence says no
    ({"1": 100}, "SUPPORTED", "mismatch"),      # disbelieved, evidence says yes
    ({"5": 100}, "SUPPORTED", "match"),         # believed and supported
    ({"1": 100}, "CONTRADICTED", "match"),      # disbelieved and contradicted
    # NO EVIDENCE FOUND is outside the scoring in BOTH belief directions.
    ({"5": 100}, "NO EVIDENCE FOUND", "not_scored"),
    ({"1": 100}, "NO EVIDENCE FOUND", "not_scored"),
])
def test_verdict_rules(cfg, counts, label, expected):
    d = describe_claim("C1", _series(counts), cfg)
    k = build_matrix([d], _claims([("C1", label)]), cfg).classifications[0]
    assert k.verdict_status == expected
    assert k.mismatch is (expected == "mismatch")


def test_no_evidence_found_is_excluded_from_the_scoring_counts(cfg):
    """It gets its own bucket; it is never counted as a match or a mismatch."""
    ds = [describe_claim("C1", _series({"5": 100}), cfg),   # believed
          describe_claim("C2", _series({"1": 100}), cfg),   # not believed
          describe_claim("C3", _series({"5": 100}), cfg),   # believed
          describe_claim("C4", _series({"1": 100}), cfg)]   # not believed
    m = build_matrix(ds, _claims([("C1", "SUPPORTED"),          # match
                                  ("C2", "SUPPORTED"),          # mismatch
                                  ("C3", "NO EVIDENCE FOUND"),  # unscored
                                  ("C4", "NO EVIDENCE FOUND")]), cfg)
    assert m.n_match == 1
    assert m.n_mismatch == 1
    assert m.n_not_scored == 2
    assert m.n_scored == 2                      # the denominator to quote
    assert m.n_scored + m.n_not_scored == 4
    # Still placed in the grid — excluded from scoring, not from the matrix.
    cells = [c for c in m.cells if c.evidence_label == "NO EVIDENCE FOUND"]
    assert sorted(i for c in cells for i in c.claim_ids) == ["C3", "C4"]


def test_the_matrix_has_exactly_three_evidence_columns(cfg):
    ds = [describe_claim(f"C{i}", _series({"4": 100}), cfg) for i in range(3)]
    m = build_matrix(ds, _claims([("C0", "SUPPORTED"), ("C1", "CONTRADICTED"),
                                  ("C2", "NO EVIDENCE FOUND")]), cfg)
    assert m.evidence_labels == ["SUPPORTED", "CONTRADICTED", "NO EVIDENCE FOUND"]
    assert m.belief_classes == [BELIEVED, NOT_BELIEVED]


def test_pending_adds_a_fourth_column_only_when_present(cfg):
    ds = [describe_claim("C1", _series({"4": 100}), cfg)]
    labelled = build_matrix(ds, _claims([("C1", "SUPPORTED")]), cfg)
    assert "PENDING" not in labelled.evidence_labels
    unlabelled = build_matrix(ds, _claims([("C1", "PENDING")]), cfg)
    assert unlabelled.evidence_labels[-1] == "PENDING"


def test_strength_qualifier_travels_with_the_claim(cfg):
    claims = _claims([("C1", "SUPPORTED")])
    claims["evidence_strength"] = "weak evidence"
    d = describe_claim("C1", _series({"1": 100}), cfg)
    k = build_matrix([d], claims, cfg).classifications[0]
    assert k.evidence_strength == "weak evidence"
    # Scored exactly as plain SUPPORTED, but the qualifier is visible.
    assert k.verdict_status == "mismatch"
    assert "weak evidence" in k.verdict



# ---------------------------------------------------------------------------
# Unlabelled and unclassifiable claims are surfaced, never hidden
# ---------------------------------------------------------------------------

def test_pending_evidence_gets_its_own_column(cfg):
    d = describe_claim("C1", _series({"5": 100}), cfg)
    m = build_matrix([d], _claims([("C1", "PENDING")]), cfg)
    assert m.n_pending_evidence == 1
    assert "PENDING" in m.evidence_labels
    assert any("no RQ2 evidence label yet" in n for n in m.notes)


def test_claim_with_no_valid_answers_is_marked_unclassifiable(cfg):
    d = describe_claim("C1", pd.Series(["IDK"] * 50), cfg)
    m = build_matrix([d], _claims([("C1", "SUPPORTED")]), cfg)
    k = m.classifications[0]
    assert k.belief_class == UNCLASSIFIED
    assert k.median is None
    assert k.reason
    assert UNCLASSIFIED in m.belief_classes


def test_every_claim_appears_in_exactly_one_cell(cfg):
    ds = [describe_claim("C1", _series({"5": 100}), cfg),
          describe_claim("C2", _series({"1": 100}), cfg),
          describe_claim("C3", pd.Series(["IDK"] * 50), cfg)]
    m = build_matrix(ds, _claims([("C1", "SUPPORTED"), ("C2", "CONTRADICTED"),
                                  ("C3", "PENDING")]), cfg)
    placed = [cid for c in m.cells for cid in c.claim_ids]
    assert sorted(placed) == ["C1", "C2", "C3"]
    assert len(placed) == len(set(placed))


def test_threshold_status_is_carried_into_the_output(cfg):
    d = describe_claim("C1", _series({"5": 100}), cfg)
    m = build_matrix([d], _claims([("C1", "SUPPORTED")]), cfg)
    assert "PENDING" in m.threshold_status.upper()
    assert any("PLACEHOLDER" in n or "placeholder" in n for n in m.notes)


# ---------------------------------------------------------------------------
# Stage 6 — comment prioritisation
# ---------------------------------------------------------------------------

def test_comment_priority_ranks_the_interesting_claims_first(cfg):
    split = _series({"1": 30, "2": 30, "3": 10, "4": 30, "5": 30})   # bimodal
    plain = _series({"4": 130})
    ds = [describe_claim("C_PLAIN", plain, cfg), describe_claim("C_SPLIT", split, cfg)]
    claims = _claims([("C_PLAIN", "SUPPORTED"), ("C_SPLIT", "SUPPORTED")])
    m = build_matrix(ds, claims, cfg)
    comments = pd.DataFrame([
        {"respondent_id": "R1", "claim_id": "C_SPLIT", "answer": "1", "comment": "depends"},
        {"respondent_id": "R2", "claim_id": "C_PLAIN", "answer": "4", "comment": "sure"},
    ])
    out = collect_comments(comments, ds, [], m, cfg)
    assert out[0].claim_id == "C_SPLIT"
    assert out[0].priority_score > out[1].priority_score
    assert "bimodal" in out[0].priority_reasons[0]


def test_claims_without_comments_still_appear(cfg):
    ds = [describe_claim("C1", _series({"4": 100}), cfg)]
    m = build_matrix(ds, _claims([("C1", "SUPPORTED")]), cfg)
    out = collect_comments(pd.DataFrame(
        columns=["respondent_id", "claim_id", "answer", "comment"]), ds, [], m, cfg)
    assert len(out) == 1
    assert out[0].n_comments == 0


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
