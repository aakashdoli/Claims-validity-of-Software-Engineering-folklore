"""Stage 2 — subgroup comparisons (and the pairwise follow-ups).

For every (claim x demographic variable) pair:

* two surviving groups   -> Mann-Whitney U  (``scipy.stats.mannwhitneyu``)
* three or more          -> Kruskal-Wallis H (``scipy.stats.kruskal``)

Both are the standard nonparametric choices for ordinal outcomes:

  Wohlin et al. (2012), *Experimentation in Software Engineering*, Ch. 10.
  Kitchenham, B. et al. (2017). "Robust statistical methods for empirical
  software engineering." *Empirical Software Engineering*, 22(2), 579-630.

Formulas are NOT hand-rolled — scipy owns the tie corrections and the normal
approximation. ``method="asymptotic"`` is pinned explicitly so that a run is
deterministic and does not silently switch to the exact test on small,
tie-free subgroups.

Two rules are enforced without exception:

1. A subgroup with fewer than ``comparisons.min_subgroup_size`` valid answers
   is dropped from that claim's comparison, and the drop is recorded as an
   explicit :class:`Exclusion`. (The previous pipeline used a floor of 3, which
   was flagged as a bug; the floor is now config-driven and defaults to 10.)
2. IDK answers never enter the ranked data — but the IDK rate is reported per
   claim per subgroup, because a subgroup that mostly cannot answer a claim is
   itself a finding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from ..config import Config
from .descriptives import count_idk, valid_scores
from .effects import EpsilonSquared, RankBiserial, epsilon_squared, rank_biserial


# Demographics were non-compulsory (Davide's instruction: complete claim data
# matters more than complete demographic data), so every comparison carries a
# row for the respondents who left that question blank.
UNASSIGNED_LABEL = "(not recorded)"


@dataclass
class GroupSummary:
    group: str
    n_total: int          # respondents in this subgroup shown the claim
    n_valid: int          # answered on the 1-5 scale
    n_idk: int
    idk_rate: float
    median: float | None
    mean_rank: float | None
    included: bool
    # Raw counts per scale point, so every downstream number on the claim page
    # traces back to a breakdown shown on the same page.
    frequencies: dict[int, int] = field(default_factory=dict)
    percentages: dict[int, float] = field(default_factory=dict)
    rank_sum: float | None = None
    # Why the subgroup is not in the test: it is below the size floor, or its
    # respondents never gave this demographic and so belong to no subgroup at
    # all. The two are different facts and are never shown as the same one.
    excluded_kind: str | None = None   # "below_min_size" | "unassigned"
    exclusion_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["frequencies"] = {str(k): v for k, v in self.frequencies.items()}
        d["percentages"] = {str(k): v for k, v in self.percentages.items()}
        return d


@dataclass
class TestWorking:
    """The arithmetic behind one test statistic, step by step.

    Reproduced by hand from the rank sums rather than copied out of scipy: the
    test suite asserts these steps land on exactly the statistic and p-value
    scipy returns, so the walkthrough shown to a reader is the real computation
    and not a plausible-looking reconstruction.
    """

    test: str
    steps: list[dict[str, Any]]
    values: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"test": self.test, "steps": self.steps, "values": self.values}


@dataclass
class BHDetail:
    """Where this comparison sat in its Benjamini-Hochberg family."""

    family: str
    family_size: int
    rank_in_family: int
    raw_p: float
    critical_value: float      # (rank / family_size) * alpha
    p_adjusted: float
    significant: bool
    method: str
    alpha: float

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class PairwiseResult:
    group_a: str
    group_b: str
    n_a: int
    n_b: int
    u_statistic: float
    p_value: float
    p_adjusted: float | None = None
    significant_adjusted: bool | None = None
    effect: RankBiserial | None = None

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["effect"] = self.effect.to_dict() if self.effect else None
        return d


@dataclass
class ComparisonResult:
    claim_id: str
    variable: str
    test: str | None                 # "mann_whitney_u" | "kruskal_wallis" | None
    statistic: float | None
    p_value: float | None
    p_adjusted: float | None = None
    significant_adjusted: bool | None = None
    effect: RankBiserial | None = None       # two-group comparisons
    omnibus_effect: EpsilonSquared | None = None  # 3+ group comparisons
    groups: list[GroupSummary] = field(default_factory=list)
    pairwise: list[PairwiseResult] = field(default_factory=list)
    working: TestWorking | None = None
    bh: BHDetail | None = None
    excluded: bool = False
    exclusion_reason: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["effect"] = self.effect.to_dict() if self.effect else None
        d["omnibus_effect"] = self.omnibus_effect.to_dict() if self.omnibus_effect else None
        d["groups"] = [g.to_dict() for g in self.groups]
        d["pairwise"] = [p.to_dict() for p in self.pairwise]
        d["working"] = self.working.to_dict() if self.working else None
        d["bh"] = self.bh.to_dict() if self.bh else None
        return d


@dataclass
class Exclusion:
    """An analysis that did not run, and exactly why. Never silently dropped."""

    scope: str            # "comparison" | "subgroup" | "pairwise"
    claim_id: str
    variable: str
    group: str | None
    reason: str
    n_valid: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _rank_sums(groups: dict[str, np.ndarray]) -> dict[str, float]:
    """Rank sum per group over the pooled, midrank (tie-corrected) ranking."""
    labels = list(groups)
    pooled = np.concatenate([groups[g] for g in labels]) if labels else np.array([])
    if pooled.size == 0:
        return {g: float("nan") for g in labels}
    ranks = stats.rankdata(pooled)
    out: dict[str, float] = {}
    i = 0
    for g in labels:
        n = groups[g].size
        out[g] = float(ranks[i:i + n].sum()) if n else float("nan")
        i += n
    return out


def _tie_term(pooled: np.ndarray) -> float:
    """sum(t^3 - t) over tied groups — the correction both tests need."""
    _, counts = np.unique(pooled, return_counts=True)
    return float(((counts.astype(float) ** 3) - counts).sum())


def _mann_whitney_working(label_a: str, a: np.ndarray, label_b: str,
                          b: np.ndarray, rank_sums: dict[str, float]) -> TestWorking:
    """Mann-Whitney U rebuilt from the rank sums.

    U_i = R_i - n_i(n_i + 1)/2, and the normal approximation with tie and
    continuity corrections. Verified against scipy in the test suite.
    """
    n1, n2 = int(a.size), int(b.size)
    N = n1 + n2
    r1, r2 = rank_sums[label_a], rank_sums[label_b]
    u1 = r1 - n1 * (n1 + 1) / 2
    u2 = r2 - n2 * (n2 + 1) / 2
    mu = n1 * n2 / 2
    tie = _tie_term(np.concatenate([a, b]))
    sigma = float(np.sqrt(n1 * n2 / 12 * ((N + 1) - tie / (N * (N - 1)))))
    u_max = max(u1, u2)
    z = (u_max - mu - 0.5) / sigma
    p = float(min(1.0, 2 * stats.norm.sf(z)))

    steps = [
        {"label": "Pooled midranks",
         "formula": "rank all valid answers together; tied answers share the mean rank",
         "result": f"N = {n1} + {n2} = {N}"},
        {"label": f"Rank sum, {label_a}",
         "formula": f"R₁ = sum of ranks held by {label_a}",
         "result": f"R₁ = {r1:,.1f}"},
        {"label": f"Rank sum, {label_b}",
         "formula": f"R₂ = sum of ranks held by {label_b}",
         "result": f"R₂ = {r2:,.1f}"},
        {"label": "Check",
         "formula": "R₁ + R₂ = N(N+1)/2",
         "result": f"{r1 + r2:,.1f} = {N * (N + 1) / 2:,.1f}"},
        {"label": f"U for {label_a}",
         "formula": f"U₁ = R₁ − n₁(n₁+1)/2 = {r1:,.1f} − {n1}({n1}+1)/2",
         "result": f"U₁ = {u1:,.1f}"},
        {"label": f"U for {label_b}",
         "formula": f"U₂ = R₂ − n₂(n₂+1)/2 = {r2:,.1f} − {n2}({n2}+1)/2",
         "result": f"U₂ = {u2:,.1f}"},
        {"label": "Check",
         "formula": "U₁ + U₂ = n₁ × n₂",
         "result": f"{u1 + u2:,.1f} = {n1 * n2:,}"},
        {"label": "Expected U under H₀",
         "formula": f"μ = n₁n₂/2 = {n1} × {n2} / 2",
         "result": f"μ = {mu:,.1f}"},
        {"label": "Tie correction term",
         "formula": "Σ(t³ − t) over each set of t tied answers",
         "result": f"Σ(t³ − t) = {tie:,.0f}"},
        {"label": "Standard deviation of U",
         "formula": "σ = √[ n₁n₂/12 × ((N+1) − Σ(t³−t)/(N(N−1))) ]",
         "result": f"σ = {sigma:,.3f}"},
        {"label": "z with continuity correction",
         "formula": f"z = (max(U₁,U₂) − μ − 0.5)/σ = ({u_max:,.1f} − {mu:,.1f} − 0.5)/{sigma:,.3f}",
         "result": f"z = {z:,.4f}"},
        {"label": "Two-sided p",
         "formula": "p = 2 × P(Z > z)",
         "result": f"p = {p:.6g}"},
    ]
    return TestWorking(
        test="mann_whitney_u",
        steps=steps,
        values={"n1": n1, "n2": n2, "N": N, "R1": r1, "R2": r2, "U1": u1, "U2": u2,
                "U_reported": u1, "U_max": u_max, "mu": mu, "tie_term": tie,
                "sigma": sigma, "z": z, "p": p,
                "group_a": label_a, "group_b": label_b},
    )


def _kruskal_working(labels: list[str], groups: dict[str, np.ndarray],
                     rank_sums: dict[str, float]) -> TestWorking:
    """Kruskal-Wallis H rebuilt from the rank sums, with the tie correction."""
    k = len(labels)
    N = int(sum(groups[g].size for g in labels))
    term = sum(rank_sums[g] ** 2 / groups[g].size for g in labels)
    h_uncorrected = 12 / (N * (N + 1)) * term - 3 * (N + 1)
    tie = _tie_term(np.concatenate([groups[g] for g in labels]))
    correction = 1 - tie / (N ** 3 - N)
    h = h_uncorrected / correction
    p = float(stats.chi2.sf(h, k - 1))

    per_group = " + ".join(
        f"{rank_sums[g]:,.1f}²/{groups[g].size}" for g in labels)
    steps = [
        {"label": "Pooled midranks",
         "formula": "rank all valid answers across every included subgroup together",
         "result": f"N = {N}, k = {k} subgroups"},
        {"label": "Rank sums",
         "formula": "Rᵢ = sum of ranks held by subgroup i",
         "result": " · ".join(f"{g}: R = {rank_sums[g]:,.1f} (n = {groups[g].size})"
                              for g in labels)},
        {"label": "Σ Rᵢ²/nᵢ",
         "formula": per_group,
         "result": f"{term:,.2f}"},
        {"label": "H before tie correction",
         "formula": f"H = 12/(N(N+1)) × ΣRᵢ²/nᵢ − 3(N+1) = 12/({N}×{N + 1}) × {term:,.2f} − 3×{N + 1}",
         "result": f"H = {h_uncorrected:,.4f}"},
        {"label": "Tie correction",
         "formula": f"C = 1 − Σ(t³−t)/(N³−N) = 1 − {tie:,.0f}/{N ** 3 - N:,}",
         "result": f"C = {correction:,.6f}"},
        {"label": "H corrected",
         "formula": f"H = {h_uncorrected:,.4f} / {correction:,.6f}",
         "result": f"H = {h:,.4f}"},
        {"label": "p from χ²",
         "formula": f"p = P(χ²({k - 1}) > {h:,.4f})",
         "result": f"p = {p:.6g}"},
    ]
    return TestWorking(
        test="kruskal_wallis",
        steps=steps,
        values={"N": N, "k": k, "df": k - 1, "sum_R2_over_n": term,
                "H_uncorrected": h_uncorrected, "tie_term": tie,
                "tie_correction": correction, "H": h, "p": p,
                "rank_sums": {g: rank_sums[g] for g in labels},
                "group_sizes": {g: int(groups[g].size) for g in labels}},
    )


def compare_claim(claim_id: str, answers: pd.Series, grouping: pd.Series,
                  variable: str, cfg: Config) -> tuple[ComparisonResult, list[Exclusion]]:
    """Run one (claim x demographic variable) comparison."""
    min_n = cfg.min_subgroup_size
    min_groups = int(cfg.get("comparisons.min_groups"))
    exclusions: list[Exclusion] = []

    frame = pd.DataFrame({"answer": answers, "group": grouping})
    # Demographics were optional, so some respondents belong to no subgroup at
    # all. They are shown as their own row rather than dropped, otherwise the
    # subgroup counts on the claim page would not add up to the overall counts
    # and the page would be quietly lying about its own arithmetic.
    unassigned = frame[frame["group"].isna()]
    frame = frame[frame["group"].notna()]

    summaries: list[GroupSummary] = []
    usable: dict[str, np.ndarray] = {}

    scale = cfg.likert_values
    for group, chunk in frame.groupby("group", sort=True):
        group = str(group)
        x = valid_scores(chunk["answer"])
        n_idk = count_idk(chunk["answer"])
        n_total = int(chunk.shape[0])
        freqs = {v: int((x == v).sum()) for v in scale}
        pcts = {v: (freqs[v] / x.size * 100 if x.size else 0.0) for v in scale}
        common = dict(
            group=group, n_total=n_total, n_valid=int(x.size), n_idk=n_idk,
            idk_rate=n_idk / n_total if n_total else 0.0,
            frequencies=freqs, percentages=pcts,
        )
        if x.size >= min_n:
            usable[group] = x
            summaries.append(GroupSummary(
                **common, median=float(np.median(x)), mean_rank=None, included=True))
        else:
            reason = (f"only {x.size} valid (non-IDK) answers, below "
                      f"min_subgroup_size={min_n}")
            summaries.append(GroupSummary(
                **common, median=float(np.median(x)) if x.size else None,
                mean_rank=None, included=False,
                excluded_kind="below_min_size", exclusion_reason=reason))
            exclusions.append(Exclusion("subgroup", claim_id, variable, group,
                                        reason, int(x.size)))

    if not unassigned.empty:
        x = valid_scores(unassigned["answer"])
        n_idk = count_idk(unassigned["answer"])
        n_total = int(unassigned.shape[0])
        freqs = {v: int((x == v).sum()) for v in scale}
        reason = (f"{n_total} respondent(s) did not answer the optional "
                  f"'{variable}' question, so they belong to no subgroup and "
                  "cannot enter this comparison")
        summaries.append(GroupSummary(
            group=UNASSIGNED_LABEL, n_total=n_total, n_valid=int(x.size),
            n_idk=n_idk, idk_rate=n_idk / n_total if n_total else 0.0,
            frequencies=freqs,
            percentages={v: (freqs[v] / x.size * 100 if x.size else 0.0) for v in scale},
            median=float(np.median(x)) if x.size else None, mean_rank=None,
            included=False, excluded_kind="unassigned", exclusion_reason=reason))
        exclusions.append(Exclusion("unassigned", claim_id, variable,
                                    UNASSIGNED_LABEL, reason, int(x.size)))

    # Rank sums over the pooled ranking of the INCLUDED subgroups only — the
    # same ranking the test statistic is built from, so the numbers shown on the
    # claim page are the ones that produced the result.
    rank_sums = _rank_sums(usable)
    for s in summaries:
        if s.included:
            s.rank_sum = rank_sums.get(s.group)
            s.mean_rank = (s.rank_sum / s.n_valid) if s.n_valid else None

    if len(usable) < min_groups:
        reason = (f"only {len(usable)} subgroup(s) met min_subgroup_size="
                  f"{min_n}; need at least {min_groups} to run a test")
        exclusions.append(Exclusion("comparison", claim_id, variable, None, reason))
        return ComparisonResult(
            claim_id=claim_id, variable=variable, test=None, statistic=None,
            p_value=None, groups=summaries, excluded=True, exclusion_reason=reason,
        ), exclusions

    labels = list(usable)
    pooled = np.concatenate([usable[g] for g in labels])
    if np.unique(pooled).size == 1:
        # scipy.stats.kruskal raises on a constant input; catch it here and
        # report it as an explicit exclusion instead of letting it surface as
        # a crash or a missing row.
        reason = ("every included subgroup gave the identical single answer "
                  "value; no variance to test")
        exclusions.append(Exclusion("comparison", claim_id, variable, None, reason))
        return ComparisonResult(
            claim_id=claim_id, variable=variable, test=None, statistic=None,
            p_value=None, groups=summaries, excluded=True, exclusion_reason=reason,
        ), exclusions

    if len(labels) == 2:
        a, b = usable[labels[0]], usable[labels[1]]
        # scipy.stats.mannwhitneyu — two-sided, continuity-corrected normal
        # approximation with tie handling. Pinned to "asymptotic" for
        # determinism across subgroup sizes.
        res = stats.mannwhitneyu(a, b, alternative="two-sided", method="asymptotic")
        return ComparisonResult(
            claim_id=claim_id, variable=variable, test="mann_whitney_u",
            statistic=float(res.statistic), p_value=float(res.pvalue),
            effect=rank_biserial(a, b, cfg), groups=summaries,
            working=_mann_whitney_working(labels[0], a, labels[1], b, rank_sums),
            notes=[f"positive effect size favours '{labels[0]}' over '{labels[1]}'"],
        ), exclusions

    # scipy.stats.kruskal — H with tie correction.
    res = stats.kruskal(*[usable[g] for g in labels])
    n_total_valid = int(sum(usable[g].size for g in labels))
    return ComparisonResult(
        claim_id=claim_id, variable=variable, test="kruskal_wallis",
        statistic=float(res.statistic), p_value=float(res.pvalue),
        omnibus_effect=epsilon_squared(float(res.statistic), n_total_valid,
                                       len(labels), cfg),
        groups=summaries,
        working=_kruskal_working(labels, usable, rank_sums),
        notes=["pairwise Mann-Whitney follow-ups run only if this omnibus test "
               "survives Benjamini-Hochberg correction"],
    ), exclusions


def run_pairwise(claim_id: str, answers: pd.Series, grouping: pd.Series,
                 variable: str, included_groups: list[str],
                 cfg: Config) -> list[PairwiseResult]:
    """Pairwise Mann-Whitney follow-ups over the groups that met the size floor."""
    frame = pd.DataFrame({"answer": answers, "group": grouping})
    data = {g: valid_scores(frame.loc[frame["group"] == g, "answer"])
            for g in included_groups}
    out: list[PairwiseResult] = []
    for ga, gb in combinations(sorted(included_groups), 2):
        a, b = data[ga], data[gb]
        if a.size == 0 or b.size == 0:
            continue
        res = stats.mannwhitneyu(a, b, alternative="two-sided", method="asymptotic")
        out.append(PairwiseResult(
            group_a=ga, group_b=gb, n_a=int(a.size), n_b=int(b.size),
            u_statistic=float(res.statistic), p_value=float(res.pvalue),
            effect=rank_biserial(a, b, cfg),
        ))
    return out
