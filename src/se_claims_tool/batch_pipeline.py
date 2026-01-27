from __future__ import annotations
from pathlib import Path
from typing import List, Tuple, Dict, Any
import zipfile
import shutil
from datetime import datetime, timezone
import csv
import json

from .config import RunConfig
from .pipeline import extract_claims
from .export.exporter import write_jsonl, write_csv, write_metadata

SUPPORTED = {".epub", ".pdf"}

def _collect_inputs(inputs: str, workdir: Path) -> List[Path]:
    p = Path(inputs)
    if p.is_dir():
        files = [f for f in p.rglob("*") if f.suffix.lower() in SUPPORTED]
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
    raise ValueError("inputs must be a folder, a .zip, or a single .epub/.pdf")

def run_corpus(
    inputs: str,
    outdir: str,
    cfg: RunConfig,
    detector,
    logger,
) -> Dict[str, Any]:
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)

    workdir = out / "_work"
    workdir.mkdir(exist_ok=True)

    files = _collect_inputs(inputs, workdir)
    if not files:
        raise ValueError("No .epub or .pdf files found.")

    manifest_rows = []
    all_claims = []
    errors = []

    for f in files:
        try:
            logger.info(f"Processing: {f.name}")
            claims, meta = extract_claims(str(f), cfg, detector, logger)

            # per-book folder
            book_out = out / meta["input"]
            book_out.mkdir(parents=True, exist_ok=True)
            write_jsonl(str(book_out / "claims.jsonl"), claims)
            write_csv(str(book_out / "claims.csv"), claims)
            write_metadata(str(book_out / "run_metadata.json"), meta)

            all_claims.extend(claims)
            manifest_rows.append({
                "filename": f.name,
                "format": f.suffix.lower().lstrip("."),
                "total_sentences": meta["total_sentences"],
                "candidates_tested": meta["candidates_tested"],
                "claims_found": meta["claims_found"],
                "timestamp_utc": meta["timestamp_utc"],
            })
        except Exception as e:
            logger.error(f"Error on {f.name}: {e}")
            errors.append({"file": f.name, "error": str(e)})

    # combined outputs
    write_jsonl(str(out / "all_claims.jsonl"), all_claims)
    write_csv(str(out / "all_claims.csv"), all_claims)

    # manifest
    man_path = out / "manifest.csv"
    with man_path.open("w", encoding="utf-8", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=list(manifest_rows[0].keys()) if manifest_rows else ["filename"])
        w.writeheader()
        for r in manifest_rows:
            w.writerow(r)

    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "books_count": len(files),
        "books_succeeded": len(manifest_rows),
        "books_failed": len(errors),
        "total_claims": len(all_claims),
        "config": {
            "max_llm_calls": cfg.max_llm_calls,
            "language": cfg.language,
            "cue_phrases_count": len(cfg.cue_phrases),
        },
        "errors": errors,
    }
    with (out / "run_summary.json").open("w", encoding="utf-8") as fp:
        json.dump(summary, fp, indent=2)

    # zip everything for easy download/share
    zip_path = out / "results.zip"
    tmp_base = out.parent / (out.name + "_results")
    # create zip outside the target folder to avoid self-inclusion
    tmp_zip = tmp_base.with_suffix(".zip")
    if tmp_zip.exists():
        tmp_zip.unlink()
    shutil.make_archive(str(tmp_base), "zip", out)
    if zip_path.exists():
        zip_path.unlink()
    tmp_zip.replace(zip_path)

    # cleanup workdir (optional)
    # shutil.rmtree(workdir, ignore_errors=True)

    logger.info(f"Wrote combined outputs + {zip_path}")
    return summary
