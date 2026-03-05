from __future__ import annotations
from dataclasses import dataclass

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
    "prev_sentence",       # NEW: context before claim
    "next_sentence",       # NEW: context after claim
    "sentence_index",
    "citation_status",
    "citation_marker_text",
    "citation_marker_location_text",
    "citation_context",
    "nlp_claim_type",      # NEW: what NLP detected (NORMATIVE, CAUSAL, etc.)
    "nlp_matched_term",    # NEW: the exact term that triggered NLP
    "llm_is_claim",        # NEW: LLM final decision (True/False)
    "llm_claim_type",      # NEW: LLM assigned type
    "llm_is_author_perspective",  # NEW: LLM flagged as author perspective
    "llm_confidence",      # NEW: LLM confidence score
    "llm_reason",          # NEW: LLM reasoning
    "llm_error",           # NEW: any LLM API error
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
    prev_sentence: str          # sentence before claim (context)
    next_sentence: str          # sentence after claim (context)
    sentence_index: int
    citation_status: str        # cited | not_cited | ambiguous
    citation_marker_text: str
    citation_marker_location_text: str
    citation_context: str
    nlp_claim_type: str = ""    # NORMATIVE | CAUSAL | COMPARATIVE | QUANTITATIVE | GENERALIZATION | AUTHOR_PERSPECTIVE
    nlp_matched_term: str = ""  # the keyword that triggered NLP
    llm_is_claim: str = ""      # "True" or "False"
    llm_claim_type: str = ""    # LLM's claim type classification
    llm_is_author_perspective: str = ""
    llm_confidence: str = ""
    llm_reason: str = ""
    llm_error: str = ""
    confidence: float = 0.0
    notes: str = ""
    verified: str = ""
    verifier: str = ""
    verification_notes: str = ""
