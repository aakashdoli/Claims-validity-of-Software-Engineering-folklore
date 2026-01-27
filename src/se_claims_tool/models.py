from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

@dataclass(frozen=True)
class SentenceRecord:
    book_id: str
    source_path: str

    # Location / traceability
    chapter_id: str
    chapter_title: str
    paragraph_id: str
    sentence_index: int
    global_sentence_index: int

    # New: page / spine info
    page_number: Optional[int] = None      # PDF: 1-based; EPUB: None
    spine_index: Optional[int] = None      # EPUB: spine order index; PDF: None

    text: str = ""


@dataclass(frozen=True)
class ClaimRecord:
    # New: serial / claim id
    claim_serial: int                      # 1..N within run

    book_id: str
    source_path: str

    # Location / traceability
    chapter_id: str
    chapter_title: str
    paragraph_id: str
    sentence_index: int
    global_sentence_index: int

    # New: page / spine info
    page_number: Optional[int] = None
    spine_index: Optional[int] = None

    # Context window (3 sentences)
    pre_context: str = ""
    claim: str = ""
    post_context: str = ""

    # New: citations extracted from claim sentence
    citations: List[str] = None

    label: str = "unknown"
    confidence: float = 0.0
    detector: str = "rule"
    extra: Dict[str, Any] = None
