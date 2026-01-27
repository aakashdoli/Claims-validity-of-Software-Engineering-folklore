from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional

DEFAULT_CUES = [
    "causes", "cause", "leads to", "lead to", "results in", "result in",
    "increases", "increase", "reduces", "reduce", "improves", "improve",
    "prevents", "prevent", "makes", "make", "due to", "therefore", "thus",
    "helps", "help", "hurts", "hurt", "boosts", "boost", "decreases", "decrease",
    "raises", "raise", "lowers", "lower", "drives", "drive", "enables", "enable",
]

@dataclass
class RunConfig:
    max_llm_calls: Optional[int] = None
    cue_phrases: List[str] = field(default_factory=lambda: DEFAULT_CUES.copy())
    case_insensitive: bool = True

    # privacy: if False, we only store claim snippets + IDs in outputs
    store_only_snippets: bool = True

    # sentence tokenization
    language: str = "en"
