"""Stage 2b — the experience comparison, as a genuine two-group test.

The survey collected four ordered bands, not continuous years, so a cut can only
fall on a band boundary. **No band breaks at five years**, which is why no
five-year split exists anywhere in this module: the data cannot support one.
The split used is at ten years, the only boundary that leaves both groups large
enough to test:

    Group 1 "Under 10 years"  =  Less than 1 year + 1 to 3 years + 4 to 9 years
    Group 2 "10+ years"       =  10+ years

Per claim: Mann-Whitney U (``scipy.stats.mannwhitneyu``, two-sided, asymptotic
so a run is deterministic), with IDK excluded — it is not a point on the ordinal
scale and cannot be ranked.

That yields one family of 50 p-values, corrected together with Benjamini-Hochberg
(``statsmodels``). Effect size is computed **only** for claims that survive that
correction: rank-biserial correlation, Kerby's simple difference formula.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

from ..config import Config
from .descriptives import count_idk, valid_scores
from .effects import RankBiserial, rank_biserial


@dataclass
class ExperienceResult:
    claim_id: str
    group_1_label: str
    group_2_label: str
    group_1_n: int              # directional answers only, IDK excluded
    group_2_n: int
    group_1_idk: int
    group_2_idk: int
    group_1_median: float | None
    group_2_median: float | None
    u_statistic: float | None
    p_raw: float | None
    p_corrected: float | None = None
    significant_after_correction: bool = False
    # Kerby rank-biserial — populated ONLY where the corrected p is significant.
    effect: RankBiserial | None = None
    tested: bool = True
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["effect"] = self.effect.to_dict() if self.effect else None
        return d


@dataclass
class ExperienceFamily:
    variable: str
    group_1_label: str
    group_2_label: str
    group_1_total: int          # respondents in the band, across the survey
    group_2_total: int
    results: list[ExperienceResult]
    n_tested: int
    n_significant_raw: int
    n_significant_corrected: int
    method: str
    alpha: float
    unassigned_n: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["results"] = [r.to_dict() for r in self.results]
        return d


def assign_groups(experience: pd.Series, cfg: Config) -> pd.Series:
    """Map each respondent's band onto group 1, group 2, or NA.

    A band that appears in the data but in neither list is left unassigned
    rather than being folded into a group by guesswork.
    """
    spec = cfg.get("experience_split")
    g1, g2 = spec["group_1"], spec["group_2"]
    lookup = {band: g1["label"] for band in g1["bands"]}
    lookup.update({band: g2["label"] for band in g2["bands"]})
    return experience.map(lambda v: lookup.get(v) if pd.notna(v) else None)


def compare(responses: pd.DataFrame, claim_ids: list[str],
            cfg: Config) -> ExperienceFamily:
    spec = cfg.get("experience_split")
    var = str(spec["variable"])
    g1_label, g2_label = spec["group_1"]["label"], spec["group_2"]["label"]
    min_n = cfg.min_subgroup_size
    alpha = float(cfg.get("correction.alpha"))
    method = str(cfg.get("correction.method"))

    groups = assign_groups(responses[var], cfg)
    known_bands = set(spec["group_1"]["bands"]) | set(spec["group_2"]["bands"])
    seen = {str(v) for v in responses[var].dropna().unique()}
    notes: list[str] = []
    stray = sorted(seen - known_bands)
    if stray:
        notes.append(f"bands present in the data but assigned to neither group: "
                     f"{', '.join(stray)}")

    results: list[ExperienceResult] = []
    for claim_id in claim_ids:
        answers = responses[claim_id]
        a_mask, b_mask = groups == g1_label, groups == g2_label
        a, b = valid_scores(answers[a_mask]), valid_scores(answers[b_mask])
        common = dict(
            claim_id=claim_id, group_1_label=g1_label, group_2_label=g2_label,
            group_1_n=int(a.size), group_2_n=int(b.size),
            group_1_idk=count_idk(answers[a_mask]),
            group_2_idk=count_idk(answers[b_mask]),
            group_1_median=float(np.median(a)) if a.size else None,
            group_2_median=float(np.median(b)) if b.size else None,
        )
        if a.size < min_n or b.size < min_n:
            results.append(ExperienceResult(
                **common, u_statistic=None, p_raw=None, tested=False,
                reason=(f"group sizes {a.size}/{b.size} — one is below the "
                        f"minimum of {min_n} directional answers"),
            ))
            continue
        if np.unique(np.concatenate([a, b])).size == 1:
            results.append(ExperienceResult(
                **common, u_statistic=None, p_raw=None, tested=False,
                reason="every respondent in both groups gave the same answer; "
                       "no variance to test",
            ))
            continue
        res = stats.mannwhitneyu(a, b, alternative="two-sided", method="asymptotic")
        results.append(ExperienceResult(
            **common, u_statistic=float(res.statistic), p_raw=float(res.pvalue)))

    # --- one BH family across the 50 claims ---
    testable = [r for r in results if r.p_raw is not None]
    if testable:
        reject, p_adj, _, _ = multipletests([r.p_raw for r in testable],
                                            alpha=alpha, method=method)
        for r, rej, padj in zip(testable, reject, p_adj):
            r.p_corrected = float(padj)
            r.significant_after_correction = bool(rej)

    # --- effect size ONLY where the corrected p survives ---
    for r in results:
        if not r.significant_after_correction:
            continue
        a_mask, b_mask = groups == g1_label, groups == g2_label
        r.effect = rank_biserial(valid_scores(responses[r.claim_id][a_mask]),
                                 valid_scores(responses[r.claim_id][b_mask]), cfg)

    return ExperienceFamily(
        variable=var, group_1_label=g1_label, group_2_label=g2_label,
        group_1_total=int((groups == g1_label).sum()),
        group_2_total=int((groups == g2_label).sum()),
        results=results, n_tested=len(testable),
        n_significant_raw=sum(1 for r in testable if r.p_raw < alpha),
        n_significant_corrected=sum(1 for r in results
                                    if r.significant_after_correction),
        method=method, alpha=alpha,
        unassigned_n=int(groups.isna().sum()),
        notes=notes,
    )
