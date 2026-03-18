"""
batch_pipeline.py
-----------------
Runs the two-stage claim extraction pipeline across multiple books.

Usage:
    from se_claims_tool.batch_pipeline import run_corpus
    summary = run_corpus(inputs="/path/to/books", outdir="/path/to/out", cfg=cfg, llm_filter=filter, logger=logger)
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import zipfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import RunConfig
from .export.exporter import write_csv, write_jsonl, write_metadata
from .models_rq1 import RQ1ClaimRow
from .pipeline import extract_claims_for_book
from .llm.azure_llm_filter import AzureLLMFilter

SUPPORTED = {".epub", ".azw3", ".pdf"}


def _collect_inputs(inputs: str, workdir: Path) -> List[Path]:
    p = Path(inputs)
    if p.is_dir():
        files = [f for f in p.rglob("*") if f.suffix.lower() in SUPPORTED or f.suffix.lower() == ".zip"]
        return sorted(files)
    if p.is_file() and p.suffix.lower() == ".zip":
        extract_dir = workdir / "uploaded_zip"
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(p, "r") as z:
            z.extractall(extract_dir)
        return sorted([f for f in extract_dir.rglob("*") if f.suffix.lower() in SUPPORTED])
    if p.is_file() and p.suffix.lower() in SUPPORTED:
        return [p]
    raise ValueError("inputs must be a folder, a .zip, or a single .epub/.azw3")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _dedupe_files(files: List[Path], logger) -> List[Path]:
    seen, out = set(), []
    for f in files:
        try:
            hx = _sha256_file(f)
        except Exception as e:
            logger.warning(f"Could not hash {f.name}, keeping it. Error: {e}")
            out.append(f)
            continue
        if hx in seen:
            logger.warning(f"Skipping duplicate: {f.name}")
            continue
        seen.add(hx)
        out.append(f)
    return out


def _format_claim_id(n: int) -> str:
    return f"CLM-{n:06d}"


def run_corpus(
    inputs: str,
    outdir: str,
    cfg: RunConfig,
    llm_filter: Optional[AzureLLMFilter],
    logger,
    pilot_books: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Run the two-stage pipeline across all books in inputs.
    Writes per-book CSVs and a combined all_claims.csv to outdir.
    Books and CSVs are NOT stored permanently — outdir is temporary/session only.
    """
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    workdir = out / "_work"
    workdir.mkdir(exist_ok=True)
    cache_dir = str(workdir / "converted")

    files = _collect_inputs(inputs, workdir)

    # Expand any zips
    expanded: List[Path] = []
    for f in files:
        if f.suffix.lower() == ".zip":
            xdir = workdir / f"zip_{f.stem}"
            xdir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(f, "r") as z:
                z.extractall(xdir)
            expanded.extend([x for x in xdir.rglob("*") if x.suffix.lower() in SUPPORTED])
        else:
            expanded.append(f)

    files = _dedupe_files(sorted(expanded), logger)

    if pilot_books:
        pilot_set = {b.strip() for b in pilot_books if b.strip()}
        files = [f for f in files if f.stem in pilot_set or f.name in pilot_set]

    if not files:
        raise ValueError("No .epub or .azw3 files found.")

    manifest_rows, all_rows, per_book_summaries, errors = [], [], [], []
    next_id = 1

    for book_idx, f in enumerate(files):
        try:
            logger.info(f"=== Processing book {book_idx+1}/{len(files)}: {f.name} ===")
            rows, meta = extract_claims_for_book(
                input_path=str(f),
                cfg=cfg,
                llm_filter=llm_filter,
                logger=logger,
                cache_dir=cache_dir,
                book_idx=book_idx,
            )

            # Assign final claim IDs
            assigned: List[RQ1ClaimRow] = []
            for r in rows:
                cid = _format_claim_id(next_id)
                next_id += 1
                assigned.append(replace(r, claim_id=cid))

            total = len(assigned)
            cited     = sum(1 for r in assigned if r.citation_status == "cited")
            ambiguous = sum(1 for r in assigned if r.citation_status == "ambiguous")
            not_cited = sum(1 for r in assigned if r.citation_status == "not_cited")

            def pct(x): return round(x / total * 100, 2) if total else 0.0

            per_book_summaries.append({
                "filename":         f.name,
                "sentences_total":  meta.get("sentences_total", 0),
                "nlp_candidates":   meta.get("nlp_candidates", 0),
                "claims_found":     total,
                "llm_used":         meta.get("llm_used", False),
                "cited_count":      cited,
                "ambiguous_count":  ambiguous,
                "not_cited_count":  not_cited,
                "cited_pct":        pct(cited),
                "ambiguous_pct":    pct(ambiguous),
                "not_cited_pct":    pct(not_cited),
            })

            book_out = out / f.stem
            book_out.mkdir(parents=True, exist_ok=True)
            write_jsonl(str(book_out / "claims.jsonl"), assigned)
            write_csv(str(book_out / "claims.csv"), assigned)
            write_metadata(str(book_out / "run_metadata.json"), meta)

            all_rows.extend(assigned)
            manifest_rows.append({
                "filename":        f.name,
                "sentences_total": meta.get("sentences_total", ""),
                "nlp_candidates":  meta.get("nlp_candidates", ""),
                "claims_found":    meta.get("claims_found", ""),
                "llm_used":        meta.get("llm_used", ""),
                "timestamp_utc":   meta.get("timestamp_utc", ""),
            })

        except Exception as e:
            logger.error(f"Error on {f.name}: {e}")
            errors.append({"file": f.name, "error": str(e)})

    write_jsonl(str(out / "all_claims.jsonl"), all_rows)
    write_csv(str(out / "all_claims.csv"), all_rows)

    # Write manifest
    if manifest_rows:
        man_path = out / "manifest.csv"
        with man_path.open("w", encoding="utf-8", newline="") as fp:
            w = csv.DictWriter(fp, fieldnames=list(manifest_rows[0].keys()))
            w.writeheader()
            for r in manifest_rows:
                w.writerow(r)

    # Write per-book summary
    if per_book_summaries:
        sum_path = out / "per_book_summary.csv"
        with sum_path.open("w", encoding="utf-8", newline="") as fp:
            w = csv.DictWriter(fp, fieldnames=list(per_book_summaries[0].keys()))
            w.writeheader()
            for r in per_book_summaries:
                w.writerow(r)

    total_claims = len(all_rows)
    summary = {
        "timestamp_utc":   datetime.now(timezone.utc).isoformat(),
        "books_count":     len(files),
        "books_succeeded": len(manifest_rows),
        "books_failed":    len(errors),
        "total_claims":    total_claims,
        "llm_used":        llm_filter is not None,
        "errors":          errors,
    }
    with (out / "run_summary.json").open("w", encoding="utf-8") as fp:
        json.dump(summary, fp, indent=2)

    # Create results zip
    zip_path = out / "results.zip"
    tmp_base = out.parent / (out.name + "_results")
    shutil.make_archive(str(tmp_base), "zip", out)
    tmp_zip = tmp_base.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    tmp_zip.replace(zip_path)

    logger.info(f"Pipeline complete. Total claims: {total_claims}")
    return summary