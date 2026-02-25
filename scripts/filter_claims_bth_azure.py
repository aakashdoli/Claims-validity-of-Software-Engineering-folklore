#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import time
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv

SYSTEM_PROMPT = """You label candidate sentences extracted from practitioner books.

Label as a CLAIM only if the sentence is a generalizable assertion or advice relevant to software engineering practice.
A claim can be prescriptive ("should", "must"), causal ("leads to"), comparative ("better than"), or quantitative ("reduces by 30%").

Do NOT treat headings, pure descriptions, definitions, examples, or anecdotes as claims.

Mark is_author_perspective=true when it is personal experience, opinion, narrative, or first-person framing (I, we, my, in my experience).

Be conservative. If uncertain, set is_claim=false and lower confidence.

Return ONLY valid JSON as:
{
  "items": [
    {
      "row_id": "string",
      "is_claim": true/false,
      "is_author_perspective": true/false,
      "claim_type": "prescriptive|causal|comparative|quantitative|conditional|definition|descriptive|other",
      "confidence": 0.0-1.0,
      "reason": "short"
    }
  ]
}
"""


def read_csv(path: str) -> tuple[list[dict[str, str]], list[str]]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        rows = list(r)
        if not r.fieldnames:
            raise ValueError("CSV has no header")
        return rows, list(r.fieldnames)


def write_csv(path: str, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def chunk(items: list[dict[str, Any]], n: int) -> list[list[dict[str, Any]]]:
    return [items[i : i + n] for i in range(0, len(items), n)]


def call_bth_azure_chat_completions(
    base_endpoint: str,
    deployment: str,
    api_key: str,
    api_version: str,
    payload: dict[str, Any],
    max_retries: int = 5,
) -> dict[str, Any]:
    url = f"{base_endpoint}/deployments/{deployment}/chat/completions?api-version={api_version}"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "Label these candidates.\n\nINPUT:\n"
            + json.dumps(payload, ensure_ascii=False),
        },
    ]

    body = {
        "messages": messages,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }

    headers = {
        "Content-Type": "application/json",
        "api-key": api_key,
    }

    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=60)
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception as e:
            last_err = e
            if attempt == max_retries:
                raise
            time.sleep(min(8, 2 ** (attempt - 1)))

    raise RuntimeError(f"Failed call. Last error: {last_err}")


def main() -> None:
    load_dotenv()

    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to all_claims.csv")
    ap.add_argument("--outdir", default="out", help="Output directory")
    ap.add_argument(
        "--text-col", default="claim_text", help="Column that contains candidate text"
    )
    ap.add_argument("--id-col", default="", help="Optional stable id column")
    ap.add_argument("--prev-col", default="", help="Optional previous sentence column")
    ap.add_argument("--next-col", default="", help="Optional next sentence column")
    ap.add_argument("--batch-size", type=int, default=20)
    ap.add_argument("--min-confidence", type=float, default=0.7)
    args = ap.parse_args()

    base_endpoint = os.getenv("BTH_AZURE_OPENAI_ENDPOINT", "").strip()
    deployment = os.getenv("BTH_AZURE_OPENAI_DEPLOYMENT", "").strip()
    api_key = os.getenv("BTH_AZURE_OPENAI_API_KEY", "").strip()
    api_version = os.getenv("BTH_AZURE_OPENAI_API_VERSION", "").strip()

    missing = [
        k
        for k, v in {
            "BTH_AZURE_OPENAI_ENDPOINT": base_endpoint,
            "BTH_AZURE_OPENAI_DEPLOYMENT": deployment,
            "BTH_AZURE_OPENAI_API_KEY": api_key,
            "BTH_AZURE_OPENAI_API_VERSION": api_version,
        }.items()
        if not v
    ]
    if missing:
        raise SystemExit(f"Missing env vars: {missing}. Put them in .env")

    os.makedirs(args.outdir, exist_ok=True)

    rows, fieldnames = read_csv(args.input)
    if args.text_col not in fieldnames:
        raise SystemExit(
            f"Missing text column '{args.text_col}'. Available: {fieldnames}"
        )

    items: list[dict[str, Any]] = []
    for i, r in enumerate(rows):
        rid = r.get(args.id_col, "").strip() if args.id_col else ""
        if not rid:
            rid = str(i)
        items.append(
            {
                "row_id": rid,
                "row_index": i,
                "text": (r.get(args.text_col) or "").strip(),
                "prev": (r.get(args.prev_col) or "").strip() if args.prev_col else "",
                "next": (r.get(args.next_col) or "").strip() if args.next_col else "",
            }
        )

    extra_cols = [
        "is_claim",
        "is_author_perspective",
        "claim_type",
        "confidence",
        "llm_reason",
    ]
    out_fields = list(fieldnames)
    for c in extra_cols:
        if c not in out_fields:
            out_fields.append(c)

    strict_rows: list[dict[str, Any]] = []
    non_rows: list[dict[str, Any]] = []

    batches = chunk(items, args.batch_size)
    for bi, batch in enumerate(batches, start=1):
        payload = {
            "candidates": [
                {
                    "row_id": x["row_id"],
                    "text": x["text"],
                    "prev": x["prev"],
                    "next": x["next"],
                }
                for x in batch
            ]
        }
        result = call_bth_azure_chat_completions(
            base_endpoint=base_endpoint,
            deployment=deployment,
            api_key=api_key,
            api_version=api_version,
            payload=payload,
        )

        by_id = {x["row_id"]: x for x in result.get("items", [])}

        for x in batch:
            lab = by_id.get(x["row_id"])
            if not lab:
                lab = {
                    "is_claim": False,
                    "is_author_perspective": False,
                    "claim_type": "other",
                    "confidence": 0.0,
                    "reason": "No label returned",
                }

            r = dict(rows[x["row_index"]])
            r["is_claim"] = str(bool(lab["is_claim"]))
            r["is_author_perspective"] = str(bool(lab["is_author_perspective"]))
            r["claim_type"] = lab["claim_type"]
            r["confidence"] = f'{float(lab["confidence"]):.2f}'
            r["llm_reason"] = lab["reason"]

            keep = (
                bool(lab["is_claim"])
                and (not bool(lab["is_author_perspective"]))
                and float(lab["confidence"]) >= args.min_confidence
            )
            if keep:
                strict_rows.append(r)
            else:
                non_rows.append(r)

        print(f"Batch {bi}/{len(batches)} done. Strict so far: {len(strict_rows)}")

    strict_path = os.path.join(args.outdir, "strict_claims.csv")
    non_path = os.path.join(args.outdir, "non_claims.csv")

    write_csv(strict_path, strict_rows, out_fields)
    write_csv(non_path, non_rows, out_fields)

    meta = {
        "input": args.input,
        "deployment": deployment,
        "api_version": api_version,
        "temperature": 0,
        "batch_size": args.batch_size,
        "min_confidence": args.min_confidence,
        "total_rows": len(rows),
        "strict_rows": len(strict_rows),
        "non_rows": len(non_rows),
    }
    with open(
        os.path.join(args.outdir, "openai_filter_metadata.json"), "w", encoding="utf-8"
    ) as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"Wrote {strict_path}")
    print(f"Wrote {non_path}")


if __name__ == "__main__":
    main()
