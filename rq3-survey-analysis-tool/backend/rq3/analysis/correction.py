"""Stage 4 — multiple-testing correction.

Benjamini-Hochberg FDR via ``statsmodels.stats.multitest.multipletests`` with
``method="fdr_bh"``:

  Benjamini, Y. & Hochberg, Y. (1995). "Controlling the false discovery rate."
  *Journal of the Royal Statistical Society B*, 57(1), 289-300.

Family definition matters as much as the method. Correction is applied PER
DEMOGRAPHIC-VARIABLE FAMILY: the 50 claims tested within "experience" form one
family, the 50 within "role" another, and so on. Pooling all ~300 comparisons
into a single family would over-correct (every genuine difference vanishes);
skipping correction entirely would manufacture false positives at this many
tests. Both the raw and the adjusted p-value are kept for every comparison so
nothing is hidden behind the correction.

Pairwise follow-ups are corrected separately, within their own
(claim x variable) set, since they are a second, conditional question.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from statsmodels.stats.multitest import multipletests

from ..config import Config
from .comparisons import BHDetail, ComparisonResult, PairwiseResult


@dataclass
class FamilySummary:
    variable: str
    n_tests: int
    n_excluded: int
    n_significant_raw: int
    n_significant_adjusted: int
    method: str
    alpha: float

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def apply_bh(results: list[ComparisonResult], cfg: Config) -> list[FamilySummary]:
    """Correct in place, one family per demographic variable.

    Comparisons that were excluded (no p-value) are counted but never fed into
    the correction — including them would inflate the family size and weaken
    every surviving test.
    """
    method = str(cfg.get("correction.method"))
    alpha = float(cfg.get("correction.alpha"))
    if str(cfg.get("correction.family_scope")) != "per_variable":
        raise ValueError(
            "only correction.family_scope='per_variable' is implemented; "
            "pooling families across variables would over-correct"
        )

    families: dict[str, list[ComparisonResult]] = {}
    for r in results:
        families.setdefault(r.variable, []).append(r)

    summaries: list[FamilySummary] = []
    for variable, members in families.items():
        testable = [m for m in members if m.p_value is not None]
        excluded = len(members) - len(testable)
        if not testable:
            summaries.append(FamilySummary(variable, 0, excluded, 0, 0, method, alpha))
            continue
        pvals = [m.p_value for m in testable]
        reject, p_adj, _, _ = multipletests(pvals, alpha=alpha, method=method)
        # Rank within the family (1 = smallest raw p) and the BH critical value
        # it was compared against, so a reader can redo the step by hand.
        order = sorted(range(len(pvals)), key=lambda i: pvals[i])
        rank_of = {i: pos + 1 for pos, i in enumerate(order)}
        m_size = len(testable)
        for idx, (m, rej, padj) in enumerate(zip(testable, reject, p_adj)):
            m.p_adjusted = float(padj)
            m.significant_adjusted = bool(rej)
            m.bh = BHDetail(
                family=variable,
                family_size=m_size,
                rank_in_family=rank_of[idx],
                raw_p=float(m.p_value),
                critical_value=rank_of[idx] / m_size * alpha,
                p_adjusted=float(padj),
                significant=bool(rej),
                method=method,
                alpha=alpha,
            )
        summaries.append(FamilySummary(
            variable=variable,
            n_tests=len(testable),
            n_excluded=excluded,
            n_significant_raw=sum(1 for p in pvals if p < alpha),
            n_significant_adjusted=int(sum(reject)),
            method=method,
            alpha=alpha,
        ))
    return summaries


def apply_bh_pairwise(pairwise: list[PairwiseResult], cfg: Config) -> None:
    """Correct one claim's pairwise follow-up set in place."""
    if not pairwise:
        return
    if not bool(cfg.get("correction.correct_pairwise_within_claim")):
        for p in pairwise:
            p.p_adjusted = p.p_value
            p.significant_adjusted = p.p_value < float(cfg.get("correction.alpha"))
        return
    method = str(cfg.get("correction.method"))
    alpha = float(cfg.get("correction.alpha"))
    reject, p_adj, _, _ = multipletests([p.p_value for p in pairwise],
                                        alpha=alpha, method=method)
    for p, rej, padj in zip(pairwise, reject, p_adj):
        p.p_adjusted = float(padj)
        p.significant_adjusted = bool(rej)
