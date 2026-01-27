from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Tuple

from .candidate_filter import CandidateFilter
from .citations import extract_citations
from .config import RunConfig
from .models import SentenceRecord, ClaimRecord
from .tokenize import SentenceTokenizer
from .ingest.epub_ingest import ingest_epub
from .ingest.pdf_ingest import ingest_pdf


def ingest_sentences(input_path: str, tokenizer: SentenceTokenizer) -> List[SentenceRecord]:
    p = Path(input_path)
    suffix = p.suffix.lower()

    if suffix == ".epub":
        return list(ingest_epub(str(p), tokenizer))
    if suffix == ".pdf":
        return list(ingest_pdf(str(p), tokenizer))

    raise ValueError(f"Unsupported file type: {suffix}. Only .epub and .pdf")


def build_context(sentences: List[SentenceRecord], idx: int) -> Tuple[str, str, str]:
    pre = sentences[idx - 1].text if idx - 1 >= 0 else ""
    claim = sentences[idx].text
    post = sentences[idx + 1].text if idx + 1 < len(sentences) else ""
    return pre, claim, post


def extract_claims(
    input_path: str,
    cfg: RunConfig,
    detector,
    logger,
) -> Tuple[List[ClaimRecord], Dict[str, Any]]:
    """
    End-to-end extraction for a single book (PDF/EPUB):
    - ingest sentences
    - heuristic candidate filter
    - detector (offline rule-based OR azure)
    - always build 3-sentence context
    - add claim_serial + page/spine fields + citation extraction
    """
    tok = SentenceTokenizer(language=cfg.language)
    sentences = ingest_sentences(input_path, tok)

    cand_filter = CandidateFilter(cfg)

    claims: List[ClaimRecord] = []
    tested = 0
    claim_serial = 0

    for i, s in enumerate(sentences):
        if not cand_filter.is_candidate(s):
            continue

        if cfg.max_llm_calls is not None and tested >= cfg.max_llm_calls:
            logger.warning("Max sentence tests reached; stopping detection.")
            break

        res = detector.detect(s)
        tested += 1

        if not res.is_claim:
            continue

        pre, claim_text, post = build_context(sentences, i)
        cites = extract_citations(claim_text)

        claim_serial += 1
        claims.append(
            ClaimRecord(
                claim_serial=claim_serial,
                book_id=s.book_id,
                source_path=s.source_path,
                chapter_id=s.chapter_id,
                chapter_title=s.chapter_title,
                paragraph_id=s.paragraph_id,
                sentence_index=s.sentence_index,
                global_sentence_index=s.global_sentence_index,
                page_number=s.page_number,
                spine_index=s.spine_index,
                pre_context=pre,
                claim=claim_text,
                post_context=post,
                citations=cites,
                label=res.label,
                confidence=res.confidence,
                detector=("azure" if detector.__class__.__name__.lower().startswith("azure") else "rule"),
                extra=res.raw,
            )
        )

    meta = {
        "input": str(Path(input_path).name),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "language": cfg.language,
        "cue_phrases": cfg.cue_phrases,
        "max_llm_calls": cfg.max_llm_calls,
        "total_sentences": len(sentences),
        "candidates_tested": tested,
        "claims_found": len(claims),
    }
    return claims, meta
