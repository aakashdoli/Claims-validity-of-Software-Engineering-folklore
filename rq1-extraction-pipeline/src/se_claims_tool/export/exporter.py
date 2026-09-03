from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

from ..models_rq1 import RQ1ClaimRow, RQ1_CSV_COLUMNS
from .schema_validate import validate_records


def write_jsonl(path: str, rows: Iterable[RQ1ClaimRow]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")


def write_csv(path: str, rows: List[RQ1ClaimRow]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        with p.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(RQ1_CSV_COLUMNS)
        return

    validate_records(rows)

    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RQ1_CSV_COLUMNS, extrasaction="raise")
        writer.writeheader()
        for r in rows:
            d = asdict(r)
            row = {k: d.get(k, "") for k in RQ1_CSV_COLUMNS}
            writer.writerow(row)


def write_metadata(path: str, meta: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
