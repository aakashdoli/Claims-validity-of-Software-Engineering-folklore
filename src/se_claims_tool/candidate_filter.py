from __future__ import annotations

import re
from typing import List

from .config import RunConfig


class CandidateFilter:
    def __init__(self, cfg: RunConfig):
        flags = re.IGNORECASE if cfg.case_insensitive else 0

        cues: List[str] = []
        for cue in cfg.cue_phrases:
            cue = (cue or "").strip()
            if cue:
                cues.append(re.escape(cue))

        if cues:
            pattern = r"(" + r"|".join(cues) + r")"
            self._re = re.compile(pattern, flags)
        else:
            self._re = None

    def is_candidate_text(self, text: str) -> bool:
        if not self._re:
            return False
        t = (text or "").strip()
        if not t:
            return False
        return bool(self._re.search(t))
