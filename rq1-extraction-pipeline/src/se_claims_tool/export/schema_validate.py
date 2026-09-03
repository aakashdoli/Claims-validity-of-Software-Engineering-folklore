from __future__ import annotations

from dataclasses import asdict
from typing import List

from ..models_rq1 import RQ1ClaimRow, RQ1_CSV_COLUMNS


def validate_records(rows: List[RQ1ClaimRow]) -> None:
    if rows is None:
        raise ValueError("rows is None")

    for i, r in enumerate(rows):
        d = asdict(r)
        keys = list(d.keys())

        if keys.count("claim_text") != 1:
            raise ValueError(f"Schema error on row {i}. claim_text appears {keys.count('claim_text')} times")

        missing = [c for c in RQ1_CSV_COLUMNS if c not in d]
        extra = [k for k in d.keys() if k not in RQ1_CSV_COLUMNS]

        if missing:
            raise ValueError(f"Schema error on row {i}. Missing columns: {missing}")
        if extra:
            raise ValueError(f"Schema error on row {i}. Extra columns: {extra}")

        if r.citation_status not in {"cited", "not_cited", "ambiguous"}:
            raise ValueError(f"Schema error on row {i}. Invalid citation_status: {r.citation_status}")

        if not isinstance(r.paragraph_index, int):
            raise ValueError(f"Schema error on row {i}. paragraph_index must be int")
        if not isinstance(r.sentence_index, int):
            raise ValueError(f"Schema error on row {i}. sentence_index must be int")
