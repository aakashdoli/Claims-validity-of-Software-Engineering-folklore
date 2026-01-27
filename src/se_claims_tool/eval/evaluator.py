from __future__ import annotations
import csv
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

import pandas as pd

def _load_ai_claims(ai_path: str) -> pd.DataFrame:
    p = Path(ai_path)
    if p.suffix.lower() == ".csv":
        return pd.read_csv(p)
    if p.suffix.lower() == ".jsonl":
        rows = []
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        return pd.DataFrame(rows)
    raise ValueError("AI claims must be .csv or .jsonl")

def _load_human(path: str) -> pd.DataFrame:
    p = Path(path)
    if p.suffix.lower() == ".csv":
        return pd.read_csv(p)
    if p.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(p)
    raise ValueError("Human ground-truth must be .csv or .xlsx/.xls")

def _norm_exact(s: str) -> str:
    return (s or "").strip()

def _best_fuzzy_match(target: str, candidates: List[str]) -> Tuple[Optional[str], float]:
    # difflib is stdlib (no extra dependency)
    import difflib
    target_n = _norm_exact(target)
    best = None
    best_score = 0.0
    for c in candidates:
        c_n = _norm_exact(c)
        score = difflib.SequenceMatcher(None, target_n, c_n).ratio()
        if score > best_score:
            best_score = score
            best = c
    return best, best_score

def run_evaluation(
    ai_claims_path: str,
    human_path: str,
    outdir: str,
    fuzzy: bool,
    fuzzy_threshold: float,
    logger,
) -> None:
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)

    ai = _load_ai_claims(ai_claims_path)
    human = _load_human(human_path)

    # Required minimal columns (as per your spec)
    required = {"human_claim_text"}
    missing = required - set(human.columns)
    if missing:
        raise ValueError(f"Human file missing required columns: {sorted(missing)}")

    ai_claims = [_norm_exact(x) for x in ai.get("claim", pd.Series(dtype=str)).fillna("").tolist()]
    ai_claims_set = set(ai_claims)

    tp = 0
    fn = 0
    matched_ai_indices = set()

    rows_out: List[Dict[str, Any]] = []
    for i, row in human.iterrows():
        htxt = _norm_exact(str(row.get("human_claim_text", "")))
        status = "MISS"
        nearest = ""
        score = 0.0

        if not fuzzy:
            if htxt in ai_claims_set:
                status = "MATCH"
                tp += 1
            else:
                fn += 1
                status = "MISS"
        else:
            best, best_score = _best_fuzzy_match(htxt, ai_claims)
            if best is not None and best_score >= fuzzy_threshold:
                status = "MATCH"
                tp += 1
                nearest = best
                score = best_score
            else:
                fn += 1
                status = "MISS"
                nearest = best or ""
                score = best_score

        out_row = dict(row)
        out_row["status"] = status
        out_row["nearest_ai_claim"] = nearest
        out_row["nearest_score"] = score
        rows_out.append(out_row)

    # FP: AI claims not matched by any human claim (exact mode)
    # In fuzzy mode, we approximate FP by counting unique AI claims that were never the nearest accepted match.
    if not fuzzy:
        human_set = set(_norm_exact(str(x)) for x in human["human_claim_text"].fillna("").tolist())
        fp = sum(1 for c in ai_claims if c and c not in human_set)
    else:
        # Conservative FP estimate: all AI claims minus TP (can overcount duplicates)
        fp = max(0, len([c for c in ai_claims if c]) - tp)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0

    metrics = {
        "tp": tp,
        "fp": fp,
        "fn": fn,  # MISSES
        "precision": precision,
        "recall": recall,
        "matching": "fuzzy" if fuzzy else "exact",
        "fuzzy_threshold": fuzzy_threshold if fuzzy else None,
        "ai_claims_count": int(len([c for c in ai_claims if c])),
        "human_claims_count": int(len(human)),
    }

    # Write outputs
    with (out / "eval_metrics.json").open("w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    # per-claim report
    report_path = out / "eval_per_human_claim.csv"
    if rows_out:
        fieldnames = list(rows_out[0].keys())
        with report_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in rows_out:
                w.writerow(r)
    else:
        with report_path.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(["(no rows)"])

    logger.info(f"Eval metrics: TP={tp}, FP={fp}, FN(MISS)={fn}, P={precision:.3f}, R={recall:.3f}")
    logger.info(f"Wrote: {out/'eval_metrics.json'} and {report_path}")
