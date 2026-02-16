from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class DetectionResult:
    is_claim: bool
    claim: str
    confidence: float
    label: str
    raw: Dict[str, Any]


class RuleBasedClaimDetector:
    """
    Precision-first claim detector.
    """

    _NORMATIVE = re.compile(r"\b(should|must|recommend|recommended|best practice|you should)\b", re.IGNORECASE)
    _CAUSAL = re.compile(r"\b(leads?\s+to|results?\s+in|causes?|prevents?|enables?|drives?|contributes?\s+to)\b", re.IGNORECASE)
    _COMPARATIVE = re.compile(r"\b(better than|worse than|more than|less than)\b", re.IGNORECASE)
    _QUANT = re.compile(r"\b\d+(\.\d+)?\s*%?\b|\btwice\b|\b\d+\s+times\b|\b(increases?|decreases?|reduces?)\s+by\b", re.IGNORECASE)
    _GENERALIZATION = re.compile(r"\b(often|usually|generally|tends?\s+to|typically|always|never)\b", re.IGNORECASE)

    _FIRST_PERSON = re.compile(r"\b(i|we|my|our|i've|we've|i’m|we’re|i\s+jokingly)\b", re.IGNORECASE)

    _SE_CONTEXT = re.compile(
        r"\b(software|code|coding|developer|engineer|engineering|testing|tests|unit test|tdd|code review|pull request|refactor|technical debt|architecture|design|requirements|ci|deployment|deploy|release|bug|defect|maintainability|performance|security|reliability|team|teams|management|manager|leadership)\b",
        re.IGNORECASE,
    )

    def detect(self, sent) -> DetectionResult:
        txt = (getattr(sent, "text", "") or "").strip()
        if not txt:
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"reason": "empty"})

        if len(txt) < 25:
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"reason": "too_short"})
        if txt.endswith(":"):
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"reason": "heading"})
        if txt.endswith("?"):
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"reason": "question"})

        # Must mention SE practice context
        if not self._SE_CONTEXT.search(txt):
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"reason": "no_se_context"})

        has_norm = bool(self._NORMATIVE.search(txt))
        has_causal = bool(self._CAUSAL.search(txt))
        has_comp = bool(self._COMPARATIVE.search(txt))
        has_quant = bool(self._QUANT.search(txt))
        has_gen = bool(self._GENERALIZATION.search(txt))

        if not (has_norm or has_causal or has_comp or has_quant or has_gen):
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"reason": "no_claim_signal"})

        # Reject first-person narrative unless it is clearly generalizing or recommending
        if self._FIRST_PERSON.search(txt) and not (has_gen or has_norm):
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"reason": "first_person_narrative"})

        score = 0.60
        if has_norm:
            score += 0.20
        if has_causal:
            score += 0.15
        if has_comp:
            score += 0.10
        if has_quant:
            score += 0.05
        if has_gen:
            score += 0.05

        score = max(0.0, min(0.95, score))
        return DetectionResult(True, txt, float(score), "unknown", {"mode": "rule"})
