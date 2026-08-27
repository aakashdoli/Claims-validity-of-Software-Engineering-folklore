"""Stage 5 — the belief-evidence matrix.

The core RQ3 output: what the surveyed sample believes, crossed with what the
RQ2 evidence mapping found. Structurally this follows the belief-vs-evidence
framing of

  Devanbu, P., Zimmermann, T. & Bird, C. (2016). "Belief & evidence in
  empirical software engineering." *ICSE 2016*, 108-119.

Two rules protect the classification from looking more certain than it is:

1. ``BELIEF_THRESHOLD`` lives in ``config.yaml`` (``belief.threshold``) and
   NOWHERE else. It is PENDING DAVIDE'S SIGN-OFF and must not be presented as
   a settled methodological choice.
2. Any claim whose median sits within ``belief.borderline_delta`` of the
   threshold is flagged ``borderline``. It still lands in a cell — dropping it
   would hide it — but the cell records it as provisional and the frontend
   marks it for manual review.

Claims whose RQ2 label has not been entered yet keep the ``PENDING`` label and
get their own row block in the matrix. They are never silently folded into one
of the four evidence categories.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..config import Config
from .descriptives import ClaimDescriptives

BELIEVED = "Widely believed"
NOT_BELIEVED = "Not widely believed"
UNCLASSIFIED = "Not classifiable"


@dataclass
class ClaimClassification:
    claim_id: str
    median: float | None
    belief_class: str
    evidence_label: str
    borderline: bool
    distance_from_threshold: float | None
    mismatch: bool           # believed-but-contradicted, or unbelieved-but-supported
    mismatch_kind: str | None
    n_valid: int
    idk_rate: float
    # Strength qualifier collapsed off the label ("weak evidence", "moderate
    # evidence", ...). Reported, but never a matrix category of its own.
    evidence_strength: str = ""
    # A single plain-language verdict line for the claim page. While the RQ2
    # label is PENDING this states that the comparison cannot be made yet — it
    # never guesses a verdict from the belief side alone.
    verdict_status: str = "pending"   # match | mismatch | not_scored | pending | unclassifiable
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
    threshold: float
    borderline_delta: float
    threshold_status: str
    belief_classes: list[str]
    evidence_labels: list[str]
    cells: list[MatrixCell]
    classifications: list[ClaimClassification]
    n_borderline: int
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


# Which (belief, evidence) combinations count as a belief-evidence mismatch —
# the cells that carry the actual RQ3 finding.
#
# Strength qualifiers are NOT separate categories. "SUPPORTED (weak evidence)"
# is scored exactly as "SUPPORTED": weak evidence still leans toward the claim
# being true, so disbelief still disagrees with it. The weakness qualifies how
# strongly the finding can be stated, not which direction it points; it travels
# with the claim in `evidence_strength` and is shown on the claim page.
# (Confirmed as the intended rule, 18 Aug 2026.)
_MISMATCH_RULES = {
    (BELIEVED, "CONTRADICTED"): "believed despite contradicting evidence",
    (NOT_BELIEVED, "SUPPORTED"): "not believed despite supporting evidence",
}
_MATCH_RULES = {
    (BELIEVED, "SUPPORTED"): "believed, and the evidence supports it",
    (NOT_BELIEVED, "CONTRADICTED"): "not believed, and the evidence contradicts it",
}


def _is_unscored(label: str, cfg: Config) -> bool:
    """NO EVIDENCE FOUND is neither a match nor a mismatch.

    With no evidence located there is nothing for belief to agree or disagree
    with, so scoring it either way would manufacture a finding. Those claims
    keep their own column in the matrix and sit outside the match/mismatch
    counts entirely (``belief.unscored_labels``).
    """
    return label in set(cfg.get("belief.unscored_labels"))


def _verdict(d: ClaimDescriptives, belief: str, label: str, kind: str | None,
             threshold: float, pending: str, borderline: bool,
             unscored: bool, strength: str) -> tuple[str, str]:
    """One plain-language line an examiner can read as the claim's result."""
    believed = belief == BELIEVED
    stem = (f"The surveyed sample {'believes' if believed else 'does not believe'} "
            f"this claim (median {d.median:g} "
            f"{'\u2265' if believed else '<'} threshold {threshold:g})")
    if label == pending:
        return "pending", (
            f"{stem}. No verdict yet: the RQ2 evidence label for this claim is "
            f"still {pending}, so belief and evidence cannot be compared. "
            "Fill data/claims_evidence.csv to complete this section.")

    qualified = f"{label} ({strength})" if strength else label
    tail = (" This placement is provisional \u2014 the median sits inside the "
            "borderline band around the threshold." if borderline else "")

    if unscored:
        return "not_scored", (
            f"NOT SCORED \u2014 {stem}, but the RQ2 mapping located no evidence "
            f"either way ({qualified}). With nothing to agree or disagree with, "
            "this claim is reported in its own bucket rather than counted as a "
            f"match or a mismatch.{tail}")
    if kind:
        return "mismatch", (
            f"MISMATCH \u2014 {stem}, but the RQ2 evidence mapping labelled it "
            f"{qualified}: {kind}.{tail}")
    return "match", (
        f"MATCH \u2014 {stem}, consistent with the RQ2 evidence label "
        f"{qualified}.{tail}")


def build_matrix(descriptives: list[ClaimDescriptives], claims: pd.DataFrame,
                 cfg: Config) -> BeliefEvidenceMatrix:
    threshold = cfg.belief_threshold
    delta = float(cfg.get("belief.borderline_delta"))
    pending = str(cfg.get("belief.pending_label"))
    labels = list(cfg.get("belief.evidence_labels"))

    evidence_by_id = dict(zip(claims["claim_id"], claims["evidence_label"]))
    strength_by_id = (dict(zip(claims["claim_id"], claims["evidence_strength"]))
                      if "evidence_strength" in claims.columns else {})
    classifications: list[ClaimClassification] = []

    for d in descriptives:
        label = str(evidence_by_id.get(d.claim_id, pending))
        if d.median is None:
            classifications.append(ClaimClassification(
                claim_id=d.claim_id, median=None, belief_class=UNCLASSIFIED,
                evidence_label=label, borderline=False,
                distance_from_threshold=None, mismatch=False, mismatch_kind=None,
                n_valid=d.n_valid, idk_rate=d.idk_rate,
                evidence_strength=str(strength_by_id.get(d.claim_id, "") or ""),
                verdict_status="unclassifiable",
                verdict=("No verdict: this claim has no answers on the 1-5 scale, "
                         "so no median and no belief classification exist."),
                reason=d.exclusion_reason or "no valid answers to compute a median",
            ))
            continue
        belief = BELIEVED if d.median >= threshold else NOT_BELIEVED
        distance = abs(d.median - threshold)
        borderline = distance <= delta
        strength = str(strength_by_id.get(d.claim_id, "") or "")
        unscored = _is_unscored(label, cfg)
        kind = None if unscored else _MISMATCH_RULES.get((belief, label))
        status, verdict = _verdict(d, belief, label, kind, threshold, pending,
                                   borderline, unscored, strength)
        classifications.append(ClaimClassification(
            claim_id=d.claim_id, median=d.median, belief_class=belief,
            evidence_label=label, borderline=borderline,
            distance_from_threshold=distance, mismatch=kind is not None,
            mismatch_kind=kind, n_valid=d.n_valid, idk_rate=d.idk_rate,
            evidence_strength=strength, verdict_status=status, verdict=verdict,
            reason=("median is within borderline_delta of the belief threshold; "
                    "classification is provisional and needs manual review"
                    if borderline else None),
        ))

    present_labels = list(labels)
    if any(c.evidence_label == pending for c in classifications):
        present_labels.append(pending)
    belief_classes = [BELIEVED, NOT_BELIEVED]
    if any(c.belief_class == UNCLASSIFIED for c in classifications):
        belief_classes.append(UNCLASSIFIED)

    cells: list[MatrixCell] = []
    for bc in belief_classes:
        for lbl in present_labels:
            members = [c for c in classifications
                       if c.belief_class == bc and c.evidence_label == lbl]
            cells.append(MatrixCell(
                belief_class=bc, evidence_label=lbl, count=len(members),
                claim_ids=[c.claim_id for c in members],
                borderline_claim_ids=[c.claim_id for c in members if c.borderline],
            ))

    notes = [
        f"belief.threshold = {threshold} is a PLACEHOLDER pending Davide's "
        "sign-off; it is read from config.yaml and appears nowhere else in the code.",
        f"claims with a median within {delta} of the threshold are marked "
        "borderline — they are placed in a cell but the placement is provisional.",
    ]
    unscored_labels = list(cfg.get("belief.unscored_labels"))
    notes.append(
        f"{', '.join(unscored_labels)} is not scored as a match or a mismatch: "
        "with no evidence located there is nothing for belief to agree or "
        "disagree with. Those claims keep their own matrix column and sit "
        "outside the match/mismatch counts.")
    notes.append(
        "Strength qualifiers (weak / moderate / mixed) are collapsed onto the "
        "base label and reported in evidence_strength; they are not separate "
        "matrix categories.")
    n_pending = sum(1 for c in classifications if c.evidence_label == pending)
    if n_pending:
        notes.append(
            f"{n_pending} of {len(classifications)} claims have no RQ2 evidence "
            f"label yet and sit in the '{pending}' column. Fill "
            "data/claims_evidence.csv before reporting this matrix."
        )

    return BeliefEvidenceMatrix(
        threshold=threshold,
        borderline_delta=delta,
        threshold_status="PENDING SUPERVISOR SIGN-OFF — not a final value",
        belief_classes=belief_classes,
        evidence_labels=present_labels,
        cells=cells,
        classifications=classifications,
        n_borderline=sum(1 for c in classifications if c.borderline),
        n_pending_evidence=n_pending,
        n_mismatch=sum(1 for c in classifications if c.verdict_status == "mismatch"),
        n_match=sum(1 for c in classifications if c.verdict_status == "match"),
        n_not_scored=sum(1 for c in classifications if c.verdict_status == "not_scored"),
        n_scored=sum(1 for c in classifications
                     if c.verdict_status in ("match", "mismatch")),
        notes=notes,
    )
