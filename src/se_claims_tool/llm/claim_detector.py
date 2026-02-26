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

    Captures:
      - Normative:       "you should...", "teams must...", "best practice is..."
      - Causal:          "TDD leads to fewer bugs", "code reviews prevent defects"
      - Comparative:     "X is better than Y for large teams"
      - Quantitative:    "80% of bugs...", "reduces time by 2x"
      - Generalization:  "engineers typically...", "most teams..."
      - Author perspective: "in my experience teams that skip review accumulate debt"
        KEPT because author assertions = core SE folklore claims for the thesis.

    Rejects:
      - Pure personal anecdotes with no generalizable claim signal
      - Headings, questions, empty/short lines
      - Non-SE content
    """

    _NORMATIVE = re.compile(
        r"\b(should|must|need\s+to|have\s+to|recommend(?:ed)?|best\s+practice|"
        r"it\s+is\s+important|critical\s+to|essential\s+to|key\s+to|"
        r"avoid|never\s+do|always\s+do|don['']t|do\s+not)\b",
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

    # Only meaningful quantitative signals — NOT plain list numbers
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

    # Author perspective claims — the core of SE folklore
    _AUTHOR_PERSPECTIVE = re.compile(
        r"\b(in\s+my\s+(?:experience|view|opinion|career)|"
        r"i\s+(?:believe|think|argue|have\s+(?:found|seen|noticed|observed|learned)|strongly\s+believe)|"
        r"i\s+(?:always|never|often|usually|typically)\s+(?:recommend|advise|suggest|tell)|"
        r"we\s+(?:believe|think|argue|have\s+found|found\s+that)|"
        r"the\s+best\s+(?:engineers?|developers?|teams?|managers?)\s+(?:i\s+(?:know|have\s+worked\s+with|have\s+met)|are|tend|always|never)|"
        r"from\s+my\s+(?:experience|perspective|observation|years)|"
        r"in\s+(?:our|my)\s+(?:experience|research|work|practice))\b",
        re.IGNORECASE,
    )

    # Pure personal story — only reject if NO claim signal exists
    _PURE_ANECDOTE = re.compile(
        r"\b(i\s+(?:was|went|had|got|felt|said|told|asked|decided|started|tried|"
        r"remember|recall|once|used\s+to)|"
        r"when\s+i\s+was\s+(?:a|working|at|in)|"
        r"at\s+my\s+(?:last|previous|first|old)\s+(?:job|company|team)|"
        r"my\s+(?:friend|colleague|boss|manager)\s+(?:told|said|asked))\b",
        re.IGNORECASE,
    )

    # Joke/sarcastic framing — always reject regardless of other signals
    _JOKE_FRAMING = re.compile(
        r"\b(jokingly|sarcastically|as\s+a\s+joke|just\s+kidding|just\s+joking)\b",
        re.IGNORECASE,
    )

    # Broad SE context — covers all practitioner book topics
    _SE_CONTEXT = re.compile(
        r"\b(software|codebase|code|coding|developer|development|engineer(?:ing)?|"
        r"tests?|testing|unit\s+tests?|tdd|bdd|code\s+review|pull\s+request|pr\b|"
        r"refactor(?:ing)?|technical\s+debt|architecture|design\s+pattern|"
        r"requirements?|ci\b|cd\b|ci/cd|deployment|deploy(?:ing)?|release|"
        r"bug|defect|maintainab|performance|security|reliability|scalab|"
        r"team|teams|management|manager|leader(?:ship)?|"
        r"agile|scrum|sprint|kanban|standup|retrospective|"
        r"product|feature|roadmap|backlog|ticket|issue|"
        r"on.?call|incident|postmortem|sre\b|devops|"
        r"staff\s+engineer|senior\s+engineer|principal\s+engineer|tech\s+lead|"
        r"feedback|mentor(?:ing|ship)?|hiring|interview|"
        r"pair\s+programming|mob\s+programming|documentation|docs|"
        r"system\s+design|distributed\s+system|microservice|monolith|api\b|"
        r"abstraction|complexity|coupling|cohesion|dependency|"
        r"productivity|velocity|throughput|cycle\s+time|lead\s+time|"
        r"craft|craftsman(?:ship)?|engineering\s+(?:culture|practice|career|growth)|"
        r"learning|grow(?:th|ing)|skill|career)\b",
        re.IGNORECASE,
    )

    _HEADING_LIKE = re.compile(
        r"^(?:chapter|section|part|figure|table|appendix)\s+\d", re.IGNORECASE
    )

    def detect(self, sent) -> DetectionResult:
        txt = (getattr(sent, "text", "") or "").strip()

        # ── Basic sanity ───────────────────────────────────────────────────────
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

        # ── Joke framing — always reject ───────────────────────────────────────
        if self._JOKE_FRAMING.search(txt):
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"reason": "joke_framing"})

        # ── Must have SE context ───────────────────────────────────────────────
        if not self._SE_CONTEXT.search(txt):
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"reason": "no_se_context"})

        has_norm     = self._NORMATIVE.search(txt)
        has_causal   = self._CAUSAL.search(txt)
        has_comp     = self._COMPARATIVE.search(txt)
        has_quant    = self._QUANT.search(txt)
        has_gen      = self._GENERALIZATION.search(txt)
        has_author   = self._AUTHOR_PERSPECTIVE.search(txt)
        has_anecdote = self._PURE_ANECDOTE.search(txt)

        any_claim_signal = has_norm or has_causal or has_comp or has_quant or has_gen

        # ── Author perspective + claim signal = KEEP (SE folklore core) ────────
        if has_author and any_claim_signal:
            rules_fired = ["AUTHOR_PERSPECTIVE"]
            terms = [has_author.group(0)]
            score = 0.70
            if has_norm:   rules_fired.append("NORMATIVE");       terms.append(has_norm.group(0));   score += 0.15
            if has_causal: rules_fired.append("CAUSAL");          terms.append(has_causal.group(0)); score += 0.10
            if has_gen:    rules_fired.append("GENERALIZATION");   terms.append(has_gen.group(0));    score += 0.05
            if has_quant:  rules_fired.append("QUANTITATIVE");     terms.append(has_quant.group(0));  score += 0.05
            return DetectionResult(True, txt, min(0.95, score), "author_perspective", {
                "mode": "rule", "trigger_rule": "|".join(rules_fired), "trigger_terms": "|".join(terms),
            })

        # ── Pure anecdote with no claim signal = REJECT ────────────────────────
        if has_anecdote and not any_claim_signal:
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"reason": "pure_anecdote"})

        # ── No claim signal at all = REJECT ────────────────────────────────────
        if not (any_claim_signal or has_author):
            return DetectionResult(False, "NO_CLAIM", 0.0, "none", {"reason": "no_claim_signal"})

        # ── Score ──────────────────────────────────────────────────────────────
        rules_fired = []
        terms = []
        score = 0.60

        if has_norm:   rules_fired.append("NORMATIVE");       terms.append(has_norm.group(0));   score += 0.20
        if has_causal: rules_fired.append("CAUSAL");          terms.append(has_causal.group(0)); score += 0.15
        if has_comp:   rules_fired.append("COMPARATIVE");     terms.append(has_comp.group(0));   score += 0.10
        if has_quant:  rules_fired.append("QUANTITATIVE");    terms.append(has_quant.group(0));  score += 0.08
        if has_gen:    rules_fired.append("GENERALIZATION");   terms.append(has_gen.group(0));    score += 0.07
        if has_author: rules_fired.append("AUTHOR_PERSPECTIVE"); terms.append(has_author.group(0)); score += 0.05

        return DetectionResult(True, txt, min(0.95, max(0.0, score)), "unknown", {
            "mode": "rule", "trigger_rule": "|".join(rules_fired), "trigger_terms": "|".join(terms),
        })
