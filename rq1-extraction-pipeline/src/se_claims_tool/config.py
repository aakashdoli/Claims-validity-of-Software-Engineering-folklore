from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


DEFAULT_CUES = [
    # normative
    "should", "must", "recommended", "recommend", "best practice",

    # causal and effect
    "causes", "cause", "leads to", "lead to", "results in", "result in",
    "increases", "increase", "decreases", "decrease",
    "reduces", "reduce", "improves", "improve",
    "prevents", "prevent", "enables", "enable",

    # generalization and strong modality
    "often", "usually", "generally", "tend to", "tends to",
    "always", "never",

    # comparative and quantitative signals
    "better than", "worse than", "more than", "less than",
    "increases by", "decreases by", "reduces by",
]


@dataclass
class RunConfig:
    max_llm_calls: Optional[int] = None
    cue_phrases: List[str] = field(default_factory=lambda: DEFAULT_CUES.copy())
    case_insensitive: bool = True

    language: str = "en"
