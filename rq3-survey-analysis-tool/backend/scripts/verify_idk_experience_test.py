"""Provenance check for the pooled IDK comparison reported in Section 4.3.4.

Answers, reproducibly, three questions an examiner may ask about the
p = 0.0171 / r = +0.125 pair:

  1. Which test produced it, and on what unit of analysis?
  2. Is the reported "r" the same rank-biserial correlation used elsewhere
     in the chapter, or a different measure labelled generically?
  3. Does the effect-size magnitude label match the Romano et al. (2006)
     bands declared in config.yaml?

Run:  cd backend && python scripts/verify_idk_experience_test.py
"""
import sys
from pathlib import Path

import numpy as np
from scipy.stats import mannwhitneyu

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rq3.analysis.effects import rank_biserial, rank_biserial_from_u
from rq3.claims import load_claims
from rq3.config import load_config
from rq3.decode import decode_export


def main() -> None:
    cfg = load_config()
    dec = decode_export(cfg.resolve_path("dataset.input_file"), load_claims(cfg), cfg)
    responses, claim_cols = dec.responses, dec.claim_columns

    g1 = responses["experience"].isin(cfg.get("experience_split.group_1.bands"))
    g2 = responses["experience"].isin(cfg.get("experience_split.group_2.bands"))

    # UNIT OF ANALYSIS = the respondent. Each person contributes ONE number:
    # the share of their own answered claims where they chose IDK. This is not
    # a two-proportion test pooled over the 751 x 50 = 37,550 responses; those
    # responses are nested within respondents and are not independent.
    answers = responses[claim_cols]
    rate = ((answers == "IDK").sum(axis=1) / answers.notna().sum(axis=1) * 100).to_numpy(float)

    a, b = rate[g1.to_numpy()], rate[g2.to_numpy()]
    u_stat, p_value = mannwhitneyu(a, b, alternative="two-sided")
    effect = rank_biserial(a, b, cfg)
    identity = rank_biserial_from_u(u_stat, a.size, b.size, cfg)

    print(f"unit of analysis   respondent (IDK rate across {len(claim_cols)} claims)")
    print(f"{cfg.get('experience_split.group_1.label'):<18} "
          f"mean {a.mean():.1f}%  median {np.median(a):.1f}%  n={a.size}")
    print(f"{cfg.get('experience_split.group_2.label'):<18} "
          f"mean {b.mean():.1f}%  median {np.median(b):.1f}%  n={b.size}")
    print(f"\nMann-Whitney U     {u_stat:,.1f}   p = {p_value:.4f}  (two-sided, UNCORRECTED)")
    print(f"rank-biserial r    {effect.r:+.4f}  [{effect.magnitude}]")
    print(f"  Kerby pair counts  favourable {effect.favourable_pairs:,.0f} / "
          f"unfavourable {effect.unfavourable_pairs:,.0f} / tied {effect.tied_pairs:,.0f} "
          f"of {effect.total_pairs:,}")
    print(f"  cross-check 2U/(n1n2)-1  {identity:+.4f}")

    t = cfg.get("effect_size.thresholds")
    print(f"\nRomano bands       small {t['small']} / medium {t['medium']} / large {t['large']}")
    print(f"  |r| = {abs(effect.r):.4f} is "
          f"{'BELOW' if abs(effect.r) < t['small'] else 'at or above'} the small threshold "
          f"-> '{effect.magnitude}'")

    assert abs(effect.r - identity) < 1e-9, "rank-biserial disagrees with its own identity"


if __name__ == "__main__":
    main()
