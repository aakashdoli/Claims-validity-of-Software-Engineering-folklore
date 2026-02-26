# src/se_claims_tool/llm/azure_filter.py
"""
Azure OpenAI secondary filter for RQ1 claim candidates.

Same design as gemini_filter.py — takes all_claims.csv, writes all_claims_filtered.csv
with two extra columns: llm_verdict (keep/reject/unverified) and llm_reason.

Reads credentials from environment variables (or .env file):
  AZURE_OPENAI_ENDPOINT
  AZURE_OPENAI_API_KEY
  AZURE_OPENAI_API_VERSION
  AZURE_OPENAI_DEPLOYMENT

These are already in your .env.example. Copy to .env and fill in the values
from BTH IT (4th floor J-building).
"""
from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Prompt ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a strict research assistant helping filter candidate claims from practitioner software engineering books.

Your job is to decide whether each sentence is a GENUINE GENERALIZABLE CLAIM about software engineering practice, or a FALSE POSITIVE that was incorrectly extracted.

A sentence IS a genuine claim if it:
- Makes a general statement about software engineering, teams, code, or technical practice
- Prescribes behaviour (you should, must, recommended)
- States a causal relationship (X leads to Y, X causes Y)
- Asserts a comparative or quantitative effect (X is better than Y, reduces by N%)
- Generalizes beyond a single anecdote (teams generally..., developers tend to...)

A sentence IS a false positive if it is:
- A numbered chapter heading or table of contents entry (e.g. "3. Distinguish between management and leadership")
- A bibliography or reference entry (e.g. "21. Andrew S. Grove, High Output Management, 2015, p.110")
- A pure personal anecdote with no generalizable lesson
- A question, code snippet, date, metadata, or transition sentence

You will receive a JSON array of claims. Return a JSON object with a single key "results"
containing an array of decisions. Output ONLY valid JSON, no markdown, no commentary."""

USER_PROMPT_TEMPLATE = """Evaluate each claim. For each return:
- "claim_id": exact claim_id from input
- "verdict": "keep" or "reject"  
- "reason": short phrase, max 10 words

Claims:
{claims_json}

Return exactly this JSON structure:
{{"results": [
  {{"claim_id": "CLM-000001", "verdict": "keep", "reason": "causal claim about team performance"}},
  {{"claim_id": "CLM-000002", "verdict": "reject", "reason": "numbered table of contents entry"}}
]}}"""


# ── Core filter class ────────────────────────────────────────────────────────

class AzureClaimFilter:
    """
    Filters claim CSV rows using BTH Azure OpenAI (GPT-4.1).

    Credentials are read from environment variables. Set them in your .env file:
      AZURE_OPENAI_ENDPOINT=https://bth-ai.azure-api.net/student
      AZURE_OPENAI_API_KEY=<key from BTH IT>
      AZURE_OPENAI_API_VERSION=2024-02-15-preview
      AZURE_OPENAI_DEPLOYMENT=<deployment name>

    Usage:
        f = AzureClaimFilter()
        summary = f.filter_csv("all_claims.csv", "all_claims_filtered.csv")
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        api_version: Optional[str] = None,
        deployment: Optional[str] = None,
        batch_size: int = 20,
        max_retries: int = 3,
        retry_delay: float = 5.0,
    ):
        try:
            from openai import AzureOpenAI
        except ImportError as e:
            raise RuntimeError("openai package not installed. Run: pip install openai") from e

        self.batch_size = batch_size
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Accept explicit params or fall back to environment variables
        _endpoint = (endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT", "")).strip().rstrip("/")
        _key      = (api_key or os.environ.get("AZURE_OPENAI_API_KEY", "")).strip()
        _version  = (api_version or os.environ.get("AZURE_OPENAI_API_VERSION", "")).strip()
        _deploy   = (deployment or os.environ.get("AZURE_OPENAI_DEPLOYMENT", "")).strip()

        # Normalize endpoint
        if _endpoint.endswith("/openai"):
            _endpoint = _endpoint[: -len("/openai")]

        if not _endpoint:
            raise RuntimeError("Missing AZURE_OPENAI_ENDPOINT — check your .env file")
        if not _key:
            raise RuntimeError("Missing AZURE_OPENAI_API_KEY — check your .env file")
        if not _version:
            raise RuntimeError("Missing AZURE_OPENAI_API_VERSION — check your .env file")
        if not _deploy:
            raise RuntimeError("Missing AZURE_OPENAI_DEPLOYMENT — check your .env file")

        self.deployment = _deploy
        self.client = AzureOpenAI(
            azure_endpoint=_endpoint,
            api_key=_key,
            api_version=_version,
        )

    # ── public API ───────────────────────────────────────────────────────────

    def filter_csv(
        self,
        input_csv: str,
        output_csv: str,
        logger=None,
    ) -> Dict[str, Any]:
        """
        Read input_csv, filter every row with Azure OpenAI, write output_csv.
        Returns summary dict with counts.
        """
        rows = _read_csv(input_csv)
        if not rows:
            _write_filtered_csv(output_csv, [], {})
            return {"total": 0, "kept": 0, "rejected": 0, "unverified": 0}

        if logger:
            logger.info(
                f"Starting Azure filter: {len(rows)} claims, "
                f"deployment={self.deployment}"
            )

        decisions = self._filter_rows(rows, logger=logger)
        _write_filtered_csv(output_csv, rows, decisions)

        kept       = sum(1 for d in decisions.values() if d["verdict"] == "keep")
        rejected   = sum(1 for d in decisions.values() if d["verdict"] == "reject")
        unverified = sum(1 for d in decisions.values() if d["verdict"] == "unverified")

        summary = {
            "total": len(rows),
            "kept": kept,
            "rejected": rejected,
            "unverified": unverified,
            "deployment": self.deployment,
            "input_csv": str(input_csv),
            "output_csv": str(output_csv),
        }
        if logger:
            logger.info(
                f"Azure filter done: {kept} kept, {rejected} rejected, "
                f"{unverified} unverified out of {len(rows)} total"
            )
        return summary

    # ── internal ─────────────────────────────────────────────────────────────

    def _filter_rows(self, rows, logger=None):
        decisions = {}
        batches = _chunk(rows, self.batch_size)
        for i, batch in enumerate(batches):
            if logger:
                start = i * self.batch_size + 1
                end   = start + len(batch) - 1
                logger.info(f"Azure filtering batch {i+1}/{len(batches)} (claims {start}-{end})")
            decisions.update(self._call_with_retry(batch, logger=logger))
        return decisions

    def _call_with_retry(self, batch, logger=None):
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return self._call_azure(batch)
            except Exception as e:
                last_error = e
                if logger:
                    logger.warning(
                        f"Azure API error (attempt {attempt}/{self.max_retries}): "
                        f"{type(e).__name__}: {e}"
                    )
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * attempt)

        error_msg = f"{type(last_error).__name__}: {str(last_error)[:200]}" if last_error else "unknown"
        if logger:
            logger.error(f"All retries failed. Error: {error_msg}")
        return {
            row["claim_id"]: {"verdict": "unverified", "reason": error_msg}
            for row in batch
        }

    def _call_azure(self, batch):
        claims_input = [
            {
                "claim_id":    row["claim_id"],
                "claim_text":  row["claim_text"],
                "trigger_rule": row.get("trigger_rule", ""),
            }
            for row in batch
        ]

        prompt = USER_PROMPT_TEMPLATE.format(
            claims_json=json.dumps(claims_input, ensure_ascii=False, indent=2),
        )

        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        raw_text = (response.choices[0].message.content or "").strip()
        if not raw_text:
            raise ValueError("Azure returned empty response")

        parsed = json.loads(raw_text)

        # Response is {"results": [...]}
        items = parsed.get("results", parsed) if isinstance(parsed, dict) else parsed
        if not isinstance(items, list):
            raise ValueError(f"Unexpected response structure: {raw_text[:200]}")

        result = {}
        for item in items:
            cid     = str(item.get("claim_id", "")).strip()
            verdict = str(item.get("verdict",  "")).strip().lower()
            reason  = str(item.get("reason",   "")).strip()
            if verdict not in ("keep", "reject"):
                verdict = "unverified"
                reason  = f"unexpected_verdict: {verdict}"
            if cid:
                result[cid] = {"verdict": verdict, "reason": reason}

        # Any rows the API missed
        for row in batch:
            if row["claim_id"] not in result:
                result[row["claim_id"]] = {
                    "verdict": "unverified",
                    "reason":  "missing_from_api_response",
                }
        return result


# ── CSV helpers (shared with gemini_filter) ───────────────────────────────────

def _read_csv(path: str) -> List[Dict[str, str]]:
    rows = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            rows.append(dict(row))
    return rows


def _write_filtered_csv(path, rows, decisions):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        p.write_text("(no rows)\n", encoding="utf-8")
        return
    original_fields = list(rows[0].keys())
    extra = [c for c in ["llm_verdict", "llm_reason"] if c not in original_fields]
    fieldnames = original_fields + extra
    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            dec = decisions.get(row.get("claim_id", ""), {"verdict": "unverified", "reason": "not_processed"})
            out = dict(row)
            out["llm_verdict"] = dec["verdict"]
            out["llm_reason"]  = dec["reason"]
            writer.writerow(out)


def _chunk(lst, size):
    return [lst[i: i + size] for i in range(0, len(lst), size)]