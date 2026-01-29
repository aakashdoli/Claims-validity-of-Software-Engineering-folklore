from __future__ import annotations

from dataclasses import asdict
from typing import List

from ..models_rq1 import RQ1ClaimRow, RQ1_CSV_COLUMNS


ALLOWED_CITATION_STATUS = {"cited", "not_cited", "ambiguous"}


def validate_records(records: List[RQ1ClaimRow]) -> None:
    if records is None:
        raise ValueError("records is None")

    claim_ids = set()
    for idx, r in enumerate(records):
        d = asdict(r)

        missing = [c for c in RQ1_CSV_COLUMNS if c not in d]
        if missing:
            raise ValueError(f"Schema missing columns at row {idx}: {missing}")

        extra = [k for k in d.keys() if k not in RQ1_CSV_COLUMNS]
        if extra:
            raise ValueError(f"Schema has unexpected columns at row {idx}: {extra}")

        if not isinstance(r.paragraph_index, int):
            raise ValueError(f"paragraph_index must be int for claim_id={r.claim_id}")
        if not isinstance(r.sentence_index, int):
            raise ValueError(f"sentence_index must be int for claim_id={r.claim_id}")

        if r.citation_status not in ALLOWED_CITATION_STATUS:
            raise ValueError(f"Invalid citation_status for claim_id={r.claim_id}: {r.citation_status}")

        if r.claim_id in claim_ids:
            raise ValueError(f"Duplicate claim_id detected: {r.claim_id}")
        claim_ids.add(r.claim_id)

        for f in ["verified", "verifier", "verification_notes"]:
            v = getattr(r, f)
            if v is None:
                raise ValueError(f"{f} must be blank string, not None, for claim_id={r.claim_id}")
