"""Data-quality screening.

Every check here FLAGS. Nothing is auto-excluded: dropping a respondent is a
research decision, made by a human from the data-quality panel, not by a
threshold in a config file. The flags and their reasons are carried into the
exports so any exclusion applied later in the thesis can be justified.

Checks:

* **Straightlining** — a respondent who used <= ``max_distinct_values``
  distinct answers across all 50 claims (this is what caught R0002 in the
  613-response batch: 50x "I don't know").
* **Modal dominance** — a respondent whose single most common answer accounts
  for >= ``modal_answer_share`` of their answers, even if they varied a little.
* **All-IDK** — IDK rate >= ``idk_rate``.
* **Duplicate answer patterns** — identical 50-answer strings across
  respondents, which would indicate submission duplication.
* **Speeding** — completion faster than ``min_completion_seconds``. Reported as
  ``unavailable`` when the export carries no duration column, never as passed.
* **Consent** — respondents without a recorded consent are flagged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from .config import Config
from .decode import DecodedSurvey

IDK = "IDK"


@dataclass
class RespondentFlag:
    respondent_id: str
    flags: list[str]
    distinct_values: int
    modal_answer: str | None
    modal_share: float
    idk_rate: float
    n_answered: int
    duration_seconds: float | None
    demographics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class QualityReport:
    n_respondents: int
    n_flagged: int
    flag_counts: dict[str, int]
    flagged: list[RespondentFlag]
    duplicate_pattern_groups: list[list[str]]
    speeding_check: str            # "applied" | "unavailable: <reason>"
    consent_check: str
    thresholds: dict[str, Any]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["flagged"] = [f.to_dict() for f in self.flagged]
        return d


def screen(decoded: DecodedSurvey, cfg: Config) -> QualityReport:
    thresholds = cfg.get("quality.low_effort")
    max_distinct = int(thresholds["max_distinct_values"])
    modal_share_limit = float(thresholds["modal_answer_share"])
    idk_limit = float(thresholds["idk_rate"])
    min_seconds = float(thresholds["min_completion_seconds"])

    df = decoded.responses
    claim_cols = decoded.claim_columns
    flags: list[RespondentFlag] = []
    counts: dict[str, int] = {}
    notes = list(decoded.notes)

    has_duration = decoded.duration_column is not None
    speeding_check = (
        "applied" if has_duration
        else "unavailable: the export carries no completion-duration column, so "
             "no respondent can be screened for speeding"
    )

    patterns: dict[str, list[str]] = {}

    # Claim IDs contain hyphens, which ``itertuples`` mangles into positional
    # attribute names — iterate over plain dicts instead.
    for row in df.to_dict(orient="records"):
        rid = str(row["respondent_id"])
        answers = [str(row[c]) if pd.notna(row[c]) else "" for c in claim_cols]
        answered = [a for a in answers if a]
        patterns.setdefault("|".join(answers), []).append(rid)

        counts_by_value = pd.Series(answered).value_counts() if answered else pd.Series(dtype=int)
        distinct = int(counts_by_value.size)
        modal = str(counts_by_value.index[0]) if distinct else None
        modal_share = float(counts_by_value.iloc[0] / len(answered)) if answered else 0.0
        idk_rate = (answers.count(IDK) / len(answers)) if answers else 0.0
        raw_duration = row.get("duration_seconds") if has_duration else None
        duration = float(raw_duration) if raw_duration is not None and pd.notna(raw_duration) else None

        row_flags: list[str] = []
        if distinct and distinct <= max_distinct:
            row_flags.append(f"straightlining: used {distinct} distinct answer "
                             f"value(s) across {len(answered)} claims")
        if modal_share >= modal_share_limit and distinct > max_distinct:
            row_flags.append(f"modal dominance: {modal_share:.0%} of answers were "
                             f"'{modal}'")
        if idk_rate >= idk_limit:
            row_flags.append(f"IDK rate {idk_rate:.0%} at or above the "
                             f"{idk_limit:.0%} threshold")
        if len(answered) < len(claim_cols):
            row_flags.append(f"incomplete: answered {len(answered)} of "
                             f"{len(claim_cols)} claims")
        if has_duration and duration is not None and duration < min_seconds:
            row_flags.append(f"completed in {duration:.0f}s, under the "
                             f"{min_seconds:.0f}s floor")
        if bool(cfg.get("quality.require_consent")) and not bool(row["consented"]):
            row_flags.append("no recorded consent")

        if row_flags:
            for f in row_flags:
                key = f.split(":")[0]
                counts[key] = counts.get(key, 0) + 1
            flags.append(RespondentFlag(
                respondent_id=rid, flags=row_flags, distinct_values=distinct,
                modal_answer=modal, modal_share=modal_share, idk_rate=idk_rate,
                n_answered=len(answered), duration_seconds=duration,
                demographics={c: (row[c] if pd.notna(row.get(c)) else None)
                              for c in decoded.demographic_columns},
            ))

    duplicate_groups = [rids for rids in patterns.values() if len(rids) > 1]
    if duplicate_groups:
        counts["duplicate answer pattern"] = sum(len(g) for g in duplicate_groups)
        notes.append(
            f"{len(duplicate_groups)} identical 50-answer pattern(s) shared by "
            f"{sum(len(g) for g in duplicate_groups)} respondents — review "
            "before treating them as independent responses."
        )

    return QualityReport(
        n_respondents=int(df.shape[0]),
        n_flagged=len(flags),
        flag_counts=counts,
        flagged=sorted(flags, key=lambda f: (-len(f.flags), f.respondent_id)),
        duplicate_pattern_groups=duplicate_groups,
        speeding_check=speeding_check,
        consent_check=(f"{int(df['consented'].sum())} of {df.shape[0]} respondents "
                       "have a recorded consent"),
        thresholds=dict(thresholds),
        notes=notes,
    )
