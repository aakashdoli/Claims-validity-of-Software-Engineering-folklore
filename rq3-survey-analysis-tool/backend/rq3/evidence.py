"""Import RQ2 evidence labels — with a claim-identity gate.

Why this module is defensive
----------------------------
Claim IDs are NOT unique across the 4,091-claim corpus: the RQ1 extraction
pipeline reused IDs across books, and 49 of the 50 survey IDs have a duplicate
somewhere in the corpus. That has already caused one silent corruption
(``50_claims_full_text_.xlsx`` carried the wrong claim text for 17 of 50), and
importing a label under a claim ID alone is therefore not safe.

So this importer never trusts the ID by itself. For every row it also compares
the *claim text* the evidence work was done against with the text that was
actually put in front of respondents. A row whose text does not match is
REJECTED — the claim keeps its ``PENDING`` label rather than inheriting a label
that was reasoned about a different claim.

Two workbook shapes are supported:

**Summary table** — one row per claim, with ``Claim ID`` / ``Final Label`` /
``Claim Text`` columns (e.g. ``RQ2_Supervisor_Summary.xlsx``).

**Detailed log** — one sheet per claim, sheet named ``CLM-XXXXXX``, with
key/value rows: ``Claim Text``, ``FINAL EVIDENCE LABEL``, ``Evidence Summary``.
Only the Section 7 ``FINAL EVIDENCE LABEL`` is read; the per-paper verdicts in
Sections 5-6 use a different vocabulary (``SUPPORTS`` / ``CONTRADICTS`` /
``NOTHING RELEVANT``) and are deliberately ignored.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .config import Config

# RQ2 uses THREE categories. Strength qualifiers are collapsed onto the base
# label and preserved separately (see :func:`parse_label`), so "SUPPORTED (weak
# evidence)" becomes label=SUPPORTED, strength="weak evidence" — nothing is lost
# but the belief-evidence matrix stays a 2 x 3 grid.
_STEM_SYNONYMS: dict[str, str] = {
    "supported": "SUPPORTED",
    "support": "SUPPORTED",
    "supports": "SUPPORTED",
    "contradicted": "CONTRADICTED",
    "contradict": "CONTRADICTED",
    "contradicts": "CONTRADICTED",
    "refuted": "CONTRADICTED",
    "no evidence found": "NO EVIDENCE FOUND",
    "no evidence": "NO EVIDENCE FOUND",
    "none found": "NO EVIDENCE FOUND",
    "no relevant evidence": "NO EVIDENCE FOUND",
    "nothing relevant": "NO EVIDENCE FOUND",
}

# Whole phrases that carry their strength inside the wording rather than as a
# separate qualifier.
_PHRASE_SYNONYMS: dict[str, tuple[str, str]] = {
    "weakly supported": ("SUPPORTED", "weak evidence"),
    "partially supported": ("SUPPORTED", "partial evidence"),
    "partly supported": ("SUPPORTED", "partial evidence"),
    "strongly supported": ("SUPPORTED", "strong evidence"),
    "weakly contradicted": ("CONTRADICTED", "weak evidence"),
    "partially contradicted": ("CONTRADICTED", "partial evidence"),
}

# No clean verdict either way. Per the finalisation rule these are recorded as
# NO EVIDENCE FOUND for matrix purposes, with the original wording kept as the
# strength note so the reason survives into the claim page and the exports.
_INCONCLUSIVE: dict[str, str] = {
    "insufficient evidence": "insufficient evidence — see notes",
    "insufficient": "insufficient evidence — see notes",
    "conflicting evidence": "conflicting evidence — see notes",
    "conflicting": "conflicting evidence — see notes",
    "mixed evidence": "conflicting evidence — see notes",
    "mixed": "conflicting evidence — see notes",
    "inconclusive": "inconclusive — see notes",
    "unclear": "inconclusive — see notes",
}

_LABEL_KEYS = ("final evidence label", "final label", "evidence label")
_TEXT_KEYS = ("claim text", "claim")
_SUMMARY_KEYS = ("evidence summary", "summary")
_ID_KEYS = ("claim id", "claimid", "id")

# Per-paper verdict vocabulary from Sections 5-6 — must never be mistaken for a
# final label if it turns up in a label cell.
_PER_PAPER_VERDICTS = {"supports", "contradicts", "nothing relevant",
                       "partially supports", "keep", "reject"}


class EvidenceError(RuntimeError):
    pass


@dataclass
class EvidenceRow:
    claim_id: str
    label_raw: str
    label: str | None            # canonical, or None if unrecognised
    strength: str                # dropped qualifier, kept verbatim
    summary: str
    source_text: str             # claim text the evidence work used
    surveyed_text: str           # claim text respondents actually saw
    text_similarity: float
    accepted: bool
    reason: str
    # Triage for a rejected row, so manual review is fast. A rejection can mean
    # two very different things and they must not be conflated:
    #   "likely_paraphrase"      — same claim, reworded; probably salvageable
    #   "likely_different_claim" — no shared subject matter; the label belongs
    #                              to another claim and must not be imported
    shared_terms: list[str] = field(default_factory=list)
    triage: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class ImportReport:
    source_file: str
    shape: str                   # "summary_table" | "detailed_log"
    rows: list[EvidenceRow]
    missing_claims: list[str] = field(default_factory=list)
    unknown_ids: list[str] = field(default_factory=list)
    min_similarity: float = 0.0

    @property
    def accepted(self) -> list[EvidenceRow]:
        return [r for r in self.rows if r.accepted]

    @property
    def rejected(self) -> list[EvidenceRow]:
        return [r for r in self.rows if not r.accepted]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file, "shape": self.shape,
            "min_similarity": self.min_similarity,
            "n_accepted": len(self.accepted), "n_rejected": len(self.rejected),
            "missing_claims": self.missing_claims, "unknown_ids": self.unknown_ids,
            "rows": [r.to_dict() for r in self.rows],
        }


def _norm_text(value: object) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", str(value).lower()).strip()


def _similarity(a: str, b: str) -> float:
    na, nb = _norm_text(a), _norm_text(b)
    if not na or not nb:
        return 0.0
    # The evidence logs often append "Core testable assertion: ..." to the book
    # wording, so compare on the shorter string's terms rather than penalising
    # the extra text.
    ratio = difflib.SequenceMatcher(None, na, nb).ratio()
    shorter, longer = sorted((na, nb), key=len)
    if shorter and shorter in longer:
        return 1.0
    blocks = difflib.SequenceMatcher(None, shorter, longer)
    covered = sum(b.size for b in blocks.get_matching_blocks())
    return max(ratio, covered / len(shorter))


# Words too common in software engineering prose to be evidence of shared
# subject matter between two claims.
_STOPWORDS = {
    "software", "should", "development", "developer", "developers", "engineer",
    "engineers", "engineering", "process", "processes", "project", "projects",
    "system", "systems", "product", "products", "there", "their", "these",
    "those", "which", "while", "would", "could", "about", "often", "usually",
    "however", "instead", "because", "through", "between", "before", "after",
    "other", "others", "such", "than", "that", "this", "with", "from", "more",
    "most", "many", "some", "when", "where", "into", "also", "been", "being",
    "have", "must", "will", "made", "make", "used", "using", "based", "code",
    "codes", "coding", "team", "teams", "work", "works", "time", "times",
}


def _distinctive_terms(text: str) -> set[str]:
    return {w for w in _norm_text(text).split()
            if len(w) >= 5 and w not in _STOPWORDS}


def triage_rejection(source_text: str, surveyed_text: str) -> tuple[list[str], str]:
    """Does a rejected row at least concern the same subject matter?"""
    shared = sorted(_distinctive_terms(source_text) & _distinctive_terms(surveyed_text))
    if len(shared) >= 2:
        return shared, "likely_paraphrase"
    return shared, "likely_different_claim"


def _split_qualifier(text: str) -> tuple[str, str]:
    """Separate a label stem from its strength qualifier.

    Handles the spellings the evidence work actually used:
    ``SUPPORTED (weak evidence)`` · ``SUPPORTED / WEAK EVIDENCE`` ·
    ``SUPPORTED - moderate`` · ``SUPPORTED, mixed/contextual evidence``.
    """
    t = " ".join(text.replace("\u2013", "-").replace("\u2014", "-").split())
    m = re.match(r"^([^(]+?)\s*\((.+)\)\s*$", t)
    if m:
        return m.group(1).strip(), m.group(2).strip().lower()
    for sep in (" / ", "/", " - ", " , ", ", ", ";"):
        if sep in t:
            head, _, tail = t.partition(sep)
            head, tail = head.strip(), tail.strip()
            # Only treat it as a qualifier if the head is a label on its own;
            # otherwise the slash is part of the wording ("mixed/contextual").
            if head.lower() in _STEM_SYNONYMS:
                return head, tail.lower()
    return t, ""


def parse_label(raw: object, cfg: Config) -> tuple[str | None, str]:
    """Return ``(canonical_label, strength_qualifier)``.

    The canonical label is always one of the three values in
    ``belief.evidence_labels``, or ``None`` when the text is not a recognised
    final label. The qualifier is the dropped strength wording, kept verbatim so
    it can be shown on the claim page and carried into exports.
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None, ""
    text = " ".join(str(raw).strip().split())
    if not text:
        return None, ""

    canonical = set(cfg.get("belief.evidence_labels"))
    if text in canonical:
        return text, ""

    stem, qualifier = _split_qualifier(text)
    key = stem.lower().rstrip(".").strip()

    if key in _PER_PAPER_VERDICTS and not qualifier:
        return None, ""          # a Section 5/6 verdict, not a final label

    if key in _PHRASE_SYNONYMS:
        base, strength = _PHRASE_SYNONYMS[key]
        return base, (qualifier or strength)

    if key in _INCONCLUSIVE:
        return "NO EVIDENCE FOUND", _INCONCLUSIVE[key]

    base = _STEM_SYNONYMS.get(key)
    if base is None:
        return None, ""
    if base not in canonical:
        return None, ""
    # "no evidence found (weak)" makes no sense as a strength; keep the wording
    # anyway rather than inventing a rule for it.
    return base, qualifier


def normalise_label(raw: object, cfg: Config) -> str | None:
    """Canonical label only — thin wrapper over :func:`parse_label`."""
    return parse_label(raw, cfg)[0]


# ---------------------------------------------------------------------------
# Shape detection and extraction
# ---------------------------------------------------------------------------

def _grid(path: Path, sheet: object) -> pd.DataFrame:
    d = pd.read_excel(path, sheet_name=sheet, header=None)
    return d.map(lambda v: "" if pd.isna(v) else str(v).strip())


def _value_beside(grid: pd.DataFrame, keys: tuple[str, ...]) -> str:
    """First non-empty cell to the right of a key cell, searched top-down."""
    for i in range(len(grid)):
        for j in range(grid.shape[1]):
            cell = grid.iat[i, j].lower().rstrip(":").strip()
            if cell in keys:
                for k in range(j + 1, grid.shape[1]):
                    if grid.iat[i, k]:
                        return grid.iat[i, k]
    return ""


def _extract_detailed_log(path: Path) -> list[dict[str, str]]:
    xl = pd.ExcelFile(path)
    sheets = [s for s in xl.sheet_names if str(s).upper().startswith("CLM-")]
    out = []
    for sheet in sheets:
        g = _grid(path, sheet)
        out.append({
            "claim_id": str(sheet).strip().upper(),
            "label": _value_beside(g, _LABEL_KEYS),
            "text": _value_beside(g, _TEXT_KEYS),
            "summary": _value_beside(g, _SUMMARY_KEYS),
        })
    return out


def _extract_summary_table(path: Path) -> list[dict[str, str]]:
    xl = pd.ExcelFile(path)
    best: list[dict[str, str]] = []
    for sheet in xl.sheet_names:
        g = _grid(path, sheet)
        for i in range(min(20, len(g))):
            headers = [g.iat[i, j].lower().strip() for j in range(g.shape[1])]
            if not any(h in _ID_KEYS for h in headers):
                continue
            col = {}
            for j, h in enumerate(headers):
                lead = h.split("(")[0].strip()
                for name, keys in (("claim_id", _ID_KEYS), ("label", _LABEL_KEYS),
                                   ("text", _TEXT_KEYS), ("summary", _SUMMARY_KEYS)):
                    if name not in col and (h in keys or lead in keys):
                        col[name] = j
            if "claim_id" not in col or "label" not in col:
                continue
            out = []
            for r in range(i + 1, len(g)):
                cid = g.iat[r, col["claim_id"]].strip().upper()
                if not cid.startswith("CLM-"):
                    continue
                out.append({
                    "claim_id": cid,
                    "label": g.iat[r, col["label"]],
                    "text": g.iat[r, col["text"]] if "text" in col else "",
                    "summary": g.iat[r, col["summary"]] if "summary" in col else "",
                })
            # Several sheets can look table-ish; keep the richest one rather
            # than whichever happens to come first in the workbook.
            if len(out) > len(best):
                best = out
    if best:
        return best
    raise EvidenceError(
        f"{path.name}: found neither one-sheet-per-claim (CLM-* sheets) nor a "
        "table with 'Claim ID' and a label column"
    )


def read_workbook(path: str | Path, claims: pd.DataFrame,
                  cfg: Config, min_similarity: float | None = None) -> ImportReport:
    """Extract labels and gate every one of them on claim identity."""
    path = Path(path)
    if not path.exists():
        raise EvidenceError(f"file not found: {path}")
    threshold = (min_similarity if min_similarity is not None
                 else float(cfg.get("evidence.min_text_similarity")))

    xl = pd.ExcelFile(path)
    clm_sheets = [s for s in xl.sheet_names if str(s).upper().startswith("CLM-")]
    # A one-row-per-claim table is tried FIRST. Workbooks often keep a stray
    # per-claim sheet alongside the main table (Final_50_Claims.xlsx still has a
    # leftover CLM-000179 tab), and reading that one sheet instead of the table
    # would silently import 1 claim and report the other 49 as missing.
    try:
        raw, shape = _extract_summary_table(path), "summary_table"
    except EvidenceError:
        if not clm_sheets:
            raise
        raw, shape = _extract_detailed_log(path), "detailed_log"
    else:
        # Only prefer the per-sheet logs if they genuinely cover more claims.
        if len(clm_sheets) > len(raw):
            raw, shape = _extract_detailed_log(path), "detailed_log"

    surveyed = dict(zip(claims["claim_id"], claims["source_text"]))
    rows: list[EvidenceRow] = []
    unknown: list[str] = []

    for item in raw:
        cid = item["claim_id"]
        if cid not in surveyed:
            unknown.append(cid)
            continue
        label, strength = parse_label(item["label"], cfg)
        sim = _similarity(item["text"], surveyed[cid]) if item["text"] else 0.0

        if label is None:
            accepted, reason = False, (
                f"label {item['label']!r} is not one of "
                f"{cfg.get('belief.evidence_labels')} and has no known synonym")
        elif not item["text"]:
            accepted, reason = False, (
                "no claim text in the source, so the label cannot be tied to "
                "this claim; claim IDs alone are not unique in this corpus")
        elif sim < threshold:
            accepted, reason = False, (
                f"claim text does not match the surveyed claim "
                f"(similarity {sim:.2f} < {threshold}); the evidence appears to "
                "have been mapped against a different claim")
        else:
            accepted, reason = True, f"claim text matches (similarity {sim:.2f})"

        shared, triage = ([], "") if accepted else triage_rejection(
            item["text"], surveyed[cid])
        rows.append(EvidenceRow(
            claim_id=cid, label_raw=str(item["label"]).strip(), label=label,
            strength=strength, summary=str(item["summary"]).strip(),
            source_text=str(item["text"]).strip(),
            surveyed_text=str(surveyed[cid]), text_similarity=sim,
            accepted=accepted, reason=reason, shared_terms=shared, triage=triage,
        ))

    seen = {r.claim_id for r in rows}
    return ImportReport(
        source_file=str(path), shape=shape, rows=rows,
        missing_claims=sorted(set(surveyed) - seen), unknown_ids=sorted(set(unknown)),
        min_similarity=threshold,
    )


def write_evidence_csv(report: ImportReport, claims: pd.DataFrame,
                       out_path: str | Path, cfg: Config) -> pd.DataFrame:
    """Write claims_evidence.csv from the ACCEPTED rows only.

    Rejected and absent claims stay ``PENDING`` and flow through the pipeline as
    unlabelled — they are never given a label the gate refused.
    """
    pending = str(cfg.get("belief.pending_label"))
    accepted = {r.claim_id: r for r in report.accepted}
    frame = pd.DataFrame({
        "claim_id": claims["claim_id"],
        "evidence_label": [accepted[c].label if c in accepted else pending
                           for c in claims["claim_id"]],
        # The strength qualifier dropped when collapsing onto the base label.
        # Kept so "SUPPORTED (weak evidence)" is still readable as such on the
        # claim page and in exports, without being a separate matrix category.
        "evidence_strength": [accepted[c].strength if c in accepted else ""
                              for c in claims["claim_id"]],
        "evidence_notes": [accepted[c].summary if c in accepted else ""
                           for c in claims["claim_id"]],
    })
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out_path, index=False)
    return frame
