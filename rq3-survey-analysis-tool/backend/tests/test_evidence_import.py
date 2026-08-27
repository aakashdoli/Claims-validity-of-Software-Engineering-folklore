"""The RQ2 evidence importer and its claim-identity gate.

The gate exists because claim IDs are not unique in the 4,091-claim corpus. A
label imported on the strength of its ID alone can belong to a different claim,
which is exactly what happened to `RQ2_Supervisor_Summary (2).xlsx`.
"""

from __future__ import annotations

import pandas as pd
import pytest

from rq3.claims import MISSING
from rq3.config import PROJECT_ROOT
from rq3.evidence import (EvidenceError, normalise_label, parse_label,
                          read_workbook, triage_rejection, write_evidence_csv)

SUMMARY = (PROJECT_ROOT / "data" / "source" / "_superseded"
           / "RQ2_Supervisor_Summary (2).xlsx")


def _claims(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame([
        {"q_number": i + 1, "claim_id": cid, "claim_type": "NORMATIVE",
         "book": "b", "author": MISSING, "source_text": text}
        for i, (cid, text) in enumerate(rows)
    ])


def _summary_book(path, rows: list[tuple[str, str, str, str]]):
    """rows = (claim_id, claim_text, final_label, evidence_summary)"""
    grid = [["RQ2 Evidence Mapping — Supervisor Summary", None, None, None],
            ["Label key: ...", None, None, None],
            ["Claim ID", "Claim Text", "Final Label", "Evidence Summary"]]
    grid += [list(r) for r in rows]
    pd.DataFrame(grid).to_excel(path, sheet_name="RQ2 Summary",
                                header=False, index=False)


def _detailed_log(path, sheets: list[tuple[str, str, str, str]]):
    """sheets = (claim_id, claim_text, final_label, evidence_summary)"""
    with pd.ExcelWriter(path) as xw:
        for cid, text, label, summary in sheets:
            grid = [
                [f"Evidence Mapping Log | {cid}", None],
                ["SECTION 1 — CLAIM DETAILS", None],
                ["Claim ID", cid],
                ["Claim Text", text],
                ["SECTION 5 — FULL PAPER READING", None],
                # A per-paper verdict, which must never be read as the final label.
                ["Verdict vs Claim", "SUPPORTS"],
                ["SECTION 7 — FINAL CONCLUSION", None],
                ["FINAL EVIDENCE LABEL", label],
                ["Evidence Summary", summary],
            ]
            pd.DataFrame(grid).to_excel(xw, sheet_name=cid, header=False, index=False)


# ---------------------------------------------------------------------------
# Label normalisation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("SUPPORTED", ("SUPPORTED", "")),
    ("supported", ("SUPPORTED", "")),
    ("  SUPPORTED  ", ("SUPPORTED", "")),
    ("CONTRADICTED", ("CONTRADICTED", "")),
    ("NO EVIDENCE FOUND", ("NO EVIDENCE FOUND", "")),
    ("no evidence", ("NO EVIDENCE FOUND", "")),
])
def test_plain_labels_parse_without_a_qualifier(cfg, raw, expected):
    assert parse_label(raw, cfg) == expected


@pytest.mark.parametrize("raw,strength", [
    ("SUPPORTED (weak evidence)", "weak evidence"),
    ("SUPPORTED / WEAK EVIDENCE", "weak evidence"),
    ("SUPPORTED/weak evidence", "weak evidence"),
    ("SUPPORTED (moderate evidence)", "moderate evidence"),
    ("SUPPORTED (mixed/contextual evidence)", "mixed/contextual evidence"),
    ("SUPPORTED - moderate", "moderate"),
    ("Supported (weak/contextual)", "weak/contextual"),
    ("weakly supported", "weak evidence"),
    ("partially supported", "partial evidence"),
])
def test_supported_variants_collapse_to_supported(cfg, raw, strength):
    """Only three categories exist; the qualifier is preserved, not a category."""
    label, got = parse_label(raw, cfg)
    assert label == "SUPPORTED"
    assert got == strength


@pytest.mark.parametrize("raw,strength", [
    ("CONTRADICTED (weak)", "weak"),
    ("CONTRADICTED (weak evidence)", "weak evidence"),
    ("weakly contradicted", "weak evidence"),
])
def test_contradicted_variants_collapse_too(cfg, raw, strength):
    label, got = parse_label(raw, cfg)
    assert label == "CONTRADICTED"
    assert got == strength


@pytest.mark.parametrize("raw", ["INSUFFICIENT EVIDENCE", "Conflicting evidence",
                                 "mixed evidence", "inconclusive", "unclear"])
def test_inconclusive_verdicts_become_no_evidence_found_with_a_note(cfg, raw):
    """Rule 3: no clean verdict either way is recorded as NO EVIDENCE FOUND."""
    label, strength = parse_label(raw, cfg)
    assert label == "NO EVIDENCE FOUND"
    assert "see notes" in strength


def test_every_parsed_label_is_one_of_the_three_categories(cfg):
    canonical = set(cfg.get("belief.evidence_labels"))
    assert canonical == {"SUPPORTED", "CONTRADICTED", "NO EVIDENCE FOUND"}
    for raw in ["SUPPORTED", "SUPPORTED (weak evidence)", "SUPPORTED / WEAK EVIDENCE",
                "CONTRADICTED", "CONTRADICTED (weak)", "NO EVIDENCE FOUND",
                "INSUFFICIENT EVIDENCE", "weakly supported"]:
        assert parse_label(raw, cfg)[0] in canonical


@pytest.mark.parametrize("raw", ["SUPPORTS", "CONTRADICTS", "NOTHING RELEVANT",
                                 "KEEP", "REJECT"])
def test_per_paper_verdicts_are_never_accepted_as_a_final_label(cfg, raw):
    """Sections 5-6 use a different vocabulary; it must not leak through."""
    assert normalise_label(raw, cfg) is None


@pytest.mark.parametrize("raw", ["", None, "probably fine", "TBD", float("nan")])
def test_unrecognised_labels_return_none(cfg, raw):
    assert normalise_label(raw, cfg) is None


# ---------------------------------------------------------------------------
# The claim-identity gate
# ---------------------------------------------------------------------------

def test_matching_claim_text_is_accepted(tmp_path, cfg):
    text = "Quality is an essential aspect of software that contributes to durability."
    claims = _claims([("CLM-000001", text)])
    book = tmp_path / "s.xlsx"
    _summary_book(book, [("CLM-000001", text, "SUPPORTED", "notes here")])
    report = read_workbook(book, claims, cfg)
    assert len(report.accepted) == 1
    row = report.rows[0]
    assert row.label == "SUPPORTED"
    assert row.summary == "notes here"
    assert row.text_similarity == pytest.approx(1.0)


def test_mismatched_claim_text_is_rejected(tmp_path, cfg):
    claims = _claims([("CLM-000062",
                       "Manual software development cannot be much more than 15% "
                       "better than average development.")])
    book = tmp_path / "s.xlsx"
    _summary_book(book, [("CLM-000062",
                          "Testing is the process of executing a program with the "
                          "intent of finding errors.", "CONTRADICTED", "x")])
    report = read_workbook(book, claims, cfg)
    assert report.accepted == []
    row = report.rows[0]
    assert row.accepted is False
    assert "mapped against a different claim" in row.reason
    assert row.triage == "likely_different_claim"


def test_a_label_with_no_claim_text_is_rejected(tmp_path, cfg):
    """An ID on its own is not enough — IDs are not unique in this corpus."""
    claims = _claims([("CLM-000001", "Some surveyed claim about durability.")])
    book = tmp_path / "s.xlsx"
    _summary_book(book, [("CLM-000001", "", "SUPPORTED", "x")])
    report = read_workbook(book, claims, cfg)
    assert report.accepted == []
    assert "claim IDs alone are not unique" in report.rows[0].reason


def test_paraphrase_and_different_claim_are_triaged_apart():
    para = triage_rejection(
        "Leadership by example is more effective than hierarchical authority.",
        "Some management theorists hold that motivating team members by example "
        "and leadership, and not through the hierarchy of authority, is effective.")
    assert para[1] == "likely_paraphrase"
    assert "leadership" in para[0]

    diff = triage_rejection(
        "Testing is the process of executing a program to find errors.",
        "Manual development cannot be 15% better than average due to fatigue.")
    assert diff[1] == "likely_different_claim"


def test_similarity_tolerates_an_appended_testable_assertion(tmp_path, cfg):
    """The detailed logs append 'Core testable assertion: ...' to book wording."""
    surveyed = "These organizations want to limit the use of specific FOSS licenses."
    claims = _claims([("CLM-000115", surveyed)])
    book = tmp_path / "d.xlsx"
    _detailed_log(book, [("CLM-000115",
                          surveyed + " Core testable assertion: vendors restrict "
                          "copyleft licences in commercial products.",
                          "SUPPORTED", "FOSS licensing evidence")])
    report = read_workbook(book, claims, cfg)
    assert report.shape == "detailed_log"
    assert len(report.accepted) == 1
    assert report.rows[0].label == "SUPPORTED"


def test_threshold_is_configurable_per_run(tmp_path, cfg):
    claims = _claims([("CLM-000001", "Alpha beta gamma delta epsilon zeta.")])
    book = tmp_path / "s.xlsx"
    _summary_book(book, [("CLM-000001", "Alpha beta gamma totally different.",
                          "SUPPORTED", "x")])
    assert read_workbook(book, claims, cfg, min_similarity=0.99).accepted == []
    assert len(read_workbook(book, claims, cfg, min_similarity=0.10).accepted) == 1


# ---------------------------------------------------------------------------
# Both workbook shapes
# ---------------------------------------------------------------------------

def test_detailed_log_reads_section_7_not_the_per_paper_verdict(tmp_path, cfg):
    claims = _claims([("CLM-000001", "A claim about deployment pipelines.")])
    book = tmp_path / "d.xlsx"
    _detailed_log(book, [("CLM-000001", "A claim about deployment pipelines.",
                          "CONTRADICTED", "summary text")])
    report = read_workbook(book, claims, cfg)
    # The fixture also contains a "Verdict vs Claim: SUPPORTS" row.
    assert report.rows[0].label == "CONTRADICTED"


def test_claims_absent_from_the_source_are_reported(tmp_path, cfg):
    claims = _claims([("CLM-000001", "first claim"), ("CLM-000002", "second claim")])
    book = tmp_path / "s.xlsx"
    _summary_book(book, [("CLM-000001", "first claim", "SUPPORTED", "")])
    report = read_workbook(book, claims, cfg)
    assert report.missing_claims == ["CLM-000002"]


def test_ids_not_in_the_survey_pool_are_reported(tmp_path, cfg):
    claims = _claims([("CLM-000001", "first claim")])
    book = tmp_path / "s.xlsx"
    _summary_book(book, [("CLM-000001", "first claim", "SUPPORTED", ""),
                         ("CLM-999999", "stray claim", "SUPPORTED", "")])
    report = read_workbook(book, claims, cfg)
    assert report.unknown_ids == ["CLM-999999"]
    assert len(report.rows) == 1


def test_unrecognisable_workbook_raises(tmp_path, cfg):
    book = tmp_path / "junk.xlsx"
    pd.DataFrame([["nothing", "useful"], ["here", "either"]]).to_excel(
        book, header=False, index=False)
    with pytest.raises(EvidenceError, match="found neither"):
        read_workbook(book, _claims([("CLM-000001", "x")]), cfg)


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def test_rejected_and_absent_claims_stay_pending(tmp_path, cfg):
    claims = _claims([("CLM-000001", "alpha claim about durability metrics"),
                      ("CLM-000002", "beta claim about deployment pipelines"),
                      ("CLM-000003", "gamma claim about inspection meetings")])
    book = tmp_path / "s.xlsx"
    _summary_book(book, [
        ("CLM-000001", "alpha claim about durability metrics", "SUPPORTED", "ok"),
        ("CLM-000002", "utterly unrelated wording here", "CONTRADICTED", "bad"),
    ])
    report = read_workbook(book, claims, cfg)
    frame = write_evidence_csv(report, claims, tmp_path / "out.csv", cfg)
    got = dict(zip(frame["claim_id"], frame["evidence_label"]))
    assert got == {"CLM-000001": "SUPPORTED",
                   "CLM-000002": "PENDING",     # rejected by the gate
                   "CLM-000003": "PENDING"}     # absent from the source
    notes = dict(zip(frame["claim_id"], frame["evidence_notes"]))
    assert notes["CLM-000001"] == "ok"
    assert notes["CLM-000002"] == ""            # the rejected summary is not kept
    assert "evidence_strength" in frame.columns


def test_strength_qualifier_reaches_the_written_csv(tmp_path, cfg):
    claims = _claims([("CLM-000001", "alpha claim about durability metrics")])
    book = tmp_path / "s.xlsx"
    _summary_book(book, [("CLM-000001", "alpha claim about durability metrics",
                          "SUPPORTED / WEAK EVIDENCE", "the summary")])
    report = read_workbook(book, claims, cfg)
    frame = write_evidence_csv(report, claims, tmp_path / "out.csv", cfg)
    row = frame.iloc[0]
    assert row["evidence_label"] == "SUPPORTED"      # collapsed
    assert row["evidence_strength"] == "weak evidence"  # preserved
    assert row["evidence_notes"] == "the summary"


def test_written_file_is_loadable_by_the_pipeline(tmp_path, cfg):
    """Whatever the importer writes must pass load_claims' own validation."""
    from rq3.claims import load_claims
    claims = load_claims(cfg)
    book = tmp_path / "s.xlsx"
    first = claims.iloc[0]
    _summary_book(book, [(first["claim_id"], first["source_text"], "SUPPORTED", "n")])
    report = read_workbook(book, claims, cfg)
    frame = write_evidence_csv(report, claims, tmp_path / "e.csv", cfg)
    valid = set(cfg.get("belief.evidence_labels")) | {cfg.get("belief.pending_label")}
    assert set(frame["evidence_label"]) <= valid
    assert list(frame["claim_id"]) == list(claims["claim_id"])


# ---------------------------------------------------------------------------
# The real workbook that was handed over
# ---------------------------------------------------------------------------

def test_the_supervisor_summary_fails_the_gate_for_most_claims(cfg):
    """Regression record of a real data-integrity problem.

    `RQ2_Supervisor_Summary (2).xlsx` carries a label for all 50 claims, but for
    most of them the Claim Text / Claim Type / Key Evidence / Evidence Summary
    columns describe a different claim, so the label cannot be attributed to the
    surveyed claim. If this file is ever corrected, this test will fail and
    should be updated deliberately — not deleted.
    """
    from rq3.claims import load_claims
    if not SUMMARY.exists():
        pytest.skip("supervisor summary not present")
    report = read_workbook(SUMMARY, load_claims(cfg), cfg)
    assert len(report.rows) == 50
    assert report.missing_claims == []
    assert len(report.rejected) > len(report.accepted), (
        "the gate no longer rejects the majority — re-verify before importing")
    # Every label in the file is at least a recognised one; the problem is
    # attribution, not vocabulary.
    assert all(r.label is not None for r in report.rows)
