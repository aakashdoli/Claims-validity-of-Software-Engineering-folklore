from __future__ import annotations

from dataclasses import dataclass

# Exact column order required by your thesis instrument
RQ1_CSV_COLUMNS = [
    "claim_id",
    "book_id",
    "book_title",
    "chapter_title",
    "section_title",
    "paragraph_index",
    "location_text",
    "ebook_locator",
    "claim_text",
    "sentence_index",
    "citation_status",
    "citation_marker_text",
    "citation_marker_location_text",
    "citation_context",
    "confidence",
    "notes",
    "verified",
    "verifier",
    "verification_notes",
]


@dataclass
class RQ1ClaimRow:
    claim_id: str
    book_id: str
    book_title: str
    chapter_title: str
    section_title: str
    paragraph_index: int
    location_text: str
    ebook_locator: str
    claim_text: str
    sentence_index: int
    citation_status: str  # cited | not_cited | ambiguous
    citation_marker_text: str
    citation_marker_location_text: str
    citation_context: str
    confidence: float
    notes: str = ""
    verified: str = ""
    verifier: str = ""
    verification_notes: str = ""
