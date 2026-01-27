from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, Dict, Any, List

from ..models import ClaimRecord


def write_jsonl(path: str, claims: Iterable[ClaimRecord]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    with p.open("w", encoding="utf-8") as f:
        for c in claims:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")


def write_csv(path: str, claims: List[ClaimRecord]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    # Always create CSV, even if empty
    if not claims:
        with p.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "claim_serial",
                "book_id", "source_path",
                "chapter_id", "chapter_title",
                "paragraph_id", "sentence_index", "global_sentence_index",
                "page_number", "spine_index",
                "pre_context", "claim", "post_context",
                "citations",
                "label", "confidence", "detector",
                "extra"
            ])
        return

    fieldnames = list(asdict(claims[0]).keys())

    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for c in claims:
            row = asdict(c)

            # citations list -> JSON string
            if isinstance(row.get("citations"), list):
                row["citations"] = json.dumps(row["citations"], ensure_ascii=False)

            # extra dict -> JSON string
            if isinstance(row.get("extra"), dict):
                row["extra"] = json.dumps(row["extra"], ensure_ascii=False)

            writer.writerow(row)


def write_metadata(path: str, meta: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    with p.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
