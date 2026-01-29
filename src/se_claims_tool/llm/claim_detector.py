from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict

from .prompt_templates import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE


@dataclass
class DetectionResult:
    is_claim: bool
    claim: str
    confidence: float
    label: str
    raw: Dict[str, Any]


class RuleBasedClaimDetector:
    """
    Precision-first detector aligned to thesis claim definition:
    - declarative, generalizable relationship, effect, recommendation, explanation
    - includes normative, causal, comparative, quantitative, descriptive-generalization
    - excludes headings, fragments, anecdotes without generalization
    """

    _INTENT_PHRASES = [
        "strive to", "aim to", "try to", "trying to", "attempt to", "plan to",
        "hope to", "want to", "would like to",
    ]

    _NORMATIVE = [
        r"\bshould\b", r"\bmust\b", r"\brecommend(ed)?\b", r"\bbest practice\b",
        r"\bit is better to\b", r"\byou should\b",
    ]

    _CAUSAL = [
        r"\bleads?\s+to\b",
        r"\bresults?\s+in\b",
        r"\bcauses?\b",
        r"\bprevents?\b",
        r"\benables?\b",
        r"\bdrives?\b",
        r"\bcontributes?\s+to\b",
    ]

    _COMPARATIVE = [
        r"\bbetter than\b", r"\bworse than\b",
        r"\bmore than\b", r"\bless than\b",
    ]

    _QUANT = [
        r"\b\d+(\.\d+)?\s*%?\b",
        r"\btwice\b", r"\b\d+\s+times\b",
        r"\b(increases?|decreases?|reduces?)\s+by\b",
    ]

    _GENERALIZATION = [
        r"\boften\b", r"\busually\b", r"\bgenerally\b",
        r"\btends?\s+to\b", r"\btypically\b",
        r"\balways\b", r"\bnever\b",
    ]

    _SE_CONTEXT = [
        "software", "code", "coding", "developer", "developers", "engineer", "engineers",
        "testing", "tests", "unit test", "tdd",
        "code review", "review", "pull request", "pr",
        "refactor", "refactoring", "technical debt",
        "architecture", "design", "requirements",
        "build", "ci", "continuous integration", "deployment", "deploy", "release",
        "bug", "bugs", "defect", "defects",
        "maintainability", "performance", "security", "reliability",
        "team", "teams",
    ]

    def __init__(self):
        self._intent_re = re.compile("|".join(re.escape(p) for p in self._INTENT_PHRASES), re.IGNORECASE)

        self._norm_re = re.compile("|".join(self._NORMATIVE), re.IGNORECASE)
        self._causal_re = re.compile("|".join(self._CAUSAL), re.IGNORECASE)
        self._comp_re = re.compile("|".join(self._COMPARATIVE), re.IGNORECASE)
        self._quant_re = re.compile("|".join(self._QUANT), re.IGNORECASE)
        self._gen_re = re.compile("|".join(self._GENERALIZATION), re.IGNORECASE)

        self._se_re = re.compile(
            r"\b(" + "|".join(re.escape(t) for t in self._SE_CONTEXT) + r")\b",
            re.IGNORECASE,
        )

    def detect(self, sent) -> DetectionResult:
        txt = (getattr(sent, "text", "") or "").strip()
        low = txt.lower()

        if not txt:
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"mode": "rule", "reason": "empty"})

        # Exclude headings and fragments
        if len(txt) < 20:
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"mode": "rule", "reason": "too_short"})
        if txt.endswith(":"):
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"mode": "rule", "reason": "heading_colon"})
        if txt.endswith("?"):
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"mode": "rule", "reason": "question"})

        # Exclude intent statements
        if self._intent_re.search(txt):
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"mode": "rule", "reason": "intent_phrase"})

        # Must have SE context
        if not self._se_re.search(txt):
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"mode": "rule", "reason": "no_se_context"})

        # Must have at least one strong claim signal
        has_norm = bool(self._norm_re.search(txt))
        has_causal = bool(self._causal_re.search(txt))
        has_comp = bool(self._comp_re.search(txt))
        has_quant = bool(self._quant_re.search(txt))
        has_gen = bool(self._gen_re.search(txt))

        if not (has_norm or has_causal or has_comp or has_quant or has_gen):
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"mode": "rule", "reason": "no_claim_signal"})

        # Exclude pure anecdotes without generalization
        if re.search(r"\b(i|we)\b", low) and not has_gen and not has_norm:
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"mode": "rule", "reason": "anecdote_without_generalization"})

        score = 0.55
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

        if re.search(r"\b(can|may|might)\b", low):
            score -= 0.05

        score = max(0.0, min(0.95, score))

        label = "unknown"
        if re.search(r"\b(defect|bugs?|quality)\b", low):
            label = "quality"
        elif re.search(r"\b(productivity|faster|speed|velocity|throughput)\b", low):
            label = "productivity"
        elif re.search(r"\b(maintainability|refactor|technical debt)\b", low):
            label = "maintainability"
        elif re.search(r"\b(security|risk)\b", low):
            label = "security"
        elif re.search(r"\b(performance)\b", low):
            label = "performance"
        elif re.search(r"\b(team|communication|collaboration|morale)\b", low):
            label = "team"

        return DetectionResult(True, txt, score, label, {"mode": "rule"})



class AzureClaimDetector:
    def __init__(self, client):
        self.client = client

    def detect(self, sent) -> DetectionResult:
        import json as _json

        user_prompt = USER_PROMPT_TEMPLATE.format(sentence=getattr(sent, "text", ""))
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        content = self.client.chat_json(messages, temperature=0.0)

        try:
            data = _json.loads(content)
        except Exception:
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"error": "invalid_json", "content": content})

        claim = str(data.get("claim", "NO_CLAIM"))
        is_claim = bool(data.get("is_claim", False))
        confidence = float(data.get("confidence", 0.0))
        label = str(data.get("label", "none"))

        if is_claim and claim != getattr(sent, "text", ""):
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"error": "non_verbatim", "model_claim": claim})

        if not is_claim or claim == "NO_CLAIM":
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", data)

        confidence = max(0.0, min(1.0, confidence))
        return DetectionResult(True, claim, confidence, label, data)
