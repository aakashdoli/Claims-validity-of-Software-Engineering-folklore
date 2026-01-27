from __future__ import annotations
from typing import List

try:
    import pysbd
except ImportError as e:
    pysbd = None

class SentenceTokenizer:
    """
    Deterministic English sentence splitter.
    Uses pysbd when available; falls back to a conservative regex.
    """
    def __init__(self, language: str = "en"):
        self.language = language
        self._seg = None
        if pysbd is not None:
            self._seg = pysbd.Segmenter(language=language, clean=False)

    def split(self, text: str) -> List[str]:
        text = (text or "").strip()
        if not text:
            return []
        if self._seg:
            sents = self._seg.segment(text)
            return [s.strip() for s in sents if s.strip()]
        # fallback (less accurate)
        import re
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", text)
        return [p.strip() for p in parts if p.strip()]
