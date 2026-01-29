from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple


RE_NUMERIC = re.compile(r"\[(\s*\d+(\s*[-–]\s*\d+)?(\s*,\s*\d+(\s*[-–]\s*\d+)?)*)\s*\]")
RE_AUTHOR_YEAR_PARENS = re.compile(r"\(([^()]{2,80}?\b(?:19|20)\d{2}[a-z]?)\)")
RE_INLINE_AUTHOR_YEAR = re.compile(
    r"\b([A-Z][A-Za-z\-]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z\-]+|\s+et\s+al\.)?)\s*\(((?:19|20)\d{2}[a-z]?)\)"
)
RE_URL = re.compile(r"\bhttps?://\S+\b", re.IGNORECASE)

RE_CROSSREF = re.compile(
    r"\b(see|as shown in|as described in)\s+(figure|fig\.|table|chapter|section)\b",
    re.IGNORECASE,
)

FOOTNOTE_MARKERS = ["*", "†", "‡", "¹", "²", "³", "⁴", "⁵"]


@dataclass(frozen=True)
class CitationDecision:
    citation_status: str  # cited | ambiguous | not_cited
    citation_marker_text: str
    citation_marker_location_text: str
    citation_context: str


def _dedup_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out


def _context_window(text: str, start: int, width: int = 240) -> str:
    if not text:
        return ""
    left = max(0, start - width)
    right = min(len(text), start + width)
    return text[left:right].strip()


def _find_markers_in_text(text: str) -> List[Tuple[str, int]]:
    """
    Returns list of (marker_text, start_index) for all supported marker types.
    """
    t = text or ""
    found: List[Tuple[str, int]] = []

    for m in RE_NUMERIC.finditer(t):
        found.append(("[" + m.group(1).strip() + "]", m.start()))

    for m in RE_AUTHOR_YEAR_PARENS.finditer(t):
        if re.search(r"(?:19|20)\d{2}", m.group(1)):
            found.append(("(" + m.group(1).strip() + ")", m.start()))

    for m in RE_INLINE_AUTHOR_YEAR.finditer(t):
        found.append((f"{m.group(1).strip()} ({m.group(2).strip()})", m.start()))

    for m in RE_URL.finditer(t):
        found.append((m.group(0).strip(), m.start()))

    for m in RE_CROSSREF.finditer(t):
        found.append((m.group(0).strip(), m.start()))

    for sym in FOOTNOTE_MARKERS:
        idx = t.find(sym)
        if idx != -1:
            if idx == 0 or t[idx - 1].isalnum():
                continue
            found.append((sym, idx))

    found.sort(key=lambda x: x[1])
    return found


def decide_citation_status(
    paragraph_text: str,
    sentences: List[str],
    claim_sentence_index: int,
) -> CitationDecision:
    """
    Conservative policy:
    - cited: marker in the same sentence as the claim
    - ambiguous: marker in prev or next sentence, or elsewhere in paragraph
    - not_cited: no markers anywhere in paragraph

    Always returns marker text, location text, and context if markers exist.
    """
    if not sentences or claim_sentence_index < 0 or claim_sentence_index >= len(sentences):
        markers = _find_markers_in_text(paragraph_text or "")
        if not markers:
            return CitationDecision("not_cited", "", "", "")
        marker_texts = _dedup_keep_order([m[0] for m in markers])
        contexts = [_context_window(paragraph_text, m[1]) for m in markers[:3]]
        return CitationDecision(
            "ambiguous",
            " | ".join(marker_texts),
            "same_paragraph_other",
            " | ".join([c for c in contexts if c]),
        )

    locations: List[str] = []
    marker_texts: List[str] = []
    contexts: List[str] = []

    def harvest(sentence_text: str, location_label: str):
        ms = _find_markers_in_text(sentence_text)
        if not ms:
            return
        locations.append(location_label)
        for marker, start in ms:
            marker_texts.append(marker)
            contexts.append(_context_window(sentence_text, start))

    claim_sent = sentences[claim_sentence_index]
    harvest(claim_sent, "same_sentence")

    if marker_texts:
        marker_texts = _dedup_keep_order(marker_texts)
        locations = _dedup_keep_order(locations)
        contexts = [c for c in contexts if c][:3]
        return CitationDecision(
            "cited",
            " | ".join(marker_texts),
            " | ".join(locations),
            " | ".join(contexts),
        )

    if claim_sentence_index - 1 >= 0:
        harvest(sentences[claim_sentence_index - 1], "prev_sentence")
    if claim_sentence_index + 1 < len(sentences):
        harvest(sentences[claim_sentence_index + 1], "next_sentence")

    if marker_texts:
        marker_texts = _dedup_keep_order(marker_texts)
        locations = _dedup_keep_order(locations)
        contexts = [c for c in contexts if c][:3]
        return CitationDecision(
            "ambiguous",
            " | ".join(marker_texts),
            " | ".join(locations),
            " | ".join(contexts),
        )

    # Elsewhere in paragraph
    all_markers = _find_markers_in_text(paragraph_text or "")
    if not all_markers:
        return CitationDecision("not_cited", "", "", "")

    marker_texts = _dedup_keep_order([m[0] for m in all_markers])
    contexts = [_context_window(paragraph_text, m[1]) for m in all_markers[:3]]
    return CitationDecision(
        "ambiguous",
        " | ".join(marker_texts),
        "same_paragraph_other",
        " | ".join([c for c in contexts if c]),
    )
