"""FastAPI layer.

The API is a thin read-only projection over :mod:`rq3.pipeline`. It performs no
statistics of its own — every number served here comes from a pipeline run, so
the frontend and the CSV/JSON exports can never disagree.

Data access sits behind :class:`RunStore`; swapping the CSV-on-disk source for a
database later means changing ``pipeline.run``'s input, not this module and not
the analysis code.
"""

from __future__ import annotations

import io
import threading
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .config import PROJECT_ROOT, Config, load_config
from .pipeline import (RunResult, comparisons_table, export_all, matrix_table,
                       results_table, run)


class RunStore:
    """Holds the current pipeline run in memory, rebuilt on demand."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cfg: Config | None = None
        self._result: RunResult | None = None
        self._error: str | None = None

    @property
    def cfg(self) -> Config:
        if self._cfg is None:
            self._cfg = load_config()
        return self._cfg

    def reload_config(self) -> None:
        with self._lock:
            self._cfg = load_config()

    def execute(self, input_file: str | Path | None = None) -> RunResult:
        with self._lock:
            cfg = load_config()
            self._cfg = cfg
            try:
                self._result = run(cfg, input_file=input_file)
                self._error = None
            except Exception as exc:  # surfaced to the client, never swallowed
                self._error = f"{type(exc).__name__}: {exc}"
                raise
            return self._result

    @property
    def result(self) -> RunResult:
        if self._result is None:
            self.execute()
        assert self._result is not None
        return self._result

    @property
    def error(self) -> str | None:
        return self._error


store = RunStore()

app = FastAPI(
    title="RQ3 Survey Analysis Tool",
    version="1.0.0",
    description=("Belief-vs-evidence analysis of 50 software engineering folklore "
                 "claims. Read-only projection of a deterministic pipeline run."),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _caveats(cfg: Config) -> dict[str, str]:
    return {
        "sampling": " ".join(str(cfg.get("reporting.sampling_caveat")).split()),
        "question_order": " ".join(str(cfg.get("reporting.question_order_caveat")).split()),
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "error" if store.error else "ok", "error": store.error}


@app.get("/api/datasets")
def datasets() -> dict[str, Any]:
    """Every raw export the tool can be pointed at.

    Switching dataset is always a FULL re-run against that file — the pipeline
    never merges or appends across exports.
    """
    cfg = store.cfg
    raw_dir = PROJECT_ROOT / "data" / "raw"
    files = sorted(p for p in raw_dir.glob("*.xlsx") if not p.name.startswith("~$"))
    current = store.result.manifest.input_file if store._result else None
    return {
        "available": [{"name": p.name, "path": str(p),
                       "size_bytes": p.stat().st_size,
                       "current": str(p) == current} for p in files],
        "current": current,
        "note": ("Re-running on a different export replaces the result set "
                 "entirely; results from different exports are never merged."),
    }


@app.post("/api/run")
def trigger_run(input_file: str | None = Query(default=None)) -> dict[str, Any]:
    try:
        result = store.execute(input_file)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"manifest": result.manifest.to_dict()}


@app.get("/api/overview")
def overview() -> dict[str, Any]:
    result, cfg = store.result, store.cfg
    table = results_table(result, cfg)
    return {
        "manifest": result.manifest.to_dict(),
        "caveats": _caveats(cfg),
        "claims": table.where(pd.notna(table), None).to_dict(orient="records"),
        "summary": {
            "n_respondents": result.manifest.n_respondents,
            "n_claims": result.manifest.n_claims,
            "n_comments": result.manifest.n_comments,
            "n_bimodal": int(table["bimodal"].sum()),
            "bucket_counts": result.matrix.bucket_counts,
            "n_mismatch": result.matrix.n_mismatch,
            "n_match": result.matrix.n_match,
            "n_not_scored": result.matrix.n_not_scored,
            "n_scored": result.matrix.n_scored,
            "n_pending_evidence": result.matrix.n_pending_evidence,
            "n_flagged_respondents": result.quality.n_flagged,
            "n_excluded_comparisons": sum(1 for e in result.exclusions
                                          if e.scope == "comparison"),
            "n_excluded_subgroups": sum(1 for e in result.exclusions
                                        if e.scope == "subgroup"),
            "median_idk_rate_pct": float(table["idk_rate_pct"].median()),
        },
        "correction_families": [f.to_dict() for f in result.families],
    }


@app.get("/api/claims/{claim_id}")
def claim_detail(claim_id: str) -> dict[str, Any]:
    result, cfg = store.result, store.cfg
    d = next((x for x in result.descriptives if x.claim_id == claim_id), None)
    if d is None:
        raise HTTPException(status_code=404, detail=f"unknown claim {claim_id}")
    meta = result.claims[result.claims["claim_id"] == claim_id].iloc[0].to_dict()
    classification = next(c for c in result.matrix.classifications
                          if c.claim_id == claim_id)
    comments = next((c for c in result.comments if c.claim_id == claim_id), None)
    comparisons = [c for c in result.comparisons if c.claim_id == claim_id]

    # Which subgroup comparisons survived correction — repeated here so the
    # claim page can state its own result without the caller re-deriving it.
    significant = [
        {"variable": c.variable, "test": c.test, "p_adjusted": c.p_adjusted,
         "effect": (c.effect.to_dict() if c.effect
                    else c.omnibus_effect.to_dict() if c.omnibus_effect else None)}
        for c in comparisons if c.significant_adjusted
    ]

    return {
        "claim": {**meta, "survey_text": result.survey_text.get(claim_id, "")},
        "descriptives": d.to_dict(),
        "classification": classification.to_dict(),
        "comparisons": [c.to_dict() for c in comparisons],
        "significant_comparisons": significant,
        "comments": comments.to_dict() if comments else
                    {"claim_id": claim_id, "n_comments": 0, "priority_score": 0,
                     "priority_reasons": [], "comments": []},
        "likert_labels": cfg.get("likert.labels"),
        "idk_label": cfg.get("likert.idk_label"),
        "min_subgroup_size": cfg.min_subgroup_size,
        "majority_threshold": cfg.majority_threshold,
        "idk_dominance_threshold": cfg.idk_dominance_threshold,
        "pending_label": str(cfg.get("belief.pending_label")),
        "effect_size_thresholds": cfg.get("effect_size.thresholds"),
        "caveats": _caveats(cfg),
    }


@app.get("/api/conclusions")
def conclusions() -> dict[str, Any]:
    """The findings view: the numbers a reader should leave with.

    Every figure is derived here rather than in the frontend, so the conclusion
    tab can never drift from the matrix and the claim pages.
    """
    result, cfg = store.result, store.cfg
    m = result.matrix
    desc = {d.claim_id: d for d in result.descriptives}
    meta = {r["claim_id"]: r for r in result.claims.to_dict(orient="records")}
    text = result.survey_text

    def pack(c, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        d = desc[c.claim_id]
        out = {
            "claim_id": c.claim_id, "text": text.get(c.claim_id, ""),
            "book": meta[c.claim_id]["book"],
            "agree_pct": (c.pct_agree * 100) if c.pct_agree is not None else None,
            "neutral_pct": (c.pct_neutral * 100) if c.pct_neutral is not None else None,
            "disagree_pct": (c.pct_disagree * 100) if c.pct_disagree is not None else None,
            "idk_pct": c.idk_rate * 100,
            "n_valid": c.directional_n, "n_total": c.full_sample_n,
            "bucket": c.bucket,
            "evidence_label": c.evidence_label, "belief_class": c.belief_label,
        }
        return {**out, **(extra or {})}

    scored = [c for c in m.classifications if c.verdict_status in ("match", "mismatch")]
    mismatches = [c for c in m.classifications if c.verdict_status == "mismatch"]

    # The IDK contrast: mismatched claims are the ones people could not evaluate.
    def mean_idk(status: str) -> float:
        rows = [desc[c.claim_id].idk_rate * 100
                for c in m.classifications if c.verdict_status == status]
        return round(sum(rows) / len(rows), 1) if rows else 0.0

    believed_contradicted = sorted(
        [pack(c) for c in mismatches if c.evidence_label == "CONTRADICTED"],
        key=lambda r: -(r["agree_pct"] or 0))
    unbelieved_supported = sorted(
        [pack(c) for c in mismatches if c.evidence_label == "SUPPORTED"],
        key=lambda r: -(r["disagree_pct"] or 0))

    # The specified inferential comparison: experience, two groups, one BH
    # family of 50. The per-variable Kruskal-Wallis families are a separate,
    # secondary analysis and are not what this view reports.
    sig = [{"claim_id": r.claim_id, "variable": "experience",
            "text": text.get(r.claim_id, ""), "p_adjusted": r.p_corrected,
            "p_raw": r.p_raw,
            "group_1": {"label": r.group_1_label, "n": r.group_1_n,
                        "median": r.group_1_median},
            "group_2": {"label": r.group_2_label, "n": r.group_2_n,
                        "median": r.group_2_median},
            "effect": r.effect.r if r.effect else None,
            "magnitude": r.effect.magnitude if r.effect else None}
           for r in result.experience.results if r.significant_after_correction]
    n_tests = result.experience.n_tested

    return {
        "headline": {
            "n_mismatch": m.n_mismatch, "n_scored": m.n_scored,
            "n_match": m.n_match, "n_not_scored": m.n_not_scored,
            "pct_mismatch": round(m.n_mismatch / m.n_scored * 100, 1) if m.n_scored else 0.0,
            "n_claims": len(m.classifications),
            "n_respondents": result.manifest.n_respondents,
        },
        "matrix": m.to_dict(),
        "survey_text": text,
        "believed_contradicted": believed_contradicted,
        "unbelieved_supported": unbelieved_supported,
        "idk_contrast": {
            "match": mean_idk("match"), "mismatch": mean_idk("mismatch"),
            "not_scored": mean_idk("not_scored"),
            "highest": sorted(
                [pack(c) for c in m.classifications],
                key=lambda r: -r["idk_pct"])[:5],
            "threshold_pct": cfg.idk_dominance_threshold * 100,
            "n_above_threshold": result.matrix.bucket_counts.get("idk_dominant", 0),
        },
        # NO EVIDENCE FOUND is a finding, not a null result: a claim asserted as
        # guidance in practitioner literature that empirical research has not
        # addressed points directly at where future work would be useful. The
        # sharpest pointers are the ones practitioners are CONFIDENT about —
        # high agreement AND a low IDK rate — because there the profession has
        # settled on an answer no study has checked.
        "research_gap": {
            "n": m.n_not_scored,
            "believed": sorted(
                [pack(c, {"claim_type": meta[c.claim_id]["claim_type"]})
                 for c in m.classifications
                 if c.verdict_status == "not_scored" and c.belief_label == "Majority agreed"],
                key=lambda r: -(r["agree_pct"] or 0)),
            "not_believed": sorted(
                [pack(c, {"claim_type": meta[c.claim_id]["claim_type"]})
                 for c in m.classifications
                 if c.verdict_status == "not_scored" and c.belief_label != "Majority agreed"],
                key=lambda r: -(r["agree_pct"] or 0)),
            # "Confident" = the profession agrees and few people abstained, so
            # the gap is not explained away by respondents not knowing.
            "confident_idk_ceiling": 15.0,
        },
        # Strength qualifiers travel with the label rather than splitting the
        # matrix. A SUPPORTED claim resting on one small-sample study is a
        # weaker warrant than one resting on an SLR, and that belongs in the
        # write-up even though it does not change the category.
        "evidence_strength": {
            "n_qualified": sum(1 for r in result.claims.to_dict(orient="records")
                               if str(r.get("evidence_strength") or "").strip()),
            "n_claims": len(m.classifications),
            "qualified": [
                {"claim_id": r["claim_id"], "label": r["evidence_label"],
                 "strength": str(r["evidence_strength"]).strip(),
                 "text": text.get(r["claim_id"], "")}
                for r in result.claims.to_dict(orient="records")
                if str(r.get("evidence_strength") or "").strip()
            ],
        },
        "subgroups": {
            "n_significant": len(sig), "n_tests": n_tests,
            "results": sorted(sig, key=lambda r: r["p_adjusted"] or 1),
        },
        "bimodal": [pack(c, {"reason": desc[c.claim_id].bimodality_reason})
                    for c in m.classifications if desc[c.claim_id].bimodal],
        "buckets": {
            "counts": m.bucket_counts,
            "mixed": m.excluded_mixed,
            "idk_dominant": m.excluded_idk_dominant,
            "majority_threshold": m.majority_threshold,
            "idk_dominance_threshold": m.idk_dominance_threshold,
        },
        "belief_split": {
            "majority_agreed": sum(1 for c in m.classifications
                                   if c.belief_label == "Majority agreed"),
            "majority_disagreed": sum(1 for c in m.classifications
                                      if c.belief_label == "Majority disagreed"),
        },
        "experience": result.experience.to_dict(),
        "caveats": _caveats(cfg),
    }


@app.get("/api/matrix")
def matrix() -> dict[str, Any]:
    result, cfg = store.result, store.cfg
    return {"matrix": result.matrix.to_dict(), "caveats": _caveats(cfg)}


@app.get("/api/comments")
def comments(min_priority: int = Query(default=0)) -> dict[str, Any]:
    result = store.result
    buckets = [c.to_dict() for c in result.comments if c.priority_score >= min_priority]
    return {"claims": buckets,
            "total_comments": result.manifest.n_comments,
            "note": ("Prioritisation and retrieval only — qualitative coding is a "
                     "manual task and this tool does not generate codes.")}


@app.get("/api/quality")
def quality() -> dict[str, Any]:
    result, cfg = store.result, store.cfg
    return {
        "quality": result.quality.to_dict(),
        "exclusions": [e.to_dict() for e in result.exclusions],
        "dataset": {
            "input_file": result.manifest.input_file,
            "input_sha256": result.manifest.input_sha256,
            "run_id": result.manifest.run_id,
            "timestamp_utc": result.manifest.timestamp_utc,
            "n_respondents": result.manifest.n_respondents,
        },
        "caveats": _caveats(cfg),
    }


@app.get("/api/methodology")
def methodology() -> dict[str, Any]:
    result, cfg = store.result, store.cfg
    return {
        "config": cfg.to_dict(),
        "config_path": str(cfg.path),
        "manifest": result.manifest.to_dict(),
        "caveats": _caveats(cfg),
        # What ACTUALLY ran, as opposed to what the code is capable of. The
        # methods section of the thesis has to describe the former: with 3+
        # surviving subgroups on every demographic, no two-group comparison ever
        # occurred, so every omnibus test was Kruskal-Wallis and carried
        # epsilon-squared — rank-biserial appears only on the pairwise follow-ups.
        "tests_run": {
            "n_attempted": len(result.comparisons),
            "n_run": sum(1 for c in result.comparisons if c.p_value is not None),
            "by_test": {
                "mann_whitney_u": sum(1 for c in result.comparisons
                                      if c.test == "mann_whitney_u"),
                "kruskal_wallis": sum(1 for c in result.comparisons
                                      if c.test == "kruskal_wallis"),
            },
            "n_rank_biserial_omnibus": sum(1 for c in result.comparisons if c.effect),
            "n_epsilon_squared_omnibus": sum(1 for c in result.comparisons
                                             if c.omnibus_effect),
            "n_pairwise": sum(len(c.pairwise) for c in result.comparisons),
            "n_pairwise_rank_biserial": sum(1 for c in result.comparisons
                                            for p in c.pairwise if p.effect),
            "n_pairwise_significant": sum(1 for c in result.comparisons
                                          for p in c.pairwise if p.significant_adjusted),
            "n_significant_omnibus": sum(1 for c in result.comparisons
                                         if c.significant_adjusted),
            "subgroups_per_variable": {
                v: len({g.group for c in result.comparisons if c.variable == v
                        for g in c.groups if g.included})
                for v in cfg.get("comparisons.variables")
            },
            "note": ("Every demographic variable had three or more subgroups above "
                     "the minimum size, so no two-group comparison arose and every "
                     "omnibus test was Kruskal-Wallis. Mann-Whitney U and Kerby's "
                     "rank-biserial are used in the pairwise follow-ups, which run "
                     "only after an omnibus result survives correction."),
        },
        "citations": [
            {"stage": "Stage 1 — descriptives",
             "why": "Median, not mean: individual Likert items are ordinal.",
             "source": "Wohlin et al. (2012), Experimentation in Software Engineering; "
                       "Allen & Seaman (2007), Quality Progress 40(7)."},
            {"stage": "Stage 1 — bimodality",
             "why": "The median hides a split distribution, so a bimodality flag is "
                    "computed with explicit, configurable thresholds.",
             "source": "Sarle's bimodality coefficient, SAS/STAT User's Guide (1990), "
                       "reported as a cross-check only."},
            {"stage": "Stage 2 — subgroup tests",
             "why": "Nonparametric tests for ordinal outcomes; scipy owns the tie "
                    "corrections rather than any hand-rolled formula.",
             "source": "scipy.stats.mannwhitneyu / scipy.stats.kruskal; "
                       "Kitchenham et al. (2017), EMSE 22(2)."},
            {"stage": "Stage 3 — effect size",
             "why": "Rank-biserial correlation with auditable pair counts, reported "
                    "for every comparison and not only the significant ones.",
             "source": "Kerby (2014), Comprehensive Psychology 3; thresholds from "
                       "Romano et al. (2006)."},
            {"stage": "Stage 4 — multiple testing",
             "why": "Benjamini-Hochberg FDR per demographic-variable family: pooling "
                    "would over-correct, skipping would manufacture false positives.",
             "source": "Benjamini & Hochberg (1995), JRSS-B 57(1); "
                       "statsmodels.stats.multitest.multipletests(method='fdr_bh')."},
            {"stage": "Stage 5 — belief-evidence matrix",
             "why": "Belief-vs-evidence cross-tabulation, the core RQ3 output.",
             "source": "Devanbu, Zimmermann & Bird (2016), ICSE 2016."},
            {"stage": "Sampling",
             "why": "Purposive sampling: the results describe this sample, not "
                    "practitioners in general.",
             "source": "Baltes & Ralph (2022), Empirical Software Engineering."},
        ],
    }


@app.get("/api/export/{kind}")
def export(kind: str):
    """Stream one export. Every CSV carries the caveats as comment lines."""
    result, cfg = store.result, store.cfg
    builders = {
        "claims": (results_table(result, cfg), "claim_results.csv"),
        "comparisons": (comparisons_table(result), "subgroup_comparisons.csv"),
        "matrix": (matrix_table(result), "belief_evidence_matrix.csv"),
        "exclusions": (pd.DataFrame([e.to_dict() for e in result.exclusions]),
                       "exclusions.csv"),
        "flagged": (pd.DataFrame([f.to_dict() for f in result.quality.flagged]),
                    "flagged_respondents.csv"),
    }
    if kind == "full":
        payload = result.to_dict()
        payload["caveats"] = _caveats(cfg)
        return JSONResponse(
            content=jsonable(payload),
            headers={"Content-Disposition":
                     f'attachment; filename="rq3_run_{result.manifest.run_id}.json"'},
        )
    if kind not in builders:
        raise HTTPException(status_code=404, detail=f"unknown export '{kind}'")
    df, filename = builders[kind]
    buf = io.StringIO()
    for k, v in _caveats(cfg).items():
        buf.write(f"# {k}_caveat: {v}\n")
    buf.write(f"# run_id: {result.manifest.run_id}\n")
    buf.write(f"# input_file: {result.manifest.input_file}\n")
    buf.write(f"# input_sha256: {result.manifest.input_sha256}\n")
    buf.write(f"# majority_threshold: {cfg.majority_threshold}\n")
    buf.write(f"# idk_dominance_threshold: {cfg.idk_dominance_threshold}\n")
    buf.write(f"# min_subgroup_size: {cfg.min_subgroup_size}\n")
    df.to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/export/write")
def write_exports() -> dict[str, Any]:
    """Write the run-stamped export directory to disk (data/results/<run_id>/)."""
    result, cfg = store.result, store.cfg
    return {"paths": export_all(result, cfg), "run_id": result.manifest.run_id}


def jsonable(obj: Any) -> Any:
    """NaN/NA-safe JSON coercion for the full-run payload."""
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, float) and pd.isna(obj):
        return None
    if obj is pd.NA or obj is None:
        return None
    if hasattr(obj, "item") and not isinstance(obj, (str, bytes)):
        try:
            return obj.item()
        except Exception:
            return str(obj)
    return obj
