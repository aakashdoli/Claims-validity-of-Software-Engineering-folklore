# src/se_claims_tool/llm/gemini_filter.py
"""
Gemini-based secondary filter for RQ1 claim candidates.

Takes an all_claims.csv produced by the rule-based pipeline and runs each
claim through Gemini to decide: keep (genuine SE claim) or reject (false positive).

Design principles:
- LLM is SECONDARY: it only filters, never generates new claims
- Every decision is recorded with a reason (fully auditable)
- Original CSV is never modified — outputs a new file
- Deterministic: temperature=0
- Batched: configurable batch size (default 20)
"""
from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Prompt ──────────────────────────────────────────────────────────────────

SYSTEM_INSTRUCTION = """You are a strict research assistant helping filter candidate claims from practitioner software engineering books.

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
- A pure personal anecdote with no generalizable lesson (e.g. "I once worked at a company where...")
- A question
- A code snippet or command
- A date, version number, or metadata line
- A book title, author name, or publisher line
- A transition sentence with no claim content (e.g. "In the next chapter, we will discuss...")

You will receive a JSON array of claim objects. For each, return a JSON array of decision objects.
Output ONLY valid JSON. No markdown fences, no commentary, no extra keys."""


USER_PROMPT_TEMPLATE = """Evaluate each claim below. For each one return:
- "claim_id": the exact claim_id from the input (string, copy exactly)
- "verdict": either "keep" or "reject"
- "reason": a short phrase explaining why (max 10 words)

Claims to evaluate:
{claims_json}

Return a JSON array with exactly {n} objects, one per claim, in the same order.
Example format:
[
  {{"claim_id": "CLM-000001", "verdict": "reject", "reason": "numbered table of contents entry"}},
  {{"claim_id": "CLM-000002", "verdict": "keep", "reason": "causal claim about team performance"}}
]"""


# ── Utility: list models available to an API key ─────────────────────────────

def list_available_models(api_key: str) -> List[str]:
    """
    Returns list of generative model names available for this API key.
    Used by the UI to populate the model dropdown dynamically.
    Raises an exception with a clear message if the key is invalid.
    """
    import google.generativeai as genai
    genai.configure(api_key=api_key.strip())
    models = []
    for m in genai.list_models():
        methods = getattr(m, "supported_generation_methods", [])
        if "generateContent" in methods and "gemini" in m.name:
            # Strip the "models/" prefix for display
            models.append(m.name.replace("models/", ""))
    return sorted(models)


# ── Core filter class ────────────────────────────────────────────────────────

class GeminiClaimFilter:
    """
    Filters a list of claim CSV rows using Google Gemini.

    Pass the exact model name (from list_available_models) — no auto-detection.

    Usage:
        models = list_available_models("YOUR_KEY")   # see what's available
        f = GeminiClaimFilter(api_key="YOUR_KEY", model=models[0])
        summary = f.filter_csv("all_claims.csv", "all_claims_filtered.csv")
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.0-flash",
        batch_size: int = 20,
        temperature: float = 0.0,
        max_retries: int = 3,
        retry_delay: float = 5.0,
    ):
        try:
            import google.generativeai as genai
        except ImportError as e:
            raise RuntimeError(
                "google-generativeai package not installed.\n"
                "Run: pip install google-generativeai"
            ) from e

        self._genai = genai
        self.batch_size = batch_size
        self.temperature = temperature
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.model_name = model

        key = api_key or os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "No Gemini API key found. Either pass api_key= or set "
                "GEMINI_API_KEY environment variable."
            )

        genai.configure(api_key=key)

        self.model = genai.GenerativeModel(
            model_name=model,
            system_instruction=SYSTEM_INSTRUCTION,
        )

    # ── public API ───────────────────────────────────────────────────────────

    def filter_csv(
        self,
        input_csv: str,
        output_csv: str,
        logger=None,
    ) -> Dict[str, Any]:
        rows = _read_csv(input_csv)
        if not rows:
            _write_filtered_csv(output_csv, [], {})
            return {"total": 0, "kept": 0, "rejected": 0, "unverified": 0}

        if logger:
            logger.info(
                f"Starting Gemini filter: {len(rows)} claims, model={self.model_name}"
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
            "model_used": self.model_name,
            "input_csv": str(input_csv),
            "output_csv": str(output_csv),
        }
        if logger:
            logger.info(
                f"Gemini filter done: {kept} kept, {rejected} rejected, "
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
                end = start + len(batch) - 1
                logger.info(f"Batch {i+1}/{len(batches)} (claims {start}-{end})")
            decisions.update(self._call_with_retry(batch, logger=logger))
        return decisions

    def _call_with_retry(self, batch, logger=None):
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return self._call_gemini(batch)
            except Exception as e:
                last_error = e
                if logger:
                    logger.warning(
                        f"Gemini error (attempt {attempt}/{self.max_retries}): "
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

    def _call_gemini(self, batch):
        claims_input = [
            {
                "claim_id": row["claim_id"],
                "claim_text": row["claim_text"],
                "trigger_rule": row.get("trigger_rule", ""),
            }
            for row in batch
        ]
        prompt = USER_PROMPT_TEMPLATE.format(
            claims_json=json.dumps(claims_input, ensure_ascii=False, indent=2),
            n=len(batch),
        )
        response = self.model.generate_content(
            prompt,
            generation_config=self._genai.types.GenerationConfig(temperature=self.temperature),
        )
        raw_text = (response.text or "").strip()
        if not raw_text:
            raise ValueError("Gemini returned empty response")

        parsed = _safe_parse_json(raw_text)
        if not isinstance(parsed, list):
            raise ValueError(f"Expected JSON list, got: {raw_text[:200]}")

        result = {}
        for item in parsed:
            cid = str(item.get("claim_id", "")).strip()
            verdict = str(item.get("verdict", "")).strip().lower()
            reason = str(item.get("reason", "")).strip()
            if verdict not in ("keep", "reject"):
                verdict, reason = "unverified", f"unexpected_verdict: {verdict}"
            if cid:
                result[cid] = {"verdict": verdict, "reason": reason}

        for row in batch:
            if row["claim_id"] not in result:
                result[row["claim_id"]] = {"verdict": "unverified", "reason": "missing_from_response"}

        return result


# ── CSV helpers ──────────────────────────────────────────────────────────────

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
            out["llm_reason"] = dec["reason"]
            writer.writerow(out)


def _chunk(lst, size):
    return [lst[i: i + size] for i in range(0, len(lst), size)]


def _safe_parse_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("```")).strip()
    return json.loads(text)