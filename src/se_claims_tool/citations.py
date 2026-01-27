from __future__ import annotations
import re
from typing import List

# [1], [1,2], [1-3], [12–15]
RE_NUMERIC = re.compile(r"\[(\s*\d+(\s*[-–]\s*\d+)?(\s*,\s*\d+(\s*[-–]\s*\d+)?)*)\s*\]")

# (Smith, 2019), (Smith & Jones, 2020), (Smith et al., 2021)
RE_AUTHOR_YEAR = re.compile(
    r"\(([^()]{2,80}?\b(?:19|20)\d{2}[a-z]?)\)"
)

# Smith (2019)
RE_INLINE_AUTHOR_YEAR = re.compile(
    r"\b([A-Z][A-Za-z\-]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z\-]+|\s+et\s+al\.)?)\s*\(((?:19|20)\d{2}[a-z]?)\)"
)

def extract_citations(text: str) -> List[str]:
    t = text or ""
    cites = []

    for m in RE_NUMERIC.finditer(t):
        cites.append("[" + m.group(1).strip() + "]")

    for m in RE_AUTHOR_YEAR.finditer(t):
        # only keep things that really look like author-year
        if re.search(r"(?:19|20)\d{2}", m.group(1)):
            cites.append("(" + m.group(1).strip() + ")")

    for m in RE_INLINE_AUTHOR_YEAR.finditer(t):
        cites.append(f"{m.group(1).strip()} ({m.group(2).strip()})")

    # de-dup while preserving order
    out = []
    seen = set()
    for c in cites:
        if c not in seen:
            out.append(c)
            seen.add(c)
    return out
