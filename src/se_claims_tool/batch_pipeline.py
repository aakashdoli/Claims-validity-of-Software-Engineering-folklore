# src/se_claims_tool/batch_pipeline.py
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import zipfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .config import RunConfig
from .export.exporter import write_csv, write_jsonl, write_metadata
from .models_rq1 import RQ1ClaimRow
from .pipeline import extract_claim_rows_for_book


SUPPORTED = {".epub", ".azw3"}


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
        files = [f for f in extract_dir.rglob("*") if f.suffix.lower() in SUPPORTED]
        return sorted(files)

    if p.is_file() and p.suffix.lower() in SUPPORTED:
        return [p]

    raise ValueError("inputs must be a folder, a .zip, or a single .epub/.azw3")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _dedupe_files_by_hash(files: List[Path], logger) -> List[Path]:
    """
    Deduplicate by file content hash.
    Keeps the first occurrence in sorted order.
    """
    seen = set()
    out: List[Path] = []
    for f in files:
        if f.suffix.lower() == ".zip":
            out.append(f)
            continue

        try:
            hx = _sha256_file(f)
        except Exception as e:
            logger.warning(f"Could not hash {f.name}. Keeping it. Error: {e}")
            out.append(f)
            continue

        if hx in seen:
            logger.warning(f"Skipping duplicate file by hash: {f.name}")
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
    detector,
    logger,
    pilot_books: List[str] | None = None,
) -> Dict[str, Any]:
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)

    workdir = out / "_work"
    workdir.mkdir(exist_ok=True)

    cache_dir = str(workdir / "converted")

    files = _collect_inputs(inputs, workdir)

    files = _dedupe_files_by_hash(files, logger)

    expanded: List[Path] = []
    for f in files:
        if f.suffix.lower() == ".zip":
            extract_dir = workdir / f"zip_{f.stem}"
            extract_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(f, "r") as z:
                z.extractall(extract_dir)
            expanded.extend([x for x in extract_dir.rglob("*") if x.suffix.lower() in SUPPORTED])
        else:
            expanded.append(f)

    files = sorted(expanded)

    files = _dedupe_files_by_hash(files, logger)

    if not files:
        raise ValueError("No .epub or .azw3 files found after filtering and deduplication.")

    if pilot_books:
        pilot_set = {b.strip() for b in pilot_books if b.strip()}
        files = [f for f in files if f.stem in pilot_set or f.name in pilot_set]

    manifest_rows: List[Dict[str, Any]] = []
    all_rows: List[RQ1ClaimRow] = []
    per_book_summaries: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []

    next_id = 1

    for f in files:
        try:
            logger.info(f"Processing: {f.name}")
            rows, meta = extract_claim_rows_for_book(
                input_path=str(f),
                cfg=cfg,
                detector=detector,
                logger=logger,
                cache_dir=cache_dir,
            )

            assigned: List[RQ1ClaimRow] = []
            for r in rows:
                cid = _format_claim_id(next_id)
                next_id += 1
                assigned.append(replace(r, claim_id=cid))

            cited = sum(1 for r in assigned if r.citation_status == "cited")
            ambiguous = sum(1 for r in assigned if r.citation_status == "ambiguous")
            not_cited = sum(1 for r in assigned if r.citation_status == "not_cited")
            total = len(assigned)

            def pct(x: int) -> float:
                if total == 0:
                    return 0.0
                return x / total * 100.0

            per_book_summaries.append(
                {
                    "filename": f.name,
                    "format": f.suffix.lower().lstrip("."),
                    "claims_found": total,
                    "cited_count": cited,
                    "ambiguous_count": ambiguous,
                    "not_cited_count": not_cited,
                    "cited_pct": round(pct(cited), 2),
                    "ambiguous_pct": round(pct(ambiguous), 2),
                    "not_cited_pct": round(pct(not_cited), 2),
                }
            )

            book_out = out / f.stem
            book_out.mkdir(parents=True, exist_ok=True)
            write_jsonl(str(book_out / "claims.jsonl"), assigned)
            write_csv(str(book_out / "claims.csv"), assigned)
            write_metadata(str(book_out / "run_metadata.json"), meta)

            all_rows.extend(assigned)

            manifest_rows.append(
                {
                    "filename": f.name,
                    "format": f.suffix.lower().lstrip("."),
                    "paragraphs_total": meta.get("paragraphs_total", ""),
                    "candidates_tested": meta.get("candidates_tested", ""),
                    "claims_found": meta.get("claims_found", ""),
                    "timestamp_utc": meta.get("timestamp_utc", ""),
                }
            )
        except Exception as e:
            logger.error(f"Error on {f.name}: {e}")
            errors.append({"file": f.name, "error": str(e)})

    write_jsonl(str(out / "all_claims.jsonl"), all_rows)
    write_csv(str(out / "all_claims.csv"), all_rows)

    man_path = out / "manifest.csv"
    with man_path.open("w", encoding="utf-8", newline="") as fp:
        fieldnames = list(manifest_rows[0].keys()) if manifest_rows else ["filename"]
        w = csv.DictWriter(fp, fieldnames=fieldnames)
        w.writeheader()
        for r in manifest_rows:
            w.writerow(r)

    sum_path = out / "per_book_summary.csv"
    if per_book_summaries:
        with sum_path.open("w", encoding="utf-8", newline="") as fp:
            fieldnames = list(per_book_summaries[0].keys())
            w = csv.DictWriter(fp, fieldnames=fieldnames)
            w.writeheader()
            for r in per_book_summaries:
                w.writerow(r)
    else:
        with sum_path.open("w", encoding="utf-8", newline="") as fp:
            fp.write(
                "filename,format,claims_found,cited_count,ambiguous_count,not_cited_count,cited_pct,ambiguous_pct,not_cited_pct\n"
            )

    total_claims = len(all_rows)
    total_cited = sum(1 for r in all_rows if r.citation_status == "cited")
    total_ambiguous = sum(1 for r in all_rows if r.citation_status == "ambiguous")
    total_not_cited = sum(1 for r in all_rows if r.citation_status == "not_cited")

    def pct_total(x: int) -> float:
        if total_claims == 0:
            return 0.0
        return x / total_claims * 100.0

    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "books_count": len(files),
        "books_succeeded": len(manifest_rows),
        "books_failed": len(errors),
        "total_claims": total_claims,
        "citation_breakdown": {
            "cited_count": total_cited,
            "ambiguous_count": total_ambiguous,
            "not_cited_count": total_not_cited,
            "cited_pct": round(pct_total(total_cited), 2),
            "ambiguous_pct": round(pct_total(total_ambiguous), 2),
            "not_cited_pct": round(pct_total(total_not_cited), 2),
        },
        "config": {
            "max_llm_calls": cfg.max_llm_calls,
            "language": cfg.language,
            "cue_phrases_count": len(cfg.cue_phrases),
        },
        "errors": errors,
    }
    with (out / "run_summary.json").open("w", encoding="utf-8") as fp:
        json.dump(summary, fp, indent=2)

    zip_path = out / "results.zip"
    tmp_base = out.parent / (out.name + "_results")
    tmp_zip = tmp_base.with_suffix(".zip")
    if tmp_zip.exists():
        tmp_zip.unlink()
    shutil.make_archive(str(tmp_base), "zip", out)
    if zip_path.exists():
        zip_path.unlink()
    tmp_zip.replace(zip_path)

    logger.info(f"Wrote outputs. Combined CSV: {out/'all_claims.csv'}")
    return summary
