"""
llm/azure_llm_filter.py
-----------------------
Azure OpenAI LLM filter for SE claim candidates.

Purpose:
    Takes NLP candidate sentences (with surrounding context) and asks the LLM
    to make the precise final decision: is this a genuine SE claim?

Design decisions (from meetings with Davide Fucci & Greg Wilson):
    - LLM receives: previous sentence + claim sentence + next sentence
    - LLM uses the thesis claim definition as the grounding
    - Batches of 15 candidates per API call (balances cost vs speed)
    - BTH Azure endpoint: https://bth-ai.azure-api.net/student/openai/deployments/gpt-4o-mini/chat/completions

Credentials (in .env):
    AZURE_OPENAI_ENDPOINT   = https://bth-ai.azure-api.net/student
    AZURE_OPENAI_API_KEY    = <key from BTH IT / Davide>
    AZURE_OPENAI_DEPLOYMENT = gpt-4o-mini
    AZURE_OPENAI_API_VERSION= 2024-02-01
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# ── Thesis claim definition (grounded in literature) ──────────────────────────
# Source: Meeting 3 with Davide Fucci & Greg Wilson, 26 Feb 2026
# "A claim is a declarative sentence that asserts a generalizable proposition
#  about software engineering practice, behavior, process, tools, or outcomes,
#  which is falsifiable or evaluable against empirical evidence."

SYSTEM_PROMPT = """\
You are a precise research assistant helping extract SE folklore claims from practitioner software engineering books for an academic thesis.

CLAIM DEFINITION:
A claim is a declarative sentence that asserts a GENERALIZABLE PROPOSITION about software engineering practice, behavior, process, tools, or outcomes, which is FALSIFIABLE or EVALUABLE against empirical evidence.

CLAIM TYPES:
- NORMATIVE: prescriptive statements (should, must, best practice, recommend)
- CAUSAL: cause-effect relationships (leads to, results in, causes, prevents)
- COMPARATIVE: relative comparisons (better than, more effective, preferred over)
- QUANTITATIVE: numerical/measurable assertions (%, 2x, majority, reduces by)
- GENERALIZATION: broad patterns (often, usually, most engineers, typically)
- AUTHOR_PERSPECTIVE: personal assertions (in my experience, I believe, I found)

IMPORTANT — Author perspective claims ARE valid SE folklore claims. A statement like "In my experience, teams that skip code review accumulate debt" IS a claim because it makes a generalizable assertion about SE practice.

REJECT if the sentence is:
- A numbered chapter/ToC heading (e.g. "3. Managing your team")
- A bibliography or reference entry
- A pure personal story with no generalizable lesson ("I went to the office and...")
- A question, code snippet, date, or metadata
- A transition sentence with no assertion ("In the next chapter, we will...")
- A definition or factual statement about how a technology works (not a practice claim)

You receive a JSON array of candidates, each with:
- candidate_id: identifier
- prev_sentence: sentence before the candidate (context)
- candidate_sentence: the sentence to evaluate  
- next_sentence: sentence after the candidate (context)
- nlp_type: what NLP pattern triggered (hints at claim type)

Return ONLY valid JSON, no markdown, no commentary.
"""

USER_PROMPT_TEMPLATE = """\
Evaluate each candidate. Use the context (prev/next sentences) to understand meaning.

For each return:
- "candidate_id": exact id from input
- "is_claim": true or false
- "claim_type": one of NORMATIVE|CAUSAL|COMPARATIVE|QUANTITATIVE|GENERALIZATION|AUTHOR_PERSPECTIVE (or NONE if not a claim)
- "is_author_perspective": true if the claim uses first-person author assertion ("I believe", "in my experience"), else false
- "confidence": 0.0-1.0
- "reason": brief explanation, max 12 words

Candidates:
{candidates_json}

Return exactly:
{{"results": [
  {{"candidate_id": "C-001", "is_claim": true, "claim_type": "CAUSAL", "is_author_perspective": false, "confidence": 0.9, "reason": "causal link between code review and defect reduction"}},
  {{"candidate_id": "C-002", "is_claim": false, "claim_type": "NONE", "is_author_perspective": false, "confidence": 0.95, "reason": "numbered table of contents entry"}}
]}}"""


@dataclass
class LLMFilterResult:
    candidate_id: str
    is_claim: bool
    claim_type: str
    is_author_perspective: bool
    confidence: float
    reason: str
    error: str = ""


class AzureLLMFilter:
    """
    Filters NLP candidate sentences using BTH Azure OpenAI (gpt-4o-mini).

    Each candidate is sent with its surrounding context:
        [prev_sentence] + [candidate_sentence] + [next_sentence]

    This matches the explicit requirement from the thesis supervisors:
        "You should pass the claim along with a couple of surrounding sentences
         in the prompt." — Davide Fucci, Meeting 3
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        api_version: Optional[str] = None,
        deployment: Optional[str] = None,
        batch_size: int = 15,
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

        _endpoint = (endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT", "")).strip().rstrip("/")
        _key      = (api_key or os.environ.get("AZURE_OPENAI_API_KEY", "")).strip()
        _version  = (api_version or os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01")).strip()
        _deploy   = (deployment or os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")).strip()

        # Normalize endpoint — strip trailing /openai if present
        if _endpoint.endswith("/openai"):
            _endpoint = _endpoint[: -len("/openai")]

        if not _endpoint:
            raise RuntimeError("Missing AZURE_OPENAI_ENDPOINT — check your .env file")
        if not _key:
            raise RuntimeError("Missing AZURE_OPENAI_API_KEY — check your .env file")

        self.deployment = _deploy
        self.client = AzureOpenAI(
            azure_endpoint=_endpoint,
            api_key=_key,
            api_version=_version,
        )

    def filter_candidates(
        self,
        candidates: List[Dict[str, str]],
        logger=None,
    ) -> Dict[str, LLMFilterResult]:
        """
        Filter a list of candidate dicts.

        Each candidate dict must have:
            candidate_id, prev_sentence, candidate_sentence, next_sentence, nlp_type

        Returns dict mapping candidate_id -> LLMFilterResult
        """
        if not candidates:
            return {}

        if logger:
            logger.info(
                f"LLM filter: {len(candidates)} candidates, "
                f"deployment={self.deployment}, batch_size={self.batch_size}"
            )

        results: Dict[str, LLMFilterResult] = {}
        batches = _chunk(candidates, self.batch_size)

        for i, batch in enumerate(batches):
            if logger:
                start = i * self.batch_size + 1
                end   = start + len(batch) - 1
                logger.info(f"LLM batch {i+1}/{len(batches)} (candidates {start}-{end})")

            batch_results = self._call_with_retry(batch, logger=logger)
            results.update(batch_results)

        return results

    def _call_with_retry(
        self, batch: List[Dict], logger=None
    ) -> Dict[str, LLMFilterResult]:
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
            c["candidate_id"]: LLMFilterResult(
                candidate_id=c["candidate_id"],
                is_claim=False,
                claim_type="NONE",
                is_author_perspective=False,
                confidence=0.0,
                reason="unverified",
                error=error_msg,
            )
            for c in batch
        }

    def _call_azure(self, batch: List[Dict]) -> Dict[str, LLMFilterResult]:
        # Build input — include context for each candidate
        candidates_input = [
            {
                "candidate_id":       c["candidate_id"],
                "prev_sentence":      c.get("prev_sentence", ""),
                "candidate_sentence": c["candidate_sentence"],
                "next_sentence":      c.get("next_sentence", ""),
                "nlp_type":           c.get("nlp_type", ""),
            }
            for c in batch
        ]

        prompt = USER_PROMPT_TEMPLATE.format(
            candidates_json=json.dumps(candidates_input, ensure_ascii=False, indent=2)
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
        items = parsed.get("results", parsed) if isinstance(parsed, dict) else parsed
        if not isinstance(items, list):
            raise ValueError(f"Unexpected response structure: {raw_text[:200]}")

        result: Dict[str, LLMFilterResult] = {}
        for item in items:
            cid = str(item.get("candidate_id", "")).strip()
            if not cid:
                continue
            result[cid] = LLMFilterResult(
                candidate_id=cid,
                is_claim=bool(item.get("is_claim", False)),
                claim_type=str(item.get("claim_type", "NONE")).upper(),
                is_author_perspective=bool(item.get("is_author_perspective", False)),
                confidence=float(item.get("confidence", 0.5)),
                reason=str(item.get("reason", "")),
            )

        # Any candidates the API missed get marked as unverified
        for c in batch:
            if c["candidate_id"] not in result:
                result[c["candidate_id"]] = LLMFilterResult(
                    candidate_id=c["candidate_id"],
                    is_claim=False,
                    claim_type="NONE",
                    is_author_perspective=False,
                    confidence=0.0,
                    reason="missing_from_api_response",
                    error="missing_from_api_response",
                )

        return result


def _chunk(lst: list, size: int) -> list:
    return [lst[i: i + size] for i in range(0, len(lst), size)]
