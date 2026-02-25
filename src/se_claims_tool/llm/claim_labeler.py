from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


def _clean_text(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, float) and math.isnan(x):
        return ""
    return str(x).strip()


LABEL_SYSTEM_PROMPT = """
You label candidate sentences extracted from practitioner books.

Definition
A CLAIM is a generalizable assertion or advice relevant to software engineering practice.
Examples of claims
- Prescriptive: should, must, recommend, avoid
- Causal: leads to, results in, causes, increases, reduces
- Comparative: better than, worse than, more effective
- Quantitative: numbers, percentages, "twice", "30 percent"

Not claims
- Headings or fragments
- Pure description of what the author did in one situation
- Anecdotes and personal experience
- Definitions without an assertion
- Examples used only to illustrate

Author perspective
Set is_author_perspective=true when it is first-person or personal framing such as I, we, my, in my experience, I have seen.

Be conservative
If uncertain, set is_claim=false and use a lower confidence.

Return only valid JSON in this format
{
  "items": [
    {
      "claim_id": "string",
      "is_claim": true or false,
      "is_author_perspective": true or false,
      "claim_type": "prescriptive|causal|comparative|quantitative|conditional|definition|descriptive|other",
      "confidence": 0.0 to 1.0,
      "reason": "short reason"
    }
  ]
}
""".strip()


@dataclass(frozen=True)
class LabelResult:
    claim_id: str
    is_claim: bool
    is_author_perspective: bool
    claim_type: str
    confidence: float
    reason: str


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _make_payload(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    candidates = []
    for r in rows:
        candidates.append(
            {
                "claim_id": str(r.get("claim_id", "")),
                "claim_text": _clean_text(r.get("claim_text")),
                "chapter_title": _clean_text(r.get("chapter_title")),
                "section_title": _clean_text(r.get("section_title")),
                "location_text": _clean_text(r.get("location_text")),
                "citation_context": _clean_text(r.get("citation_context")),
            }
        )
    return {"candidates": candidates}


def _parse_labels(obj: Dict[str, Any]) -> List[LabelResult]:
    items = obj.get("items", [])
    out: List[LabelResult] = []
    for it in items:
        try:
            out.append(
                LabelResult(
                    claim_id=str(it["claim_id"]),
                    is_claim=bool(it["is_claim"]),
                    is_author_perspective=bool(it["is_author_perspective"]),
                    claim_type=str(it["claim_type"]),
                    confidence=float(it["confidence"]),
                    reason=str(it["reason"]),
                )
            )
        except Exception:
            continue
    return out


def label_claims_with_azure(
    azure_client: Any,
    rows: List[Dict[str, Any]],
    model_name: str,
    batch_size: int = 20,
    max_retries: int = 4,
    sleep_base_seconds: float = 1.0,
) -> Tuple[List[LabelResult], Dict[str, Any]]:
    """
    azure_client must expose a method like:
      azure_client.chat_json(messages: list[dict], response_format: dict) -> dict
    That is consistent with your existing Azure client wrapper.

    Returns (labels, metadata)
    """
    labels: List[LabelResult] = []
    total = len(rows)

    run_meta: Dict[str, Any] = {
        "model": model_name,
        "temperature": 0,
        "batch_size": batch_size,
        "total_rows": total,
        "labeled_rows": 0,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    for start in range(0, total, batch_size):
        batch = rows[start : start + batch_size]
        payload = _make_payload(batch)

        user_prompt = (
            "Label these candidates.\n\n"
            "Only label what is provided. Do not rewrite the claim text.\n\n"
            f"INPUT:\n{json.dumps(payload, ensure_ascii=False)}"
        )

        messages = [
            {"role": "system", "content": LABEL_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        last_err: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                result = azure_client.chat_json(
                    messages=messages,
                    temperature=0,
                )
                parsed = _parse_labels(result)
                labels.extend(parsed)
                break
            except Exception as e:
                last_err = e
                if attempt == max_retries:
                    raise
                time.sleep(min(8.0, sleep_base_seconds * (2 ** (attempt - 1))))

        run_meta["labeled_rows"] = len(labels)

    return labels, run_meta