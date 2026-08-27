"""Stage 3 — effect sizes.

Rank-biserial correlation, Kerby's *simple difference formula*:

  Kerby, D. S. (2014). "The simple difference formula: An approach to teaching
  nonparametric correlation." *Comprehensive Psychology*, 3, 11.IT.3.1.

    r = f - u

where ``f`` is the proportion of all cross-group pairs favouring group A and
``u`` the proportion favouring group B. Tied pairs are split evenly between the
two, which makes the formula identical to ``r = 2U / (n1 * n2) - 1`` computed
from the Mann-Whitney U statistic — the tests assert both routes agree.

The raw pair counts (favourable / unfavourable / tied) are carried alongside
the coefficient so any reported effect size can be audited, not just trusted.

Interpretation thresholds come from:

  Romano, J., Kromrey, J. D., Coraggio, J. & Skowronek, J. (2006). "Appropriate
  statistics for ordinal level data." Florida Association of Institutional
  Research.

Kruskal-Wallis omnibus tests have no rank-biserial analogue (it is defined for
two groups only), so those report epsilon-squared instead — see
``epsilon_squared`` — and the pairwise Mann-Whitney follow-ups carry the
rank-biserial values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..config import Config


@dataclass
class RankBiserial:
    r: float
    favourable_pairs: float
    unfavourable_pairs: float
    tied_pairs: float
    total_pairs: int
    magnitude: str
    direction: str
    formula: str = "Kerby (2014) simple difference: r = f - u, ties split evenly"

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class EpsilonSquared:
    epsilon_squared: float
    h_statistic: float
    n: int
    k_groups: int
    magnitude: str
    formula: str = "epsilon^2 = (H - k + 1) / (n - k); Tomczak & Tomczak (2014)"
    field_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _magnitude(abs_r: float, cfg: Config) -> str:
    t = cfg.get("effect_size.thresholds")
    if abs_r > float(t["large"]):
        return "large"
    if abs_r >= float(t["medium"]):
        return "medium"
    if abs_r >= float(t["small"]):
        return "small"
    return "negligible"


def rank_biserial(a: np.ndarray, b: np.ndarray, cfg: Config) -> RankBiserial:
    """Rank-biserial correlation for group ``a`` versus group ``b``.

    Positive r means group ``a`` tends to score HIGHER than group ``b``.

    Pair counts are computed exactly from the joint frequency table rather than
    by enumerating n1*n2 pairs: the scale is discrete (1-5), so the table is
    small and the result is exact, not approximate.
    """
    n1, n2 = a.size, b.size
    if n1 == 0 or n2 == 0:
        raise ValueError("rank_biserial requires both groups to be non-empty")

    values = np.union1d(np.unique(a), np.unique(b))
    ca = {v: int((a == v).sum()) for v in values}
    cb = {v: int((b == v).sum()) for v in values}

    favourable = 0.0   # a > b
    unfavourable = 0.0  # a < b
    tied = 0.0
    for va in values:
        if not ca[va]:
            continue
        for vb in values:
            if not cb[vb]:
                continue
            pairs = ca[va] * cb[vb]
            if va > vb:
                favourable += pairs
            elif va < vb:
                unfavourable += pairs
            else:
                tied += pairs

    total = n1 * n2
    # Ties split evenly: half to each side (Kerby 2014).
    f = (favourable + tied / 2) / total
    u = (unfavourable + tied / 2) / total
    r = f - u
    return RankBiserial(
        r=float(r),
        favourable_pairs=float(favourable),
        unfavourable_pairs=float(unfavourable),
        tied_pairs=float(tied),
        total_pairs=int(total),
        magnitude=_magnitude(abs(r), cfg),
        direction=("higher in first group" if r > 0
                   else "higher in second group" if r < 0 else "no difference"),
    )


def rank_biserial_from_u(u_statistic: float, n1: int, n2: int, cfg: Config) -> float:
    """``r = 2U / (n1 n2) - 1`` — the algebraic identity of Kerby's formula.

    Used only to cross-validate :func:`rank_biserial` in the test suite.
    """
    return 2.0 * u_statistic / (n1 * n2) - 1.0


def epsilon_squared(h_statistic: float, n: int, k_groups: int,
                    cfg: Config) -> EpsilonSquared:
    """Effect size for a Kruskal-Wallis omnibus test.

      Tomczak, M. & Tomczak, E. (2014). "The need to report effect size
      estimates revisited." *Trends in Sport Sciences*, 1(21), 19-25.

    epsilon^2 runs 0-1 and is the rank analogue of eta^2. It is NOT on the same
    scale as rank-biserial, so the Romano thresholds do not apply; the
    conventional small/medium/large cut-offs of .01 / .06 / .14 are used and
    labelled as such.
    """
    if n <= k_groups:
        raise ValueError("epsilon_squared requires n > k")
    eps = (h_statistic - k_groups + 1) / (n - k_groups)
    eps = max(0.0, float(eps))
    magnitude = ("large" if eps >= 0.14 else
                 "medium" if eps >= 0.06 else
                 "small" if eps >= 0.01 else "negligible")
    return EpsilonSquared(
        epsilon_squared=eps,
        h_statistic=float(h_statistic),
        n=int(n),
        k_groups=int(k_groups),
        magnitude=magnitude,
        field_notes=["Cohen-style eta^2 cut-offs (.01/.06/.14) — NOT the Romano "
                     "rank-biserial thresholds, which do not apply to epsilon^2."],
    )
