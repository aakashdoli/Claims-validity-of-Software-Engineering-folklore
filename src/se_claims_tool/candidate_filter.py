from __future__ import annotations
import re
from typing import List
from .models import SentenceRecord
from .config import RunConfig

class CandidateFilter:
    def __init__(self, cfg: RunConfig):
        flags = re.IGNORECASE if cfg.case_insensitive else 0
        # phrase-level matching; escape cues but allow whitespace
        pattern_parts: List[str] = []
        for cue in cfg.cue_phrases:
            cue = cue.strip()
            if not cue:
                continue
            pattern_parts.append(re.escape(cue))
        pattern = r"(" + r"|".join(pattern_parts) + r")"
        self._re = re.compile(pattern, flags) if pattern_parts else None

    def is_candidate(self, s: SentenceRecord) -> bool:
        if self._re is None:
            return False
        return bool(self._re.search(s.text))
