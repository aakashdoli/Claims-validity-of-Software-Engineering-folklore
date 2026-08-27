"""Claim provenance (book / author) and the single-line evidence verdict."""

from __future__ import annotations

import pandas as pd
import pytest

from rq3.analysis.descriptives import describe_claim
from rq3.analysis.matrix import build_matrix
from rq3.claims import MISSING, ClaimsError, build_claims_csv, load_claims
from rq3.config import PROJECT_ROOT

SOURCE = PROJECT_ROOT / "data" / "source" / "Final_50_Claims.xlsx"


def _write_sheet(path, rows: list[list], sheet="Final 50 Claims"):
    pd.DataFrame(rows).to_excel(path, sheet_name=sheet, header=False, index=False)


# ---------------------------------------------------------------------------
# Book and author come from the workbook, or say MISSING
# ---------------------------------------------------------------------------

def test_real_workbook_yields_a_book_for_every_claim(tmp_path):
    if not SOURCE.exists():
        pytest.skip("source workbook not present")
    out = build_claims_csv(SOURCE, tmp_path / "claims.csv")
    assert len(out) == 50
    assert (out["book"] != MISSING).all()
    assert out["book"].str.len().min() > 3


def test_real_workbook_has_no_author_column_so_author_is_missing(tmp_path):
    """The sheet carries no author field; it must be MISSING, never inferred."""
    if not SOURCE.exists():
        pytest.skip("source workbook not present")
    out = build_claims_csv(SOURCE, tmp_path / "claims.csv")
    assert set(out["author"]) == {MISSING}


def test_an_author_column_is_picked_up_automatically(tmp_path):
    """Adding an Author column to the workbook needs no code change."""
    path = tmp_path / "with_author.xlsx"
    _write_sheet(path, [
        ["Final 50 Claims — Survey Pool", None, None, None, None, None, None],
        ["banner row", None, None, None, None, None, None],
        ["#", "Claim ID", "Claim Type", "Agreement Tier", "Book", "Author", "Claim Text"],
        [1, "CLM-000001", "NORMATIVE", "t1", "Some Book", "A. Writer", "Some claim."],
        [2, "CLM-000002", "CAUSAL", "t2", "Other Book", None, "Another claim."],
    ])
    out = build_claims_csv(path, tmp_path / "claims.csv")
    assert out.loc[0, "author"] == "A. Writer"
    # Blank cell in an existing column is still MISSING, not empty string.
    assert out.loc[1, "author"] == MISSING


def test_blank_book_becomes_missing_not_an_empty_cell(tmp_path):
    path = tmp_path / "blank_book.xlsx"
    _write_sheet(path, [
        ["banner", None, None, None, None, None],
        ["#", "Claim ID", "Claim Type", "Agreement Tier", "Book", "Claim Text"],
        [1, "CLM-000001", "NORMATIVE", "t1", "   ", "Some claim."],
    ])
    out = build_claims_csv(path, tmp_path / "claims.csv")
    assert out.loc[0, "book"] == MISSING


def test_missing_required_column_is_an_error_not_a_silent_blank(tmp_path):
    path = tmp_path / "no_book.xlsx"
    _write_sheet(path, [
        ["#", "Claim ID", "Claim Type", "Claim Text"],
        [1, "CLM-000001", "NORMATIVE", "Some claim."],
    ])
    with pytest.raises(ClaimsError, match="book"):
        build_claims_csv(path, tmp_path / "claims.csv")


def test_header_is_located_by_content_not_row_number(tmp_path):
    """Extra banner rows above the header must not break the extraction."""
    path = tmp_path / "deep_header.xlsx"
    _write_sheet(path, [
        ["title", None, None, None, None, None],
        ["subtitle", None, None, None, None, None],
        [None, None, None, None, None, None],
        ["#", "Claim ID", "Claim Type", "Agreement Tier", "Book", "Claim Text"],
        [1, "CLM-000009", "CAUSAL", "t", "A Book", "Text."],
    ])
    out = build_claims_csv(path, tmp_path / "claims.csv")
    assert out.loc[0, "claim_id"] == "CLM-000009"
    assert out.loc[0, "book"] == "A Book"


def test_loaded_claims_expose_book_and_author(cfg):
    claims = load_claims(cfg)
    assert {"book", "author"} <= set(claims.columns)
    assert claims["book"].notna().all()
    assert claims["author"].notna().all()


# ---------------------------------------------------------------------------
# The verdict line
# ---------------------------------------------------------------------------

def _claims(claim_id: str, label: str) -> pd.DataFrame:
    return pd.DataFrame([{
        "q_number": 1, "claim_id": claim_id, "claim_type": "NORMATIVE",
        "book": "b", "author": MISSING, "source_text": "s",
        "evidence_label": label, "evidence_notes": "",
    }])


def _series(counts: dict[str, int]) -> pd.Series:
    out: list[str] = []
    for value, n in counts.items():
        out.extend([value] * n)
    return pd.Series(out)


def test_verdict_is_pending_while_rq2_is_unfilled(cfg):
    d = describe_claim("C1", _series({"5": 100}), cfg)
    k = build_matrix([d], _claims("C1", "PENDING"), cfg).classifications[0]
    assert k.verdict_status == "pending"
    assert "PENDING" in k.verdict
    assert "No verdict yet" in k.verdict
    # No match/mismatch word may appear in a pending verdict.
    assert "MISMATCH" not in k.verdict and "MATCH" not in k.verdict


def test_verdict_states_a_mismatch_plainly(cfg):
    d = describe_claim("C1", _series({"5": 100}), cfg)
    k = build_matrix([d], _claims("C1", "CONTRADICTED"), cfg).classifications[0]
    assert k.verdict_status == "mismatch"
    assert k.verdict.startswith("MISMATCH")
    assert "CONTRADICTED" in k.verdict
    assert "median 5" in k.verdict


def test_verdict_states_a_match_plainly(cfg):
    d = describe_claim("C1", _series({"5": 100}), cfg)
    k = build_matrix([d], _claims("C1", "SUPPORTED"), cfg).classifications[0]
    assert k.verdict_status == "match"
    assert k.verdict.startswith("MATCH")


def test_verdict_flags_a_provisional_borderline_placement(cfg):
    d = describe_claim("C1", _series({"3": 50, "4": 50}), cfg)   # median 3.5
    k = build_matrix([d], _claims("C1", "SUPPORTED"), cfg).classifications[0]
    assert k.borderline is True
    assert "provisional" in k.verdict


def test_verdict_for_an_unclassifiable_claim(cfg):
    d = describe_claim("C1", pd.Series(["IDK"] * 60), cfg)
    k = build_matrix([d], _claims("C1", "SUPPORTED"), cfg).classifications[0]
    assert k.verdict_status == "unclassifiable"
    assert "No verdict" in k.verdict
