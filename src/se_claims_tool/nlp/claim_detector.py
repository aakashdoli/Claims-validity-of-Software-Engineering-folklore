"""
nlp/claim_detector.py
---------------------
NLP pre-filter for SE claim candidates.

Purpose:
    Quickly narrow down thousands of sentences to a smaller set of CANDIDATES
    that are worth sending to the Azure LLM. This stage should have HIGH RECALL
    (don't miss real claims) and is deliberately loose — the LLM does the
    precise filtering.

Claim definition (from thesis meetings with Davide Fucci & Greg Wilson):
    "A claim is a declarative sentence that asserts a generalizable proposition
    about software engineering practice, behavior, process, tools, or outcomes,
    which is falsifiable or evaluable against empirical evidence."

Claim types:
    NORMATIVE      — prescriptive (should, must, best practice)
    CAUSAL         — cause/effect (leads to, results in, causes, prevents)
    COMPARATIVE    — relative (better than, worse than, more effective)
    QUANTITATIVE   — measurable (%, 2x, reduces by, majority)
    GENERALIZATION — broad patterns (often, usually, most engineers)
    AUTHOR_PERSPECTIVE — personal assertion (in my experience, I believe)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class NLPCandidateResult:
    is_candidate: bool
    claim_type: str        # NORMATIVE | CAUSAL | COMPARATIVE | QUANTITATIVE | GENERALIZATION | AUTHOR_PERSPECTIVE | NONE
    matched_pattern: str   # which pattern triggered
    matched_term: str      # the actual term that matched


class NLPClaimDetector:
    """
    Loose NLP pre-filter. Returns True for any sentence that MIGHT be a claim.
    The Azure LLM will make the final precise decision.
    """

    # ── NORMATIVE ─────────────────────────────────────────────────────────────
    # Prescriptive statements about what should/must be done
    _NORMATIVE = re.compile(
        r"\b("
        r"should|must|ought\s+to|need\s+to|have\s+to|has\s+to|"
        r"recommend(?:ed|s)?|best\s+practice|good\s+practice|"
        r"it\s+is\s+(?:important|critical|essential|key|vital|necessary)|"
        r"you\s+(?:should|must|need|want\s+to|have\s+to)|"
        r"teams?\s+(?:should|must|need|ought)|"
        r"(?:always|never)\s+(?:do|use|write|test|deploy|review|commit|merge)|"
        r"avoid|don['']t|do\s+not|make\s+sure|ensure|"
        r"aim\s+to|strive\s+to|try\s+to|be\s+sure\s+to|"
        r"rule\s+(?:of\s+thumb|is)|principle\s+(?:is|here)|"
        r"it\s+pays\s+to|it\s+is\s+worth"
        r")\b",
        re.IGNORECASE,
    )

    # ── CAUSAL ────────────────────────────────────────────────────────────────
    # Cause-effect relationships
    _CAUSAL = re.compile(
        r"\b("
        r"leads?\s+to|results?\s+in|causes?|caused\s+by|"
        r"prevents?|enables?|drives?|contributes?\s+to|"
        r"improves?|reduces?|increases?|decreases?|"
        r"speeds?\s+up|slows?\s+down|makes?\s+(?:it\s+)?(?:easier|harder|faster|better|worse)|"
        r"helps?\s+(?:teams?|developers?|engineers?|managers?|you|us|people)|"
        r"allows?\s+(?:teams?|developers?|engineers?|you)|"
        r"so\s+that|because\s+of|due\s+to|as\s+a\s+result|"
        r"therefore|thus|hence|consequently|"
        r"if\s+you\s+(?:do|use|write|skip|ignore|avoid)|"
        r"when\s+(?:teams?|developers?|engineers?)\s+(?:do|use|adopt|skip)|"
        r"leads?\s+to\s+(?:better|worse|more|fewer|less)"
        r")\b",
        re.IGNORECASE,
    )

    # ── COMPARATIVE ───────────────────────────────────────────────────────────
    # Relative comparisons between approaches/practices
    _COMPARATIVE = re.compile(
        r"\b("
        r"better\s+than|worse\s+than|superior\s+to|inferior\s+to|"
        r"more\s+(?:effective|efficient|productive|reliable|important|valuable|scalable|maintainable)|"
        r"less\s+(?:effective|efficient|productive|reliable|important|valuable)|"
        r"faster\s+than|slower\s+than|cheaper\s+than|easier\s+than|harder\s+than|"
        r"preferred\s+(?:over|to)|preferred\s+approach|"
        r"outperforms?|beats?|surpasses?|"
        r"compared\s+to|in\s+comparison|relative\s+to|"
        r"the\s+(?:best|worst|most\s+effective|most\s+efficient)\s+(?:way|approach|practice|strategy)"
        r")\b",
        re.IGNORECASE,
    )

    # ── QUANTITATIVE ──────────────────────────────────────────────────────────
    # Numerical or measurable claims
    _QUANTITATIVE = re.compile(
        r"""
        (?:
            \b\d+(?:\.\d+)?\s*%           # percentages: 80%, 12.5%
          | \btwice\b|\bthrice\b           # multipliers
          | \b\d+\s*(?:times|x)\b         # 2 times, 3x
          | \b(?:increases?|decreases?|reduces?|improves?|cuts?)\s+by\b  # changes by amount
          | \b\d+x\b                       # 2x, 10x
          | \b(?:doubled|tripled|halved|quadrupled)\b
          | \bmajority\b|\bminority\b
          | \bmost\s+(?:engineers?|developers?|teams?|projects?|companies|bugs?|defects?|people|organizations?)\b
          | \bhalf\s+(?:of\s+)?(?:engineers?|developers?|teams?|projects?|bugs?|the\s+time)\b
          | \bone\s+(?:in|out\s+of)\s+(?:three|four|five|ten|\d+)\b
          | \b(?:nearly|almost|roughly|approximately)\s+(?:all|every|half)\b
          | \b(?:on\s+average|average\s+(?:of|time|developer))\b
          | \b(?:orders?\s+of\s+magnitude)\b
        )
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    # ── GENERALIZATION ────────────────────────────────────────────────────────
    # Broad patterns and tendencies
    _GENERALIZATION = re.compile(
        r"\b("
        r"often|usually|generally|tends?\s+to|typically|"
        r"always|never|rarely|seldom|frequently|commonly|"
        r"in\s+most\s+cases|in\s+general|by\s+and\s+large|as\s+a\s+rule|"
        r"(?:most|many|few|some|all|every)\s+(?:engineers?|developers?|teams?|companies|projects?|managers?|organizations?|people|practitioners?|seniors?|juniors?)|"
        r"(?:most|many|few|some)\s+(?:software|codebases?|systems?|projects?)|"
        r"\bmost\s+\w+\s+(?:struggle|fail|succeed|tend|find|prefer|avoid|ignore|overlook|underestimate|overestimate)\b|"
        r"(?:engineers?|developers?|teams?|managers?)\s+(?:often|usually|typically|generally|tend\s+to|always|never)|"
        r"(?:it\s+is\s+(?:common|rare|unusual|typical|normal)\s+(?:to|for))|"
        r"(?:a\s+(?:common|typical|classic|frequent)\s+(?:mistake|problem|issue|pattern|practice))|"
        r"(?:tend\s+to\s+be|tend\s+to\s+have|tend\s+to\s+use|tend\s+to\s+become)"
        r")\b",
        re.IGNORECASE,
    )

    # ── AUTHOR PERSPECTIVE ────────────────────────────────────────────────────
    # Personal assertions — core SE folklore (keep per meeting decision)
    _AUTHOR_PERSPECTIVE = re.compile(
        r"\b("
        r"in\s+my\s+(?:experience|view|opinion|career|observation|years)|"
        r"i\s+(?:believe|think|argue|feel|find|know|suggest|recommend|advise)|"
        r"i\s+have\s+(?:found|seen|noticed|observed|learned|discovered)|"
        r"i\s+(?:always|never|often|usually|typically)\s+(?:recommend|advise|suggest|tell|say)|"
        r"we\s+(?:believe|think|argue|have\s+found|found\s+that|recommend|suggest)|"
        r"from\s+my\s+(?:experience|perspective|observation|years|time)|"
        r"in\s+(?:our|my)\s+(?:experience|research|work|practice|team)|"
        r"the\s+best\s+(?:engineers?|developers?|teams?|managers?)\s+(?:i\s+(?:know|have\s+worked\s+with|have\s+met)|always|never|tend)|"
        r"i\s+(?:strongly\s+)?believe\s+that|"
        r"(?:my|our)\s+(?:advice|recommendation|suggestion|view)\s+is"
        r")\b",
        re.IGNORECASE,
    )

    # ── SE CONTEXT ────────────────────────────────────────────────────────────
    # Must relate to software engineering — filters out generic life advice
    _SE_CONTEXT = re.compile(
        r"\b("
        r"software|code(?:base)?|coding|developer|development|engineer(?:ing)?|"
        r"test(?:ing|s)?|unit\s+test|tdd|bdd|code\s+review|pull\s+request|\bpr\b|"
        r"refactor(?:ing)?|technical\s+debt|architecture|design\s+pattern|"
        r"ci\b|cd\b|ci/cd|deployment|deploy(?:ing)?|release|"
        r"bug|defect|maintainab|performance|security|reliability|scalab|"
        r"team|management|manager|leader(?:ship)?|"
        r"agile|scrum|sprint|kanban|standup|retrospective|"
        r"product|feature|roadmap|backlog|ticket|"
        r"on.?call|incident|postmortem|sre\b|devops|"
        r"staff\s+engineer|senior\s+engineer|principal|tech\s+lead|"
        r"feedback|mentor(?:ing|ship)?|hiring|interview|onboarding|"
        r"pair\s+programming|mob\s+programming|documentation|"
        r"system\s+design|distributed|microservice|monolith|\bapi\b|"
        r"abstraction|complexity|coupling|cohesion|dependency|"
        r"productivity|velocity|throughput|cycle\s+time|"
        r"craft|engineering\s+(?:culture|practice|career|growth)|"
        r"learning|career|skill(?:s)?|codebase|repository|commit|branch|merge|"
        r"sprint|iteration|delivery|ownership|accountability"
        r")\b",
        re.IGNORECASE,
    )

    # ── REJECT PATTERNS ───────────────────────────────────────────────────────
    _HEADING_LIKE = re.compile(
        r"^(?:chapter|section|part|figure|table|appendix)\s+\d", re.IGNORECASE
    )
    _REFERENCE_LIKE = re.compile(
        r"^\d+[\.\)]\s+\w.*\d{4}",  # numbered bibliography entries
        re.IGNORECASE,
    )

    def detect(self, sentence_text: str) -> NLPCandidateResult:
        txt = (sentence_text or "").strip()

        # ── Hard rejects ──────────────────────────────────────────────────────
        if not txt or len(txt) < 30:
            return NLPCandidateResult(False, "NONE", "too_short", "")
        if txt.endswith("?"):
            return NLPCandidateResult(False, "NONE", "question", "")
        if txt.endswith(":"):
            return NLPCandidateResult(False, "NONE", "heading_colon", "")
        if self._HEADING_LIKE.match(txt):
            return NLPCandidateResult(False, "NONE", "heading", "")
        if self._REFERENCE_LIKE.match(txt):
            return NLPCandidateResult(False, "NONE", "reference_entry", "")

        # ── Must have SE context ──────────────────────────────────────────────
        if not self._SE_CONTEXT.search(txt):
            return NLPCandidateResult(False, "NONE", "no_se_context", "")

        # ── Check claim type patterns (order = priority) ──────────────────────
        checks = [
            ("NORMATIVE",           self._NORMATIVE),
            ("CAUSAL",              self._CAUSAL),
            ("COMPARATIVE",         self._COMPARATIVE),
            ("QUANTITATIVE",        self._QUANTITATIVE),
            ("GENERALIZATION",      self._GENERALIZATION),
            ("AUTHOR_PERSPECTIVE",  self._AUTHOR_PERSPECTIVE),
        ]

        for claim_type, pattern in checks:
            m = pattern.search(txt)
            if m:
                return NLPCandidateResult(
                    is_candidate=True,
                    claim_type=claim_type,
                    matched_pattern=claim_type,
                    matched_term=m.group(0),
                )

        return NLPCandidateResult(False, "NONE", "no_claim_pattern", "")
