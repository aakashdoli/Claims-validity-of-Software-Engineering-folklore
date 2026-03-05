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
    Precision-first claim detector for SE folklore thesis.

    A CLAIM is a falsifiable declarative sentence asserting a generalizable
    proposition about SE practice — aligned with Davide Fucci's definition.

    Signal types (all must be falsifiable):
      - NORMATIVE:      "should", "must", "recommend", "best practice"
      - CAUSAL:         "leads to", "causes", "improves", "reduces"
      - COMPARATIVE:    "better than", "more effective than"
      - QUANTITATIVE:   "80%", "2x", "twice", "most teams"
      - GENERALIZATION: "typically", "often", "usually", "many engineers"

    AUTHOR_PERSPECTIVE is NOT a claim signal.
    "In my experience..." / "I believe..." = personal opinion hedge.
    These weaken falsifiability. They are rejected UNLESS the sentence
    also contains a strong falsifiable signal (NORMATIVE or CAUSAL or COMPARATIVE).
    "I recommend X" is kept because "recommend" = NORMATIVE.
    "We found that X improves Y" is kept because "improves" = CAUSAL.
    "In my experience, teams skip review" is rejected — no falsifiable signal.
    """

    _NORMATIVE = re.compile(
        r"\b(should|must|need\s+to|have\s+to|recommend(?:ed)?|best\s+practice|"
        r"it\s+is\s+important|critical\s+to|essential\s+to|key\s+to|"
        r"avoid|never\s+do|always\s+do|don['\u2019]t|do\s+not)\b",
        re.IGNORECASE,
    )

    _CAUSAL = re.compile(
        r"\b(leads?\s+to|results?\s+in|causes?|caused\s+by|prevents?|"
        r"enables?|drives?|contributes?\s+to|improves?|reduces?|increases?|"
        r"decreases?|speeds?\s+up|slows?\s+down|makes?\s+it\s+(?:easier|harder|faster|better)|"
        r"helps?\s+(?:teams?|developers?|engineers?|managers?|organizations?|you|us))\b",
        re.IGNORECASE,
    )

    _COMPARATIVE = re.compile(
        r"\b(better\s+than|worse\s+than|"
        r"more\s+(?:effective|efficient|productive|important|reliable|valuable)|"
        r"less\s+(?:effective|efficient|productive|important|reliable|valuable)|"
        r"faster\s+than|slower\s+than|superior\s+to|preferred\s+over)\b",
        re.IGNORECASE,
    )

    _QUANT = re.compile(
        r"""
        (?:
            \b\d+(?:\.\d+)?\s*%
          | \btwice\b
          | \b\d+\s+times\b
          | \b(?:increases?|decreases?|reduces?|improves?)\s+by\b
          | \b\d+x\b
          | \b(?:doubled|tripled|halved)\b
          | \bmajority\b
          | \bmost\s+(?:engineers?|developers?|teams?|projects?|companies|bugs?|defects?|issues?|people)\b
          | \bhalf\s+(?:of\s+)?(?:engineers?|developers?|teams?|projects?|bugs?)\b
        )
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    _GENERALIZATION = re.compile(
        r"\b(often|usually|generally|tends?\s+to|typically|always|never|"
        r"in\s+most\s+cases|in\s+general|by\s+and\s+large|"
        r"(?:most|many|few|some)\s+(?:engineers?|developers?|teams?|companies|projects?|managers?|organizations?|people))\b",
        re.IGNORECASE,
    )

    # Opinion hedges — personal, not universally falsifiable
    # Reject if sentence starts with or is dominated by these
    # UNLESS also has NORMATIVE or CAUSAL or COMPARATIVE signal
    _OPINION_HEDGE = re.compile(
        r"^\s*(?:in\s+my\s+(?:experience|view|opinion|career)|"
        r"i\s+(?:believe|think|feel|suppose|find\s+that|have\s+found\s+that)|"
        r"from\s+my\s+(?:experience|perspective|years)|"
        r"in\s+(?:my|our)\s+(?:experience|opinion|view|practice))",
        re.IGNORECASE,
    )

    # Pure personal story patterns
    _PURE_ANECDOTE = re.compile(
        r"\b(i\s+(?:was|went|had|got|felt|said|told|asked|decided|started|tried|"
        r"remember|recall|once|used\s+to)|"
        r"when\s+i\s+was\s+(?:a|working|at|in)|"
        r"at\s+my\s+(?:last|previous|first|old)\s+(?:job|company|team)|"
        r"my\s+(?:friend|colleague|boss|manager)\s+(?:told|said|asked))\b",
        re.IGNORECASE,
    )

    _JOKE_FRAMING = re.compile(
        r"\b(jokingly|sarcastically|as\s+a\s+joke|just\s+kidding|just\s+joking)\b",
        re.IGNORECASE,
    )

    _SE_CONTEXT = re.compile(
        r"\b(software|codebase|code|coding|developer|development|engineer(?:ing)?|"
        r"technical|strategy|tests?|testing|unit\s+tests?|tdd|bdd|code\s+review|"
        r"pull\s+request|pr\b|refactor(?:ing)?|technical\s+debt|architecture|"
        r"design\s+pattern|requirements?|ci\b|cd\b|ci/cd|deployment|deploy(?:ing)?|"
        r"release|bug|defect|maintainab|performance|security|reliability|scalab|"
        r"team|teams|management|manager|leader(?:ship)?|"
        r"agile|scrum|sprint|kanban|standup|retrospective|"
        r"product|feature|roadmap|backlog|ticket|issue|"
        r"on.?call|incident|postmortem|sre\b|devops|"
        r"staff\s+engineer|senior\s+engineer|principal\s+engineer|tech\s+lead|"
        r"feedback|mentor(?:ing|ship)?|hiring|interview|"
        r"pair\s+programming|mob\s+programming|documentation|docs|"
        r"system\s+design|distributed\s+system|microservice|monolith|api\b|"
        r"abstraction|complexity|coupling|cohesion|dependency|"
        r"productivity|velocity|throughput|cycle\s+time|lead\s+time)\b",
        re.IGNORECASE,
    )

    _HEADING_LIKE = re.compile(
        r"^(?:chapter|section|part|figure|table|appendix)\s+\d", re.IGNORECASE
    )

    def detect(self, sent) -> DetectionResult:
        txt = (getattr(sent, "text", "") or "").strip()

        # Basic sanity
        if not txt:
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"reason": "empty"})
        if len(txt) < 30:
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"reason": "too_short"})
        if txt.endswith(":"):
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"reason": "heading"})
        if txt.endswith("?"):
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"reason": "question"})
        if self._HEADING_LIKE.match(txt):
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"reason": "heading"})

        # Joke framing — always reject
        if self._JOKE_FRAMING.search(txt):
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"reason": "joke_framing"})

        # Must have SE context
        if not self._SE_CONTEXT.search(txt):
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"reason": "no_se_context"})

        # Detect signals
        has_norm    = self._NORMATIVE.search(txt)
        has_causal  = self._CAUSAL.search(txt)
        has_comp    = self._COMPARATIVE.search(txt)
        has_quant   = self._QUANT.search(txt)
        has_gen     = self._GENERALIZATION.search(txt)
        has_anecdote = self._PURE_ANECDOTE.search(txt)

        any_claim_signal = has_norm or has_causal or has_comp or has_quant or has_gen

        # No signal = reject
        if not any_claim_signal:
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"reason": "no_claim_signal"})

        # Pure anecdote with no real signal = reject
        if has_anecdote and not any_claim_signal:
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"reason": "pure_anecdote"})

        # Opinion hedge filter:
        # "In my experience..." / "I believe..." / "From my experience..."
        # These are personal opinions — not universally falsifiable.
        # REJECT unless the sentence ALSO contains NORMATIVE or CAUSAL or COMPARATIVE
        # (i.e. a strong falsifiable signal beyond just generalization/quantitative)
        # Reason: "In my experience, most teams..." is still just a personal observation.
        # But "In my experience, you should always..." has NORMATIVE — keep it.
        # And "We found that TDD improves quality" has CAUSAL — keep it.
        if self._OPINION_HEDGE.search(txt):
            if not (has_norm or has_causal or has_comp):
                return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"reason": "opinion_hedge_no_strong_signal"})

        # Score
        rules_fired = []
        terms = []
        score = 0.60

        if has_norm:   rules_fired.append("NORMATIVE");      terms.append(has_norm.group(0));   score += 0.20
        if has_causal: rules_fired.append("CAUSAL");         terms.append(has_causal.group(0)); score += 0.15
        if has_comp:   rules_fired.append("COMPARATIVE");    terms.append(has_comp.group(0));   score += 0.10
        if has_quant:  rules_fired.append("QUANTITATIVE");   terms.append(has_quant.group(0));  score += 0.08
        if has_gen:    rules_fired.append("GENERALIZATION"); terms.append(has_gen.group(0));    score += 0.07

        return DetectionResult(True, txt, min(0.95, max(0.0, score)), "unknown", {
            "mode": "rule",
            "trigger_rule": "|".join(rules_fired),
            "trigger_terms": "|".join(terms),
        })