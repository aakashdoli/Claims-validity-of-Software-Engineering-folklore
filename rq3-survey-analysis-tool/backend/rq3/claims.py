"""Claim metadata: identity, provenance, and RQ2 evidence labels.

Two files, deliberately kept separate:

``data/claims.csv``
    GENERATED from ``data/source/Final_50_Claims_Public.xlsx`` (the authoritative
    claim set, cross-verified against ``364_claims.xlsx`` and ``master.xlsx``)
    plus the survey wording read back out of the export itself. Regenerating it
    is always safe — it holds no hand-entered content.

``data/claims_evidence.csv``
    HAND-MAINTAINED. One row per claim ID carrying the RQ2 evidence label.
    Never overwritten by the tool. Claims left as ``PENDING`` flow through the
    whole pipeline and surface as an explicit "not yet labelled" bucket in the
    belief-evidence matrix rather than being dropped or guessed.

Claim IDs are NOT unique across the full 4,091-claim corpus (the extraction
pipeline reused IDs across books), which is why the ordered, book-qualified
row from ``Final_50_Claims_Public.xlsx`` is the identity used here, and why the
survey's own question order is the join key against the export.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import Config

_SOURCE_SHEET = "Final 50 Claims"

# Sentinel written whenever the source workbook has no value for a field. It is
# never inferred, looked up elsewhere, or left blank: a reader must be able to
# tell "the workbook does not record this" apart from "nobody filled it in".
MISSING = "MISSING"

# Column headers as they appear in the workbook, mapped to our field names.
# Several spellings are accepted so that adding e.g. an "Author" column to the
# sheet later is picked up automatically rather than needing a code change.
_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "q_number": ("#", "no", "num", "number"),
    "claim_id": ("claim id", "claimid", "id"),
    "claim_type": ("claim type", "type"),
    "book": ("book", "source book", "book title"),
    "author": ("author", "authors", "book author", "book authors"),
    "source_text": ("claim text", "text", "claim"),
}
_REQUIRED_FIELDS = ("q_number", "claim_id", "book", "source_text")


class ClaimsError(RuntimeError):
    pass


def _norm_header(value: object) -> str:
    return " ".join(str(value).strip().lower().split()) if pd.notna(value) else ""


def _locate_columns(raw: pd.DataFrame) -> tuple[int, dict[str, int]]:
    """Find the header row and map our field names onto its column positions.

    The sheet carries two banner rows above the real header, and the header text
    itself has been edited over the project's life, so the header is located by
    content ("Claim ID") rather than by a hardcoded row number.
    """
    for row_idx in range(min(10, len(raw))):
        headers = [_norm_header(v) for v in raw.iloc[row_idx].tolist()]
        if not any(h in _COLUMN_ALIASES["claim_id"] for h in headers):
            continue
        mapping: dict[str, int] = {}
        for field, aliases in _COLUMN_ALIASES.items():
            for col_idx, header in enumerate(headers):
                # "evidence label (rq2 - to fill)" must not match "claim text",
                # so compare against the header's leading phrase as well.
                lead = header.split("(")[0].strip()
                if header in aliases or lead in aliases:
                    mapping[field] = col_idx
                    break
        missing = [f for f in _REQUIRED_FIELDS if f not in mapping]
        if missing:
            raise ClaimsError(
                f"'{_SOURCE_SHEET}' header row {row_idx} is missing required "
                f"column(s) {missing}; found {[h for h in headers if h]}"
            )
        return row_idx, mapping
    raise ClaimsError(f"could not find a header row containing 'Claim ID' in '{_SOURCE_SHEET}'")


def build_claims_csv(source_xlsx: str | Path, out_path: str | Path) -> pd.DataFrame:
    """Extract the ordered 50-claim pool into a flat CSV.

    Fields the workbook does not carry (currently the book author — there is no
    such column in the sheet) are written as ``MISSING`` for every claim, never
    guessed from the book title or filled in from another source.
    """
    raw = pd.read_excel(source_xlsx, sheet_name=_SOURCE_SHEET, header=None)
    header_row, cols = _locate_columns(raw)
    df = raw.iloc[header_row + 1:]
    df = df[df.iloc[:, cols["claim_id"]].astype(str).str.strip().str.startswith("CLM")].copy()

    def column(field: str) -> list[str]:
        if field not in cols:
            return [MISSING] * len(df)
        values = df.iloc[:, cols[field]]
        return [MISSING if pd.isna(v) or not str(v).strip() else str(v).strip()
                for v in values]

    out = pd.DataFrame({
        "q_number": [int(float(v)) for v in df.iloc[:, cols["q_number"]]],
        "claim_id": column("claim_id"),
        "claim_type": column("claim_type"),
        "book": column("book"),
        "author": column("author"),
        "source_text": column("source_text"),
    })
    out = out.sort_values("q_number").reset_index(drop=True)
    if out["claim_id"].duplicated().any():
        dupes = out.loc[out["claim_id"].duplicated(keep=False), "claim_id"].tolist()
        raise ClaimsError(f"duplicate claim IDs in the survey pool: {sorted(set(dupes))}")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    return out


def build_evidence_scaffold(claims: pd.DataFrame, out_path: str | Path,
                            pending_label: str) -> Path:
    """Create the hand-maintained evidence file, if it does not exist yet.

    Never overwrites: RQ2 labels are hand-entered research output.
    """
    out_path = Path(out_path)
    if out_path.exists():
        return out_path
    scaffold = pd.DataFrame({
        "claim_id": claims["claim_id"],
        "evidence_label": pending_label,
        "evidence_strength": "",
        "evidence_notes": "",
    })
    out_path.parent.mkdir(parents=True, exist_ok=True)
    scaffold.to_csv(out_path, index=False)
    return out_path


def load_claims(cfg: Config) -> pd.DataFrame:
    """Load claim metadata joined with RQ2 evidence labels.

    Unlabelled claims are kept and marked ``PENDING``; a missing evidence file
    is an error rather than a silent default, so nobody can produce a matrix
    without noticing the labels never got wired in.
    """
    claims_path = cfg.resolve_path("dataset.claims_file")
    evidence_path = cfg.resolve_path("dataset.evidence_file")
    if not claims_path.exists():
        raise ClaimsError(
            f"{claims_path} not found — run `python -m rq3.cli build-claims` first"
        )
    claims = pd.read_csv(claims_path)
    claims = claims.sort_values("q_number").reset_index(drop=True)

    pending = str(cfg.get("belief.pending_label"))
    valid_labels = set(cfg.get("belief.evidence_labels")) | {pending}

    if not evidence_path.exists():
        raise ClaimsError(
            f"{evidence_path} not found — run `python -m rq3.cli build-claims` "
            "to create the scaffold, then fill in the RQ2 evidence labels."
        )
    evidence = pd.read_csv(evidence_path)
    # evidence_strength was added when the four label categories were collapsed
    # to three; files written before that are still valid input.
    if "evidence_strength" not in evidence.columns:
        evidence["evidence_strength"] = ""
    evidence = evidence.fillna({"evidence_label": pending, "evidence_strength": "",
                                "evidence_notes": ""})
    evidence["evidence_label"] = evidence["evidence_label"].astype(str).str.strip()
    evidence["evidence_strength"] = evidence["evidence_strength"].astype(str).str.strip()

    unknown = sorted(set(evidence["evidence_label"]) - valid_labels)
    if unknown:
        raise ClaimsError(
            f"{evidence_path} contains evidence labels that are not in "
            f"config.yaml belief.evidence_labels ({sorted(valid_labels)}): "
            f"{unknown}. Strength qualifiers are no longer separate categories — "
            "re-import with `python -m rq3.cli evidence <file> --write`, which "
            "collapses them onto the base label and preserves the wording in the "
            "evidence_strength column."
        )
    missing_rows = sorted(set(claims["claim_id"]) - set(evidence["claim_id"]))
    if missing_rows:
        raise ClaimsError(
            f"{evidence_path} has no row for: {missing_rows}. Every claim must "
            "appear, even if the label is still PENDING."
        )

    merged = claims.merge(
        evidence[["claim_id", "evidence_label", "evidence_strength", "evidence_notes"]],
        on="claim_id", how="left", validate="one_to_one",
    )
    merged["evidence_label"] = merged["evidence_label"].fillna(pending)
    merged["evidence_strength"] = merged["evidence_strength"].fillna("")
    merged["evidence_notes"] = merged["evidence_notes"].fillna("")
    return merged
