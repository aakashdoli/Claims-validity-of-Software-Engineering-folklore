"""Stage 5b — the belief-evidence matrix, built on the majority buckets.

The core RQ3 output: which direction a majority of practitioners took, crossed
with what the RQ2 evidence review found. Structurally this follows the
belief-vs-evidence framing of

  Devanbu, P., Zimmermann, T. & Bird, C. (2016). "Belief & evidence in
  empirical software engineering." *ICSE 2016*, 108-119.

**Only claims in the ``clear_direction`` bucket enter the matrix.** Claims where
no side reached a majority (``mixed``) and claims where a third of the sample
could not answer (``idk_dominant``) are reported in their own summary tables
instead — placing them in a cell would assert a direction the data does not show.
See :mod:`rq3.analysis.buckets` for how the buckets are decided.

Claims whose RQ2 label has not been entered yet keep the ``PENDING`` label and
get their own column. They are never folded into one of the three categories.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..config import Config
from .buckets import (AGREED, CLEAR_DIRECTION, DISAGREED, IDK_DOMINANT,
                      MAJORITY_AGREED, MAJORITY_DISAGREED, MIXED, ClaimBucket)

@dataclass
class ClaimClassification:
    claim_id: str
    bucket: str                      # clear_direction | mixed | idk_dominant
    belief_label: str | None         # "Majority agreed" / "Majority disagreed"
    majority_direction: str | None   # agreed | disagreed | none
    evidence_label: str
    pct_agree: float | None
    pct_disagree: float | None
    pct_neutral: float | None
    directional_n: int
    full_sample_n: int
    idk_rate: float
    in_matrix: bool
    mismatch: bool
    mismatch_kind: str | None
    # Strength qualifier collapsed off the label ("weak evidence", ...). Prose
    # that travels with the claim; never a category of its own.
    evidence_strength: str = ""
    verdict_status: str = "pending"   # match | mismatch | not_scored | pending | excluded
    verdict: str = ""
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class MatrixCell:
    belief_class: str
    evidence_label: str
    count: int
    claim_ids: list[str]
    borderline_claim_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class BeliefEvidenceMatrix:
    idk_dominance_threshold: float
    majority_threshold: float
    bucket_counts: dict[str, int]
    excluded_mixed: list[str]
    excluded_idk_dominant: list[str]
    belief_classes: list[str]
    evidence_labels: list[str]
    cells: list[MatrixCell]
    classifications: list[ClaimClassification]
    n_pending_evidence: int
    n_mismatch: int
    n_match: int = 0
    n_not_scored: int = 0        # NO EVIDENCE FOUND — outside the scoring
    n_scored: int = 0            # match + mismatch, the denominator to quote
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["cells"] = [c.to_dict() for c in self.cells]
        d["classifications"] = [c.to_dict() for c in self.classifications]
        return d


# Which (direction, evidence) combinations count as a belief-evidence mismatch —
# the cells that carry the actual RQ3 finding.
#
# Strength qualifiers are NOT separate categories. "SUPPORTED (weak evidence)"
# is scored exactly as "SUPPORTED": weak evidence still leans toward the claim
# being true, so a majority disagreeing still disagrees with it. The weakness
# qualifies how strongly the finding can be stated, not which direction it
# points; it travels with the claim in `evidence_strength` as prose.
_MISMATCH_RULES = {
    (MAJORITY_AGREED, "CONTRADICTED"):
        "a majority agreed, but the evidence contradicts the claim",
    (MAJORITY_DISAGREED, "SUPPORTED"):
        "a majority disagreed, but the evidence supports the claim",
}
_MATCH_RULES = {
    (MAJORITY_AGREED, "SUPPORTED"):
        "a majority agreed, and the evidence supports the claim",
    (MAJORITY_DISAGREED, "CONTRADICTED"):
        "a majority disagreed, and the evidence contradicts the claim",
}


def _is_unscored(label: str, cfg: Config) -> bool:
    """NO EVIDENCE FOUND is neither a match nor a mismatch.

    With no evidence located there is nothing for a majority to agree or
    disagree with, so scoring it either way would manufacture a finding. Those
    claims keep their own column and sit outside the match/mismatch counts.
    """
    return label in set(cfg.get("belief.unscored_labels"))


def _verdict(b: ClaimBucket, label: str, kind: str | None, pending: str,
             unscored: bool, strength: str, idk_cut: float) -> tuple[str, str]:
    """One plain-language line an examiner can read as the claim's result."""
    if b.bucket == IDK_DOMINANT:
        return "excluded", (
            f"NOT CLASSIFIED — {b.idk_rate:.0%} of the full sample answered "
            f"\"I don't know\", at or above the {idk_cut:.0%} dominance "
            "threshold. No majority direction is computed and the claim is "
            "excluded from the matrix; it is reported in the IDK-dominant table.")
    if b.bucket == MIXED:
        return "excluded", (
            f"NO MAJORITY — {b.pct_agree:.0%} agreed, {b.pct_disagree:.0%} "
            f"disagreed and {b.pct_neutral:.0%} were neutral among the "
            f"{b.directional_n} directional answers. Neither side passed the "
            "majority threshold, so the claim is excluded from the matrix and "
            "reported in the mixed table.")

    stem = (f"A majority {'agreed with' if b.majority_direction == AGREED else 'disagreed with'} "
            f"this claim ({(b.pct_agree if b.majority_direction == AGREED else b.pct_disagree):.0%} "
            f"of {b.directional_n} directional answers)")
    if label == pending:
        return "pending", (
            f"{stem}. No verdict yet: the RQ2 evidence label is still {pending}, "
            "so direction and evidence cannot be compared. Fill "
            "data/claims_evidence.csv to complete this section.")
    qualified = f"{label} ({strength})" if strength else label
    if unscored:
        return "not_scored", (
            f"NOT SCORED — {stem}, but the RQ2 mapping located no evidence "
            f"either way ({qualified}). With nothing to agree or disagree with, "
            "this claim is reported in its own bucket rather than counted as a "
            "match or a mismatch.")
    if kind:
        return "mismatch", (f"MISMATCH — {stem}, but the RQ2 evidence mapping "
                            f"labelled it {qualified}: {kind}.")
    return "match", (f"MATCH — {stem}, consistent with the RQ2 evidence label "
                     f"{qualified}.")


def build_matrix(buckets: list[ClaimBucket], claims: pd.DataFrame,
                 cfg: Config) -> BeliefEvidenceMatrix:
    """Cross-tabulate majority direction against the RQ2 label.

    Only ``clear_direction`` claims enter the grid; ``mixed`` and
    ``idk_dominant`` claims are carried in their own lists.
    """
    pending = str(cfg.get("belief.pending_label"))
    labels = list(cfg.get("belief.evidence_labels"))
    idk_cut = float(cfg.get("belief.idk_dominance.threshold"))
    maj_cut = float(cfg.get("belief.majority.threshold"))

    evidence_by_id = dict(zip(claims["claim_id"], claims["evidence_label"]))
    strength_by_id = (dict(zip(claims["claim_id"], claims["evidence_strength"]))
                      if "evidence_strength" in claims.columns else {})

    classifications: list[ClaimClassification] = []
    for b in buckets:
        label = str(evidence_by_id.get(b.claim_id, pending))
        strength = str(strength_by_id.get(b.claim_id, "") or "")
        in_matrix = b.bucket == CLEAR_DIRECTION
        unscored = in_matrix and _is_unscored(label, cfg)
        kind = (_MISMATCH_RULES.get((b.belief_label, label))
                if in_matrix and not unscored else None)
        status, verdict = _verdict(b, label, kind, pending, unscored, strength, idk_cut)
        classifications.append(ClaimClassification(
            claim_id=b.claim_id, bucket=b.bucket, belief_label=b.belief_label,
            majority_direction=b.majority_direction, evidence_label=label,
            pct_agree=b.pct_agree, pct_disagree=b.pct_disagree,
            pct_neutral=b.pct_neutral, directional_n=b.directional_n,
            full_sample_n=b.full_sample_n, idk_rate=b.idk_rate,
            in_matrix=in_matrix, mismatch=kind is not None, mismatch_kind=kind,
            evidence_strength=strength, verdict_status=status, verdict=verdict,
            reason=b.reason,
        ))

    present_labels = list(labels)
    if any(c.evidence_label == pending and c.in_matrix for c in classifications):
        present_labels.append(pending)
    belief_classes = [MAJORITY_AGREED, MAJORITY_DISAGREED]

    cells: list[MatrixCell] = []
    for bc in belief_classes:
        for lbl in present_labels:
            members = [c for c in classifications
                       if c.in_matrix and c.belief_label == bc
                       and c.evidence_label == lbl]
            cells.append(MatrixCell(
                belief_class=bc, evidence_label=lbl, count=len(members),
                claim_ids=[c.claim_id for c in members],
                borderline_claim_ids=[],
            ))

    counts = {
        CLEAR_DIRECTION: sum(1 for b in buckets if b.bucket == CLEAR_DIRECTION),
        MIXED: sum(1 for b in buckets if b.bucket == MIXED),
        IDK_DOMINANT: sum(1 for b in buckets if b.bucket == IDK_DOMINANT),
    }
    n_pending = sum(1 for c in classifications
                    if c.in_matrix and c.evidence_label == pending)

    notes = [
        f"A claim enters the matrix only when one side passed {maj_cut:.0%} of the "
        "directional answers (the five substantive Likert points; IDK excluded). "
        "Neutral answers count toward that denominator but toward neither side.",
        f"IDK dominance is checked first: at or above {idk_cut:.0%} of the FULL "
        "sample the claim is reported on its own terms and no majority is computed.",
        f"{counts[MIXED]} claim(s) reached no majority and {counts[IDK_DOMINANT]} "
        "were IDK-dominant; both are excluded from the grid and reported separately.",
        f"{', '.join(cfg.get('belief.unscored_labels'))} is not scored as a match "
        "or a mismatch: with no evidence located there is nothing to agree with.",
        "Strength qualifiers (weak / moderate / mixed) are prose carried in "
        "evidence_strength, not a fourth evidence category.",
    ]
    if n_pending:
        notes.append(
            f"{n_pending} claim(s) in the matrix have no RQ2 evidence label yet "
            f"and sit in the '{pending}' column. Fill data/claims_evidence.csv "
            "before reporting.")

    return BeliefEvidenceMatrix(
        idk_dominance_threshold=idk_cut,
        majority_threshold=maj_cut,
        bucket_counts=counts,
        excluded_mixed=[b.claim_id for b in buckets if b.bucket == MIXED],
        excluded_idk_dominant=[b.claim_id for b in buckets if b.bucket == IDK_DOMINANT],
        belief_classes=belief_classes,
        evidence_labels=present_labels,
        cells=cells,
        classifications=classifications,
        n_pending_evidence=n_pending,
        n_mismatch=sum(1 for c in classifications if c.verdict_status == "mismatch"),
        n_match=sum(1 for c in classifications if c.verdict_status == "match"),
        n_not_scored=sum(1 for c in classifications if c.verdict_status == "not_scored"),
        n_scored=sum(1 for c in classifications
                     if c.verdict_status in ("match", "mismatch")),
        notes=notes,
    )
