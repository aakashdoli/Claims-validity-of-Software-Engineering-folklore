from __future__ import annotations
import json
import re
from dataclasses import dataclass
from typing import Dict, Any, List

from ..models import SentenceRecord
from .prompt_templates import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE


@dataclass
class DetectionResult:
    is_claim: bool
    claim: str
    confidence: float
    label: str
    raw: Dict[str, Any]


# ---------------------------
# OFFLINE (NO API) DETECTOR
# ---------------------------
class RuleBasedClaimDetector:
    """
    Offline detector: strict causal-language rules.
    - Zero hallucination: returns sentence verbatim or NO_CLAIM
    - Filters intention/aspiration phrasing (e.g., "strive to", "aim to")
    - Requires explicit cause/effect indicators
    """

    # Phrases that often indicate intent rather than a claim of effect
    _INTENT_PHRASES = [
        "strive to", "aim to", "try to", "trying to", "attempt to", "plan to",
        "hope to", "want to", "wants to", "would like to", "we should",
        "should try", "should aim", "focus on", "focusing on",
    ]

    # Strong causal connectors
    _CONNECTORS = [
        r"\bleads?\s+to\b",
        r"\bresults?\s+in\b",
        r"\bcauses?\b",
        r"\bdrives?\b",
        r"\bcontributes?\s+to\b",
        r"\bcreates?\b",
        r"\btriggers?\b",
        r"\benables?\b",
        r"\bprevents?\b",
    ]

    # Change verbs with outcomes (we validate outcomes separately)
    _CHANGE_VERBS = [
        r"\bincreases?\b", r"\bdecreases?\b",
        r"\breduces?\b", r"\blowers?\b", r"\braises?\b",
        r"\bimproves?\b", r"\bworsens?\b",
        r"\bboosts?\b", r"\bhurts?\b", r"\bhelps?\b",
        r"\bmakes?\b",
    ]

    # Common outcomes for SE folklore (expand freely)
    _OUTCOMES = [
        "productivity", "speed", "velocity", "throughput", "delivery", "time",
        "quality", "defects", "bugs", "reliability", "maintainability",
        "security", "performance", "complexity", "cost", "risk",
        "collaboration", "communication", "morale", "happiness",
        "effective", "efficiency", "efficient", "faster", "slower",
        "easier", "harder", "better", "worse", "unhappy",
        "nitpicking", "bullying",
    ]

    # Practice/process vocabulary (broad; helps reduce non-SE sentences)
    _PRACTICES = [
        "code review", "reviews", "review",
        "testing", "tdd", "unit test", "tests",
        "refactor", "refactoring",
        "microservices", "monolith",
        "continuous integration", "ci", "continuous delivery", "cd",
        "release", "releases", "deploy", "deployment",
        "linter", "lint", "format", "formatting",
        "agile", "scrum", "kanban", "sprint", "standup", "retrospective",
        "pair programming", "pairing",
        "documentation", "requirements", "estimation",
        "architecture", "design",
        "team", "manager", "lead", "leadership", "process",
        "technical debt",
    ]

    def __init__(self):
        self._intent_re = re.compile("|".join(re.escape(p) for p in self._INTENT_PHRASES), re.IGNORECASE)
        self._conn_re = re.compile("|".join(self._CONNECTORS), re.IGNORECASE)
        self._change_re = re.compile("|".join(self._CHANGE_VERBS), re.IGNORECASE)

        self._outcome_re = re.compile(r"\b(" + "|".join(re.escape(o) for o in self._OUTCOMES) + r")\b", re.IGNORECASE)
        self._practice_re = re.compile(r"\b(" + "|".join(re.escape(p) for p in self._PRACTICES) + r")\b", re.IGNORECASE)

    def detect(self, sent: SentenceRecord) -> DetectionResult:
        txt = (sent.text or "").strip()
        low = txt.lower()

        if not txt:
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"mode": "rule", "reason": "empty"})

        # Exclude obvious headings / fragments
        if len(txt) < 15 or txt.endswith(":"):
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"mode": "rule", "reason": "too_short_or_heading"})

        # Intent filter: "strive to", "aim to", etc.
        if self._intent_re.search(txt):
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"mode": "rule", "reason": "intent_phrase"})

        # Must mention some SE practice/process/team context (broad)
        has_practice = bool(self._practice_re.search(txt))

        # Must have explicit causal connector OR change verb
        has_connector = bool(self._conn_re.search(txt))
        has_change = bool(self._change_re.search(txt))

        if not (has_connector or has_change):
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"mode": "rule", "reason": "no_causal_marker"})

        # Must mention an outcome-ish term (helps reduce false positives)
        has_outcome = bool(self._outcome_re.search(txt))
        if not has_outcome:
            # Allow some "makes everyone X" cases even if outcome word list misses it
            if not re.search(r"\bmakes?\s+.+\b(more|less)\b", low):
                return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"mode": "rule", "reason": "no_outcome_term"})

        # If it has causality but no practice terms, still allow if it clearly refers to team impact
        if not has_practice and not re.search(r"\b(team|engineer|developers?|code)\b", low):
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"mode": "rule", "reason": "not_se_context"})

        # Confidence scoring (simple + transparent)
        score = 0.45
        if has_connector:
            score += 0.25
        if has_change:
            score += 0.15
        if has_practice:
            score += 0.10
        if re.search(r"\b(can|may|might)\b", low):
            score -= 0.05  # weaker modality
        score = max(0.0, min(0.95, score))

        # Labeling (lightweight; you can expand)
        label = "unknown"
        if re.search(r"\b(defect|bugs?|quality)\b", low):
            label = "quality"
        elif re.search(r"\b(productivity|velocity|throughput|faster|speed)\b", low):
            label = "productivity"
        elif re.search(r"\b(maintainability|refactor|technical debt)\b", low):
            label = "maintainability"
        elif re.search(r"\b(security|risk)\b", low):
            label = "security"
        elif re.search(r"\b(performance)\b", low):
            label = "performance"
        elif re.search(r"\b(collaboration|communication|morale|happiness|unhappy)\b", low):
            label = "team"

        return DetectionResult(True, txt, score, label, {"mode": "rule", "has_connector": has_connector, "has_change": has_change})


# ---------------------------
# AZURE DETECTOR (for later)
# ---------------------------
class AzureClaimDetector:
    def __init__(self, client):
        self.client = client

    def detect(self, sent: SentenceRecord) -> DetectionResult:
        import json as _json

        user_prompt = USER_PROMPT_TEMPLATE.format(sentence=sent.text)
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

        # Enforce verbatim
        if is_claim and claim != sent.text:
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"error": "non_verbatim", "model_claim": claim})

        if not is_claim or claim == "NO_CLAIM":
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", data)

        confidence = max(0.0, min(1.0, confidence))
        return DetectionResult(True, claim, confidence, label, data)
