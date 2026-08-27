"""Stage 6 — comment retrieval and review prioritisation.

The tool does NOT generate qualitative codes. Inductive content analysis of the
free-text comments stays a human task; what is automated here is retrieval,
grouping and prioritisation, so the reviewer spends their time on the claims
where the comments are most likely to explain a quantitative pattern:

* the claim was flagged bimodal in Stage 1 (comments explain the split);
* a subgroup difference on the claim survived BH correction in Stage 4;
* the claim is a belief-evidence mismatch in Stage 5;
* the claim sits borderline against the belief threshold;
* the claim simply drew an unusual volume of comments.

Weights live in ``config.yaml`` (``comments.priority_weights``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..config import Config
from .comparisons import ComparisonResult
from .descriptives import ClaimDescriptives
from .matrix import BeliefEvidenceMatrix


@dataclass
class CommentEntry:
    respondent_id: str
    answer: str
    comment: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class ClaimComments:
    claim_id: str
    n_comments: int
    priority_score: int
    priority_reasons: list[str]
    comments: list[CommentEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["comments"] = [c.to_dict() for c in self.comments]
        return d


def collect_comments(comments: pd.DataFrame, descriptives: list[ClaimDescriptives],
                     comparisons: list[ComparisonResult],
                     matrix: BeliefEvidenceMatrix, cfg: Config) -> list[ClaimComments]:
    weights = cfg.get("comments.priority_weights")
    high_volume = int(cfg.get("comments.high_volume_threshold"))

    bimodal = {d.claim_id for d in descriptives if d.bimodal}
    significant = {c.claim_id for c in comparisons if c.significant_adjusted}
    mismatched = {c.claim_id for c in matrix.classifications if c.mismatch}
    borderline = {c.claim_id for c in matrix.classifications if c.borderline}

    by_claim: dict[str, list[CommentEntry]] = {}
    if not comments.empty:
        for claim_id, chunk in comments.groupby("claim_id"):
            by_claim[str(claim_id)] = [
                CommentEntry(str(r.respondent_id), str(r.answer), str(r.comment))
                for r in chunk.itertuples()
            ]

    out: list[ClaimComments] = []
    for d in descriptives:
        entries = by_claim.get(d.claim_id, [])
        score = 0
        reasons: list[str] = []
        if d.claim_id in bimodal:
            score += int(weights["bimodal"])
            reasons.append("bimodal answer distribution (Stage 1)")
        if d.claim_id in significant:
            score += int(weights["significant_subgroup_difference"])
            reasons.append("subgroup difference significant after BH correction (Stage 4)")
        if d.claim_id in mismatched:
            score += int(weights["belief_evidence_mismatch"])
            reasons.append("belief-evidence mismatch (Stage 5)")
        if d.claim_id in borderline:
            score += int(weights["borderline_threshold"])
            reasons.append("median borderline against the belief threshold (Stage 5)")
        if len(entries) >= high_volume:
            score += int(weights["high_comment_volume"])
            reasons.append(f"high comment volume (>= {high_volume})")
        out.append(ClaimComments(
            claim_id=d.claim_id, n_comments=len(entries), priority_score=score,
            priority_reasons=reasons, comments=entries,
        ))

    out.sort(key=lambda c: (-c.priority_score, -c.n_comments, c.claim_id))
    return out
