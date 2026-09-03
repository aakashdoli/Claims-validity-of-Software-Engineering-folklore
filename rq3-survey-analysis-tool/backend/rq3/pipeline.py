"""Pipeline orchestration: decode -> screen -> six analysis stages -> exports.

Reproducibility contract
------------------------
The pipeline is deterministic: the same input file and the same ``config.yaml``
produce byte-identical results. Nothing is sampled, seeded, or ordered by hash.
Every run writes a manifest recording the input file (with its SHA-256), the
row count, the timestamp, the library versions, and the complete config, so a
number in the thesis can always be traced back to the exact run that produced it.

Re-running on a new export is a FULL re-run against that file alone. The
pipeline never merges, appends, or diffs across exports — response sets from
different survey closing points are not interchangeable.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import scipy
import statsmodels

from .analysis.buckets import ClaimBucket, classify_all, role_breakdown
from .analysis.comments import ClaimComments, collect_comments
from .analysis.comparisons import (ComparisonResult, Exclusion, compare_claim,
                                   run_pairwise)
from .analysis.correction import FamilySummary, apply_bh, apply_bh_pairwise
from .analysis.descriptives import ClaimDescriptives, describe_all
from .analysis.experience import ExperienceFamily, compare as compare_experience
from .analysis.matrix import BeliefEvidenceMatrix, build_matrix
from .claims import load_claims
from .config import Config, load_config
from .decode import DecodedSurvey, decode_export, write_clean_csv
from .quality import QualityReport, screen

TOOL_VERSION = "1.0.0"


@dataclass
class RunManifest:
    tool_version: str
    run_id: str
    timestamp_utc: str
    input_file: str
    input_sha256: str
    input_bytes: int
    n_respondents: int
    n_claims: int
    n_comments: int
    config_path: str
    config: dict[str, Any]
    library_versions: dict[str, str]
    python_version: str
    platform: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class RunResult:
    manifest: RunManifest
    claims: pd.DataFrame
    survey_text: dict[str, str]
    descriptives: list[ClaimDescriptives]
    comparisons: list[ComparisonResult]
    families: list[FamilySummary]
    exclusions: list[Exclusion]
    matrix: BeliefEvidenceMatrix
    buckets: list[ClaimBucket]
    experience: ExperienceFamily
    role_breakdowns: dict[str, list[dict[str, Any]]]
    comments: list[ClaimComments]
    quality: QualityReport
    clean_csv: str
    comments_csv: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest": self.manifest.to_dict(),
            "claims": self.claims.to_dict(orient="records"),
            "survey_text": self.survey_text,
            "descriptives": [d.to_dict() for d in self.descriptives],
            "comparisons": [c.to_dict() for c in self.comparisons],
            "correction_families": [f.to_dict() for f in self.families],
            "exclusions": [e.to_dict() for e in self.exclusions],
            "belief_evidence_matrix": self.matrix.to_dict(),
            "buckets": [b.to_dict() for b in self.buckets],
            "experience": self.experience.to_dict(),
            "role_breakdowns": self.role_breakdowns,
            "comments": [c.to_dict() for c in self.comments],
            "quality": self.quality.to_dict(),
            "clean_csv": self.clean_csv,
            "comments_csv": self.comments_csv,
        }


def _sha256(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def run(cfg: Config | None = None, input_file: str | Path | None = None) -> RunResult:
    cfg = cfg or load_config()
    src = Path(input_file) if input_file else cfg.resolve_path("dataset.input_file")

    claims = load_claims(cfg)
    decoded: DecodedSurvey = decode_export(src, claims, cfg)
    clean_csv, comments_csv = write_clean_csv(
        decoded, cfg.resolve_path("dataset.processed_dir"))

    quality = screen(decoded, cfg)

    responses = decoded.responses
    claim_ids = decoded.claim_columns

    # -- Stage 1 -------------------------------------------------------------
    descriptives = describe_all(responses, claim_ids, cfg)

    # -- Stage 2 + 3 ---------------------------------------------------------
    variables = [v for v in cfg.get("comparisons.variables")]
    comparisons: list[ComparisonResult] = []
    exclusions: list[Exclusion] = []
    missing_vars = [v for v in variables if v not in responses.columns]
    for v in missing_vars:
        exclusions.append(Exclusion(
            "comparison", "*", v, None,
            f"demographic variable '{v}' is not present in this export",
        ))
    for variable in [v for v in variables if v in responses.columns]:
        for claim_id in claim_ids:
            result, excl = compare_claim(claim_id, responses[claim_id],
                                         responses[variable], variable, cfg)
            comparisons.append(result)
            exclusions.extend(excl)

    # -- Stage 4 -------------------------------------------------------------
    families = apply_bh(comparisons, cfg)

    # Pairwise follow-ups, gated on a BH-significant omnibus.
    gate = bool(cfg.get("comparisons.pairwise_requires_significant_omnibus"))
    for c in comparisons:
        if c.test != "kruskal_wallis":
            continue
        if gate and not c.significant_adjusted:
            c.notes.append("pairwise follow-ups not run: omnibus test did not "
                           "survive Benjamini-Hochberg correction")
            continue
        included = [g.group for g in c.groups if g.included]
        c.pairwise = run_pairwise(c.claim_id, responses[c.claim_id],
                                  responses[c.variable], c.variable, included, cfg)
        apply_bh_pairwise(c.pairwise, cfg)

    # -- Stage 2b: the two-group experience comparison ------------------------
    # Its own family of 50 p-values, corrected together. Separate from the
    # per-variable Kruskal-Wallis families above.
    experience = compare_experience(responses, claim_ids, cfg)

    # -- Stage 5 -------------------------------------------------------------
    # Buckets first (IDK dominance, then the majority rule), then the matrix
    # over the clear_direction claims only.
    buckets = classify_all(descriptives, cfg)
    matrix = build_matrix(buckets, claims, cfg)

    # Descriptive role breakdown, clear_direction claims only. No test: role
    # has too many categories for a two-group comparison.
    role_var = str(cfg.get("experience_split.descriptive_variable"))
    role_breakdowns: dict[str, list[dict[str, Any]]] = {}
    if role_var in responses.columns:
        for b in buckets:
            if b.bucket == "clear_direction":
                role_breakdowns[b.claim_id] = role_breakdown(
                    responses[b.claim_id], responses[role_var], cfg)

    # -- Stage 6 -------------------------------------------------------------
    comments = collect_comments(decoded.comments, descriptives, comparisons,
                                matrix, cfg)

    digest, size = _sha256(src)
    now = datetime.now(timezone.utc)
    manifest = RunManifest(
        tool_version=TOOL_VERSION,
        run_id=now.strftime("%Y%m%dT%H%M%SZ") + "-" + digest[:8],
        timestamp_utc=now.isoformat(),
        input_file=str(src),
        input_sha256=digest,
        input_bytes=size,
        n_respondents=int(responses.shape[0]),
        n_claims=len(claim_ids),
        n_comments=int(decoded.comments.shape[0]),
        config_path=str(cfg.path),
        config=cfg.to_dict(),
        library_versions={
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "statsmodels": statsmodels.__version__,
        },
        python_version=sys.version.split()[0],
        platform=platform.platform(),
        notes=list(decoded.notes),
    )

    return RunResult(
        manifest=manifest, claims=claims, survey_text=decoded.survey_text,
        descriptives=descriptives, comparisons=comparisons, families=families,
        exclusions=exclusions, matrix=matrix, buckets=buckets,
        experience=experience, role_breakdowns=role_breakdowns,
        comments=comments, quality=quality,
        clean_csv=str(clean_csv), comments_csv=str(comments_csv),
    )


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

def results_table(result: RunResult, cfg: Config) -> pd.DataFrame:
    """The per-claim output table, exactly as specified for the write-up."""
    ev = dict(zip(result.claims["claim_id"], result.claims["evidence_label"]))
    strength = dict(zip(result.claims["claim_id"], result.claims["evidence_strength"]))
    book = dict(zip(result.claims["claim_id"], result.claims["book"]))
    qnum = dict(zip(result.claims["claim_id"], result.claims["q_number"]))
    ctype = dict(zip(result.claims["claim_id"], result.claims["claim_type"]))
    cls = {c.claim_id: c for c in result.matrix.classifications}
    bkt = {b.claim_id: b for b in result.buckets}
    exp = {r.claim_id: r for r in result.experience.results}
    ncomments = {c.claim_id: c.n_comments for c in result.comments}
    roles = result.role_breakdowns

    def role_summary(claim_id: str) -> str:
        rows = roles.get(claim_id)
        if not rows:
            return ""
        return " | ".join(
            f"{r['role']}: n={r['directional_n']}"
            + (f", {r['pct_agree']:.0f}% agree" if r["pct_agree"] is not None else "")
            + (f", {r['pct_disagree']:.0f}% disagree" if r["pct_disagree"] is not None else "")
            for r in rows)

    rows = []
    for d in result.descriptives:
        k, b = cls[d.claim_id], bkt[d.claim_id]
        e = exp.get(d.claim_id)
        in_matrix = b.bucket == "clear_direction"
        rows.append({
            "q_number": qnum.get(d.claim_id),
            "claim_id": d.claim_id,
            "claim_type": ctype.get(d.claim_id),
            "book": book.get(d.claim_id),
            "survey_text": result.survey_text.get(d.claim_id, ""),
            # --- buckets and denominators
            "bucket": b.bucket,
            "full_sample_n": b.full_sample_n,
            "directional_denominator": b.directional_n,
            "idk_n": b.idk_n,
            "idk_rate_pct": round(b.idk_rate * 100, 2),
            "pct_agree": round(b.pct_agree * 100, 2) if b.pct_agree is not None else None,
            "pct_disagree": round(b.pct_disagree * 100, 2) if b.pct_disagree is not None else None,
            "pct_neutral": round(b.pct_neutral * 100, 2) if b.pct_neutral is not None else None,
            "majority_direction": b.majority_direction,
            "belief_label": b.belief_label,
            "bucket_reason": b.reason,
            # --- raw frequencies, so every percentage above is checkable
            "freq_1": d.frequencies.get(1), "freq_2": d.frequencies.get(2),
            "freq_3": d.frequencies.get(3), "freq_4": d.frequencies.get(4),
            "freq_5": d.frequencies.get(5),
            "bimodal": d.bimodal,
            # --- evidence, only meaningful for claims in the matrix
            "evidence_label": ev.get(d.claim_id) if in_matrix else None,
            "evidence_strength": strength.get(d.claim_id, "") if in_matrix else None,
            "verdict_status": k.verdict_status,
            "belief_evidence_mismatch": k.mismatch,
            "mismatch_kind": k.mismatch_kind,
            "in_matrix": in_matrix,
            # --- the two-group experience comparison
            "experience_group_1_n": e.group_1_n if e else None,
            "experience_group_2_n": e.group_2_n if e else None,
            "experience_group_1_median": e.group_1_median if e else None,
            "experience_group_2_median": e.group_2_median if e else None,
            "mannwhitney_u": e.u_statistic if e else None,
            "mannwhitney_p_raw": e.p_raw if e else None,
            "mannwhitney_p_corrected": e.p_corrected if e else None,
            "significant_after_correction": bool(e.significant_after_correction) if e else False,
            "effect_size": (round(e.effect.r, 4) if e and e.effect else None),
            "effect_magnitude": (e.effect.magnitude if e and e.effect else None),
            "experience_not_tested_reason": e.reason if e else None,
            # --- descriptive only
            "role_breakdown": role_summary(d.claim_id),
            "n_comments": ncomments.get(d.claim_id, 0),
        })
    return pd.DataFrame(rows).sort_values("q_number").reset_index(drop=True)


def bucket_summary_table(result: RunResult) -> pd.DataFrame:
    """How many claims fell into each of the three buckets."""
    counts = result.matrix.bucket_counts
    total = sum(counts.values())
    return pd.DataFrame([
        {"bucket": k, "n_claims": v,
         "pct_of_claims": round(v / total * 100, 1) if total else 0.0}
        for k, v in counts.items()
    ])


def excluded_claims_table(result: RunResult) -> pd.DataFrame:
    """The mixed and IDK-dominant claims, reported instead of being dropped."""
    rows = []
    for b in result.buckets:
        if b.bucket == "clear_direction":
            continue
        rows.append({
            "claim_id": b.claim_id, "bucket": b.bucket,
            "survey_text": result.survey_text.get(b.claim_id, ""),
            "full_sample_n": b.full_sample_n,
            "directional_denominator": b.directional_n,
            "idk_rate_pct": round(b.idk_rate * 100, 2),
            "pct_agree": round(b.pct_agree * 100, 2) if b.pct_agree is not None else None,
            "pct_disagree": round(b.pct_disagree * 100, 2) if b.pct_disagree is not None else None,
            "pct_neutral": round(b.pct_neutral * 100, 2) if b.pct_neutral is not None else None,
            "reason": b.reason,
        })
    return pd.DataFrame(rows)


def experience_table(result: RunResult) -> pd.DataFrame:
    """The full family of 50 Mann-Whitney results, tested or not."""
    f = result.experience
    return pd.DataFrame([{
        "claim_id": r.claim_id,
        "survey_text": result.survey_text.get(r.claim_id, ""),
        "group_1_label": r.group_1_label, "group_1_n": r.group_1_n,
        "group_1_median": r.group_1_median, "group_1_idk": r.group_1_idk,
        "group_2_label": r.group_2_label, "group_2_n": r.group_2_n,
        "group_2_median": r.group_2_median, "group_2_idk": r.group_2_idk,
        "mannwhitney_u": r.u_statistic,
        "mannwhitney_p_raw": r.p_raw,
        "mannwhitney_p_corrected": r.p_corrected,
        "significant_after_correction": r.significant_after_correction,
        "effect_size": round(r.effect.r, 4) if r.effect else None,
        "effect_magnitude": r.effect.magnitude if r.effect else None,
        "favourable_pairs": r.effect.favourable_pairs if r.effect else None,
        "unfavourable_pairs": r.effect.unfavourable_pairs if r.effect else None,
        "tied_pairs": r.effect.tied_pairs if r.effect else None,
        "tested": r.tested, "not_tested_reason": r.reason,
        "correction": f.method, "alpha": f.alpha, "family_size": f.n_tested,
    } for r in f.results])


def role_breakdown_table(result: RunResult) -> pd.DataFrame:
    """Descriptive role counts for clear_direction claims. No test."""
    rows = []
    for claim_id, breakdown in result.role_breakdowns.items():
        for r in breakdown:
            rows.append({"claim_id": claim_id, **{k: v for k, v in r.items()
                                                  if k != "frequencies"},
                         **{f"freq_{k}": v for k, v in r["frequencies"].items()}})
    return pd.DataFrame(rows)


def comparisons_table(result: RunResult) -> pd.DataFrame:
    rows = []
    for c in result.comparisons:
        base = {
            "claim_id": c.claim_id, "variable": c.variable, "test": c.test,
            "statistic": c.statistic, "p_value": c.p_value,
            "p_adjusted_bh": c.p_adjusted,
            "significant_after_bh": c.significant_adjusted,
            "n_groups_included": sum(1 for g in c.groups if g.included),
            "n_groups_excluded": sum(1 for g in c.groups if not g.included),
            "groups_included": "; ".join(f"{g.group} (n={g.n_valid}, mdn={g.median}, "
                                         f"IDK={g.idk_rate:.0%})"
                                         for g in c.groups if g.included),
            "groups_excluded": "; ".join(f"{g.group} (n={g.n_valid})"
                                         for g in c.groups if not g.included),
            "excluded": c.excluded, "exclusion_reason": c.exclusion_reason,
        }
        if c.effect:
            base.update({
                "effect_size_r": round(c.effect.r, 4),
                "effect_magnitude": c.effect.magnitude,
                "favourable_pairs": c.effect.favourable_pairs,
                "unfavourable_pairs": c.effect.unfavourable_pairs,
                "tied_pairs": c.effect.tied_pairs,
                "total_pairs": c.effect.total_pairs,
            })
        elif c.omnibus_effect:
            base.update({
                "effect_size_epsilon_squared": round(c.omnibus_effect.epsilon_squared, 4),
                "effect_magnitude": c.omnibus_effect.magnitude,
            })
        rows.append(base)
    return pd.DataFrame(rows)


def matrix_table(result: RunResult) -> pd.DataFrame:
    return pd.DataFrame([{
        "belief_class": c.belief_class,
        "evidence_label": c.evidence_label,
        "count": c.count,
        "claim_ids": "; ".join(c.claim_ids),
    } for c in result.matrix.cells])


def _json_default(o: Any) -> Any:
    if isinstance(o, (pd.Timestamp, datetime)):
        return o.isoformat()
    if hasattr(o, "item"):
        return o.item()
    if pd.isna(o):
        return None
    return str(o)


def export_all(result: RunResult, cfg: Config, out_dir: str | Path | None = None) -> dict[str, str]:
    """Write every export for one run into a run-stamped directory."""
    root = Path(out_dir) if out_dir else cfg.resolve_path("dataset.results_dir")
    run_dir = root / result.manifest.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    caveat = {
        "sampling_caveat": cfg.get("reporting.sampling_caveat"),
        "question_order_caveat": cfg.get("reporting.question_order_caveat"),
        "classification_rule": (
            f"majority > {result.matrix.majority_threshold:.0%} of directional "
            f"answers; IDK-dominant at >= {result.matrix.idk_dominance_threshold:.0%} "
            "of the full sample"),
    }

    paths: dict[str, str] = {}

    def _csv(df: pd.DataFrame, name: str) -> None:
        p = run_dir / name
        with p.open("w", encoding="utf-8", newline="") as fh:
            for k, v in caveat.items():
                fh.write(f"# {k}: {' '.join(str(v).split())}\n")
            fh.write(f"# run_id: {result.manifest.run_id}\n")
            fh.write(f"# input_file: {result.manifest.input_file}\n")
            fh.write(f"# input_sha256: {result.manifest.input_sha256}\n")
            df.to_csv(fh, index=False)
        paths[name] = str(p)

    _csv(results_table(result, cfg), "claim_results.csv")
    _csv(bucket_summary_table(result), "bucket_summary.csv")
    _csv(excluded_claims_table(result), "excluded_claims.csv")
    _csv(experience_table(result), "experience_mannwhitney.csv")
    _csv(role_breakdown_table(result), "role_breakdown.csv")
    _csv(comparisons_table(result), "subgroup_comparisons.csv")
    _csv(matrix_table(result), "belief_evidence_matrix.csv")
    _csv(pd.DataFrame([e.to_dict() for e in result.exclusions]), "exclusions.csv")
    _csv(pd.DataFrame([f.to_dict() for f in result.quality.flagged]),
         "flagged_respondents.csv")

    full = result.to_dict()
    full["caveats"] = caveat
    p = run_dir / "full_run.json"
    p.write_text(json.dumps(full, indent=2, default=_json_default), encoding="utf-8")
    paths["full_run.json"] = str(p)

    p = run_dir / "manifest.json"
    p.write_text(json.dumps(result.manifest.to_dict(), indent=2, default=_json_default),
                 encoding="utf-8")
    paths["manifest.json"] = str(p)
    return paths
