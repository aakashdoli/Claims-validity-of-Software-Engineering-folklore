"""Stage 1 — per-claim descriptive statistics.

Individual Likert items are ORDINAL, not interval, so the central-tendency
statistic reported here is the median, never the mean:

  Wohlin, C., Runeson, P., Host, M., Ohlsson, M. C., Regnell, B. & Wesslen, A.
  (2012). *Experimentation in Software Engineering*. Springer. Ch. 10.
  Allen, I. E. & Seaman, C. A. (2007). "Likert Scales and Data Analyses."
  *Quality Progress*, 40(7), 64-65.

The median alone hides disagreement: a claim split 40/40 between disagree and
agree has the same median as one where everybody sits at "neither". Every claim
therefore also carries a bimodality flag (thresholds in ``config.yaml``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..config import Config

IDK = "IDK"


@dataclass
class BimodalityCheck:
    """One condition of the bimodality rule, with the numbers behind it.

    Carried through to the UI so a reader sees the observed value against the
    configured threshold, not just a boolean flag.
    """

    name: str
    observed: float
    comparator: str          # ">=" or "<=" or ">"
    threshold: float
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class BimodalityAssessment:
    rule: str
    assessed: bool
    n_valid: int
    min_valid_n: int
    lower_tail_pct: float | None      # % of valid answers in {1, 2}
    middle_pct: float | None          # % of valid answers equal to 3
    upper_tail_pct: float | None      # % of valid answers in {4, 5}
    coefficient: float | None         # Sarle's BC
    coefficient_threshold: float
    heuristic_pass: bool
    coefficient_pass: bool
    flag: bool
    checks: list[BimodalityCheck]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["checks"] = [c.to_dict() for c in self.checks]
        return d


@dataclass
class ClaimDescriptives:
    claim_id: str
    n_total: int                    # respondents shown the claim
    n_valid: int                    # answered on the 1-5 scale
    n_idk: int
    n_missing: int
    idk_rate: float                 # n_idk / n_total
    frequencies: dict[int, int]     # raw counts per scale point
    percentages: dict[int, float]   # % of n_valid
    median: float | None
    mode: list[int]
    q1: float | None
    q3: float | None
    iqr: float | None
    agree_pct: float | None         # % of valid answers in {4, 5}
    disagree_pct: float | None      # % of valid answers in {1, 2}
    neutral_pct: float | None       # % of valid answers equal to 3
    bimodal: bool
    bimodality_reason: str
    bimodality_coefficient: float | None
    bimodality: BimodalityAssessment
    excluded: bool = False
    exclusion_reason: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["frequencies"] = {str(k): v for k, v in self.frequencies.items()}
        d["percentages"] = {str(k): v for k, v in self.percentages.items()}
        d["bimodality"] = self.bimodality.to_dict()
        return d


def valid_scores(series: pd.Series) -> np.ndarray:
    """Ordinal scores with IDK and missing removed.

    This is THE single implementation of the IDK rule for every numeric
    operation in the tool (see ``idk_rule`` in config.yaml). No stage may
    filter IDK any other way.
    """
    s = series.dropna()
    s = s[s.astype(str) != IDK]
    if s.empty:
        return np.array([], dtype=float)
    return pd.to_numeric(s, errors="coerce").dropna().to_numpy(dtype=float)


def count_idk(series: pd.Series) -> int:
    return int((series.astype(str) == IDK).sum())


def sarle_bimodality_coefficient(x: np.ndarray) -> float | None:
    """Sarle's BC = (skew^2 + 1) / (kurtosis + 3(n-1)^2 / ((n-2)(n-3))).

    SAS Institute (1990), *SAS/STAT User's Guide*. Values above ~0.555 (the
    value for a uniform distribution) are conventionally read as suggestive of
    bimodality. Reported as a CROSS-CHECK only: BC is known to be unreliable on
    coarse discrete scales, so it does not drive the flag.
    """
    n = x.size
    if n < 4:
        return None
    m = x.mean()
    s = x.std(ddof=1)
    if s == 0:
        return None
    z = (x - m) / s
    skew = float((z ** 3).sum() * n / ((n - 1) * (n - 2)))
    g2 = float((z ** 4).sum() * n * (n + 1) / ((n - 1) * (n - 2) * (n - 3))
               - 3 * (n - 1) ** 2 / ((n - 2) * (n - 3)))
    denom = g2 + 3 * (n - 1) ** 2 / ((n - 2) * (n - 3))
    if denom == 0:
        return None
    return (skew ** 2 + 1) / denom


def _assess_bimodality(x: np.ndarray, cfg: Config) -> BimodalityAssessment:
    b = cfg.get("descriptives.bimodality")
    rule = str(b["rule"])
    min_n = int(b["min_valid_n"])
    bc_threshold = float(b["coefficient_threshold"])

    if x.size < min_n:
        reason = f"not assessed: only {x.size} valid answers (< min_valid_n={min_n})"
        return BimodalityAssessment(
            rule=rule, assessed=False, n_valid=int(x.size), min_valid_n=min_n,
            lower_tail_pct=None, middle_pct=None, upper_tail_pct=None,
            coefficient=None, coefficient_threshold=bc_threshold,
            heuristic_pass=False, coefficient_pass=False, flag=False,
            checks=[], reason=reason,
        )

    lower = float(np.isin(x, [1, 2]).sum()) / x.size * 100
    upper = float(np.isin(x, [4, 5]).sum()) / x.size * 100
    middle = float((x == 3).sum()) / x.size * 100
    bc = sarle_bimodality_coefficient(x)

    checks = [
        BimodalityCheck("lower tail (answers 1-2)", lower, ">=",
                        float(b["min_lower_tail_pct"]),
                        lower >= float(b["min_lower_tail_pct"])),
        BimodalityCheck("upper tail (answers 4-5)", upper, ">=",
                        float(b["min_upper_tail_pct"]),
                        upper >= float(b["min_upper_tail_pct"])),
        BimodalityCheck("middle (answer 3)", middle, "<=",
                        float(b["max_middle_pct"]),
                        middle <= float(b["max_middle_pct"])),
    ]
    if bc is not None:
        checks.append(BimodalityCheck("Sarle's bimodality coefficient", bc, ">",
                                      bc_threshold, bc > bc_threshold))

    heuristic = all(c.passed for c in checks[:3])
    coefficient = bc is not None and bc > bc_threshold

    if rule == "tail_middle":
        flag = heuristic
    elif rule == "coefficient":
        flag = coefficient
    elif rule == "both":
        flag = heuristic and coefficient
    else:  # pragma: no cover - validated at config load
        raise ValueError(f"unknown bimodality rule: {rule}")

    detail = (f"tails {lower:.1f}%/{upper:.1f}% vs thresholds "
              f"{b['min_lower_tail_pct']}%/{b['min_upper_tail_pct']}%, "
              f"middle {middle:.1f}% vs max {b['max_middle_pct']}%"
              + (f", BC={bc:.3f} vs {bc_threshold}" if bc is not None else ""))

    return BimodalityAssessment(
        rule=rule, assessed=True, n_valid=int(x.size), min_valid_n=min_n,
        lower_tail_pct=lower, middle_pct=middle, upper_tail_pct=upper,
        coefficient=bc, coefficient_threshold=bc_threshold,
        heuristic_pass=heuristic, coefficient_pass=coefficient, flag=flag,
        checks=checks,
        reason=("bimodal: " if flag else "not bimodal: ") + detail,
    )


def describe_claim(claim_id: str, series: pd.Series, cfg: Config) -> ClaimDescriptives:
    scale = cfg.likert_values
    n_total = int(series.size)
    n_idk = count_idk(series)
    n_missing = int(series.isna().sum())
    x = valid_scores(series)
    n_valid = int(x.size)
    idk_rate = n_idk / n_total if n_total else 0.0

    freqs = {v: int((x == v).sum()) for v in scale}
    pcts = {v: (freqs[v] / n_valid * 100 if n_valid else 0.0) for v in scale}
    assessment = _assess_bimodality(x, cfg)

    if n_valid == 0:
        return ClaimDescriptives(
            claim_id=claim_id, n_total=n_total, n_valid=0, n_idk=n_idk,
            n_missing=n_missing, idk_rate=idk_rate,
            frequencies=freqs, percentages=pcts, median=None, mode=[], q1=None,
            q3=None, iqr=None, agree_pct=None, disagree_pct=None,
            neutral_pct=None, bimodal=False,
            bimodality_reason=assessment.reason,
            bimodality_coefficient=None, bimodality=assessment,
            excluded=True,
            exclusion_reason="no answers on the 1-5 scale (all IDK or missing)",
        )

    top = max(freqs.values())
    q1, q3 = (float(np.percentile(x, 25)), float(np.percentile(x, 75)))

    return ClaimDescriptives(
        claim_id=claim_id,
        n_total=n_total,
        n_valid=n_valid,
        n_idk=n_idk,
        n_missing=n_missing,
        idk_rate=idk_rate,
        frequencies=freqs,
        percentages=pcts,
        median=float(np.median(x)),
        mode=[v for v in scale if freqs[v] == top],
        q1=q1,
        q3=q3,
        iqr=q3 - q1,
        agree_pct=pcts[4] + pcts[5],
        disagree_pct=pcts[1] + pcts[2],
        neutral_pct=pcts[3],
        bimodal=assessment.flag,
        bimodality_reason=assessment.reason,
        bimodality_coefficient=assessment.coefficient,
        bimodality=assessment,
    )


def describe_all(responses: pd.DataFrame, claim_ids: list[str],
                 cfg: Config) -> list[ClaimDescriptives]:
    return [describe_claim(cid, responses[cid], cfg) for cid in claim_ids]
