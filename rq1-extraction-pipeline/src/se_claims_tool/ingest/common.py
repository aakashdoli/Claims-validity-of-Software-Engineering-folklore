from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Iterable

def compute_book_id(path: str) -> str:
    p = Path(path)
    data = p.read_bytes()
    return hashlib.sha1(data).hexdigest()

def stable_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()

def normalize_whitespace(s: str) -> str:
    return " ".join((s or "").split())
