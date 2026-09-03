"""Stage 5a — bucket every claim by the direction a majority took.

This replaces the earlier median >= 3.5 rule outright. A median forced every
claim onto one side of a single cut point, so a claim answered 40% disagree /
20% neutral / 40% agree landed in the same bucket as one nobody disputed. The
rule here reports what actually happened: a majority went one way, or it did
not.

Two denominators, used for two different things — the distinction is the whole
point of this module:

**Directional denominator** — respondents who chose one of the five substantive
Likert points. IDK is excluded. This is what the majority rule divides by.
Neutral counts toward it but toward *neither* side, so a claim can have no
majority in either direction.

**Full-sample denominator** — every respondent shown the claim, IDK included.
Used only for the IDK-dominance rule.

Order of operations matters. IDK dominance is checked FIRST and short-circuits:
once a third of the sample says it cannot answer, the directional split among
those who remain describes a self-selected minority, so no majority is computed
at all and the claim is reported on its own terms.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from ..config import Config
from .descriptives import ClaimDescriptives

# The three buckets. Mutually exclusive and exhaustive.
CLEAR_DIRECTION = "clear_direction"
MIXED = "mixed"
IDK_DOMINANT = "idk_dominant"

# Direction within the clear_direction bucket.
AGREED = "agreed"
DISAGREED = "disagreed"
NONE = "none"

MAJORITY_AGREED = "Majority agreed"
MAJORITY_DISAGREED = "Majority disagreed"


@dataclass
class ClaimBucket:
    claim_id: str

    # --- denominators, kept side by side so neither can be mistaken for the other
    full_sample_n: int          # every respondent shown the claim, IDK included
    directional_n: int          # respondents who answered on the 1-5 scale
    idk_n: int
    idk_rate: float             # idk_n / full_sample_n

    # --- directional shares, as a proportion of directional_n
    pct_agree: float | None     # answers 4-5
    pct_disagree: float | None  # answers 1-2
    pct_neutral: float | None   # answer 3 — counts toward neither side

    bucket: str                 # clear_direction | mixed | idk_dominant
    majority_agreed: bool | None
    majority_disagreed: bool | None
    majority_direction: str | None   # agreed | disagreed | none
    belief_label: str | None         # "Majority agreed" / "Majority disagreed"
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def classify(d: ClaimDescriptives, cfg: Config) -> ClaimBucket:
    """Bucket one claim. IDK dominance first, then the majority rule."""
    idk_cut = float(cfg.get("belief.idk_dominance.threshold"))
    maj_cut = float(cfg.get("belief.majority.threshold"))

    full_n = d.n_total
    directional_n = d.n_valid
    idk_rate = (d.n_idk / full_n) if full_n else 0.0

    base = dict(
        claim_id=d.claim_id, full_sample_n=full_n, directional_n=directional_n,
        idk_n=d.n_idk, idk_rate=idk_rate,
    )

    # --- 1. IDK dominance, on the FULL sample. Short-circuits everything else.
    if idk_rate >= idk_cut:
        return ClaimBucket(
            **base, pct_agree=None, pct_disagree=None, pct_neutral=None,
            bucket=IDK_DOMINANT, majority_agreed=None, majority_disagreed=None,
            majority_direction=None, belief_label=None,
            reason=(f"{idk_rate:.1%} of the full sample answered "
                    f"\"I don't know\", at or above the {idk_cut:.0%} dominance "
                    "threshold; no majority is computed and the claim is "
                    "excluded from the belief-evidence matrix"),
        )

    # --- 2. Nothing to divide by.
    if directional_n == 0:
        return ClaimBucket(
            **base, pct_agree=None, pct_disagree=None, pct_neutral=None,
            bucket=MIXED, majority_agreed=False, majority_disagreed=False,
            majority_direction=NONE, belief_label=None,
            reason="no answers on the 1-5 scale, so no direction can be read",
        )

    # --- 3. Majority rule, on the DIRECTIONAL denominator.
    agree_n = d.frequencies.get(4, 0) + d.frequencies.get(5, 0)
    disagree_n = d.frequencies.get(1, 0) + d.frequencies.get(2, 0)
    neutral_n = d.frequencies.get(3, 0)

    pct_agree = agree_n / directional_n
    pct_disagree = disagree_n / directional_n
    pct_neutral = neutral_n / directional_n

    agreed = pct_agree > maj_cut
    disagreed = pct_disagree > maj_cut

    shares = dict(pct_agree=pct_agree, pct_disagree=pct_disagree,
                  pct_neutral=pct_neutral)

    if agreed:
        return ClaimBucket(
            **base, **shares, bucket=CLEAR_DIRECTION, majority_agreed=True,
            majority_disagreed=False, majority_direction=AGREED,
            belief_label=MAJORITY_AGREED,
            reason=(f"{pct_agree:.1%} of the {directional_n} directional "
                    f"answers agreed, above the {maj_cut:.0%} threshold"),
        )
    if disagreed:
        return ClaimBucket(
            **base, **shares, bucket=CLEAR_DIRECTION, majority_agreed=False,
            majority_disagreed=True, majority_direction=DISAGREED,
            belief_label=MAJORITY_DISAGREED,
            reason=(f"{pct_disagree:.1%} of the {directional_n} directional "
                    f"answers disagreed, above the {maj_cut:.0%} threshold"),
        )
    return ClaimBucket(
        **base, **shares, bucket=MIXED, majority_agreed=False,
        majority_disagreed=False, majority_direction=NONE, belief_label=None,
        reason=(f"neither side passed {maj_cut:.0%}: {pct_agree:.1%} agreed, "
                f"{pct_disagree:.1%} disagreed, {pct_neutral:.1%} neutral "
                "(neutral counts toward the denominator but toward neither side)"),
    )


def classify_all(descriptives: list[ClaimDescriptives],
                 cfg: Config) -> list[ClaimBucket]:
    return [classify(d, cfg) for d in descriptives]


def bucket_counts(buckets: list[ClaimBucket]) -> dict[str, int]:
    return {
        CLEAR_DIRECTION: sum(1 for b in buckets if b.bucket == CLEAR_DIRECTION),
        MIXED: sum(1 for b in buckets if b.bucket == MIXED),
        IDK_DOMINANT: sum(1 for b in buckets if b.bucket == IDK_DOMINANT),
    }


def role_breakdown(answers: pd.Series, roles: pd.Series,
                   cfg: Config) -> list[dict[str, Any]]:
    """Descriptive counts by role. No test — role has too many categories.

    Reported only for clear_direction claims, per the analysis plan.
    """
    scale = cfg.likert_values
    frame = pd.DataFrame({"answer": answers, "role": roles})
    out: list[dict[str, Any]] = []
    for role, chunk in frame.groupby(frame["role"].fillna("(not recorded)"), sort=True):
        vals = chunk["answer"].astype(str)
        freqs = {v: int((vals == str(v)).sum()) for v in scale}
        idk = int((vals == "IDK").sum())
        directional = sum(freqs.values())
        agree = freqs.get(4, 0) + freqs.get(5, 0)
        disagree = freqs.get(1, 0) + freqs.get(2, 0)
        out.append({
            "role": str(role),
            "n_total": int(chunk.shape[0]),
            "directional_n": directional,
            "idk_n": idk,
            "idk_pct": (idk / chunk.shape[0] * 100) if chunk.shape[0] else 0.0,
            "frequencies": {str(k): v for k, v in freqs.items()},
            "pct_agree": (agree / directional * 100) if directional else None,
            "pct_disagree": (disagree / directional * 100) if directional else None,
            "pct_neutral": (freqs.get(3, 0) / directional * 100) if directional else None,
        })
    return sorted(out, key=lambda r: -r["n_total"])
