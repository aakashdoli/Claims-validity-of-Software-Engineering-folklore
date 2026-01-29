from __future__ import annotations

import hashlib
import logging
import sys
from pathlib import Path
from typing import List, Optional

import pandas as pd
import streamlit as st

# Ensure project package imports work when running: streamlit run ui/app.py
REPO_ROOT = Path(__file__).resolve().parents[1]  # .../se-folklore-claims
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from se_claims_tool.batch_pipeline import run_corpus
from se_claims_tool.config import RunConfig
from se_claims_tool.llm.claim_detector import RuleBasedClaimDetector

# Paths
UPLOAD_DIR = REPO_ROOT / "books_upload"
DEFAULT_OUTDIR = REPO_ROOT / "out_ui"


class _StreamlitLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines: List[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


def _setup_logger(level: str = "INFO") -> tuple[logging.Logger, _StreamlitLogHandler]:
    logger = logging.getLogger("se_claims_tool_ui")
    logger.setLevel(getattr(logging, (level or "INFO").upper(), logging.INFO))
    logger.handlers.clear()
    logger.propagate = False

    handler = _StreamlitLogHandler()
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    return logger, handler


def _sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_save_upload(uploaded_file, target_dir: Path) -> tuple[Path, bool]:
    """
    Saves the uploaded file deterministically.

    Dedup rule:
    - If another file in target_dir has the same content hash, do not save again.
      Return the existing path and is_duplicate=True.

    If not duplicate:
    - Save using original filename.
    - If name collision exists, append _1, _2, ... deterministically.
    """
    target_dir.mkdir(parents=True, exist_ok=True)

    data = uploaded_file.getbuffer().tobytes()
    incoming_hash = _sha256_bytes(data)

    for existing in target_dir.iterdir():
        if not existing.is_file():
            continue
        if existing.suffix.lower() not in [".epub", ".azw3", ".zip"]:
            continue
        try:
            if _sha256_file(existing) == incoming_hash:
                return existing, True
        except Exception:
            continue

    target = target_dir / uploaded_file.name
    if target.exists():
        stem = target.stem
        suffix = target.suffix
        i = 1
        while True:
            candidate = target_dir / f"{stem}_{i}{suffix}"
            if not candidate.exists():
                target = candidate
                break
            i += 1

    with open(target, "wb") as f:
        f.write(data)

    return target, False


def _list_books(folder: Path) -> List[Path]:
    if not folder.exists():
        return []
    files: List[Path] = []
    for ext in ["*.epub", "*.EPUB", "*.azw3", "*.AZW3", "*.zip", "*.ZIP"]:
        files.extend(folder.rglob(ext))
    return sorted(files)


def _read_bytes(path: Path) -> Optional[bytes]:
    if path.exists() and path.is_file():
        return path.read_bytes()
    return None


st.set_page_config(page_title="SE Folklore Claim Extraction (RQ1)", layout="wide")
st.title("SE Folklore Claim Extraction Tool (RQ1)")

st.write(
    "Upload EPUB/AZW3 (or a ZIP containing them). The tool extracts one claim per row, "
    "adds traceability, and assigns conservative citation_status (cited / ambiguous / not_cited)."
)

UPLOAD_DIR.mkdir(exist_ok=True)
DEFAULT_OUTDIR.mkdir(exist_ok=True)

with st.sidebar:
    st.header("Settings")

    log_level = st.selectbox("Log level", ["INFO", "DEBUG", "WARNING", "ERROR"], index=0)

    max_calls = st.number_input(
        "Max detector calls (optional cap)",
        min_value=0,
        value=0,
        step=100,
        help="0 means no cap",
    )

    outdir_name = st.text_input("Output folder name", value="out_ui")
    outdir = REPO_ROOT / outdir_name

    st.caption("AZW3 requires calibre ebook-convert installed locally.")
    st.caption("No online scraping. Only processes files you upload.")

st.header("1) Upload books")
uploaded = st.file_uploader(
    "Choose EPUB/AZW3 files (or ZIP)",
    type=["epub", "azw3", "zip"],
    accept_multiple_files=True,
)

if uploaded:
    saved_paths = []
    dup_count = 0
    for f in uploaded:
        saved_path, is_dup = _safe_save_upload(f, UPLOAD_DIR)
        saved_paths.append(saved_path)
        if is_dup:
            dup_count += 1

    st.success(f"Processed {len(uploaded)} file(s). Saved new: {len(uploaded) - dup_count}. Duplicates skipped: {dup_count}.")
    if saved_paths:
        st.caption("Saved to: books_upload/")

books = _list_books(UPLOAD_DIR)

col1, col2 = st.columns([2, 1])
with col1:
    st.subheader("Files in upload folder")
    if books:
        df_books = pd.DataFrame(
            [
                {
                    "filename": p.name,
                    "stem": p.stem,
                    "ext": p.suffix.lower(),
                    "size_kb": round(p.stat().st_size / 1024, 1),
                }
                for p in books
            ]
        )
        st.dataframe(df_books, use_container_width=True, hide_index=True)
    else:
        st.info("No EPUB/AZW3/ZIP files found yet in books_upload/.")

with col2:
    st.subheader("Manage uploads")
    if st.button("Clear uploaded files", type="secondary", disabled=not bool(books)):
        for p in books:
            try:
                p.unlink()
            except Exception:
                pass
        st.rerun()

st.header("2) Run extraction")

available_stems = [p.stem for p in books if p.suffix.lower() != ".zip"]
pilot = st.multiselect(
    "Pilot books (select 2, or leave empty to run all)",
    options=available_stems,
    default=available_stems[:2] if len(available_stems) >= 2 else [],
)

run_btn = st.button("Run extraction", type="primary", disabled=not bool(books))

if run_btn:
    logger, handler = _setup_logger(log_level)

    cfg = RunConfig(max_llm_calls=None if max_calls == 0 else int(max_calls))
    detector = RuleBasedClaimDetector()

    outdir.mkdir(parents=True, exist_ok=True)

    with st.spinner("Running extraction..."):
        try:
            summary = run_corpus(
                inputs=str(UPLOAD_DIR),
                outdir=str(outdir),
                cfg=cfg,
                detector=detector,
                logger=logger,
                pilot_books=pilot if pilot else None,
            )
            st.success("Extraction completed.")
        except Exception as e:
            st.error(f"Run failed: {e}")
            summary = None

    st.subheader("Logs")
    st.code("\n".join(handler.lines[-400:]) if handler.lines else "No logs captured.")

    if summary:
        st.subheader("Run summary")
        st.json(summary)

        combined_csv = outdir / "all_claims.csv"
        per_book_csv = outdir / "per_book_summary.csv"
        results_zip = outdir / "results.zip"

        st.subheader("Downloads")
        dcol1, dcol2, dcol3 = st.columns(3)

        with dcol1:
            st.write("Combined claims CSV")
            data = _read_bytes(combined_csv)
            if data:
                st.download_button("Download all_claims.csv", data=data, file_name="all_claims.csv", mime="text/csv")
            else:
                st.info("Not found.")

        with dcol2:
            st.write("Per-book summary CSV")
            data = _read_bytes(per_book_csv)
            if data:
                st.download_button(
                    "Download per_book_summary.csv",
                    data=data,
                    file_name="per_book_summary.csv",
                    mime="text/csv",
                )
            else:
                st.info("Not found.")

        with dcol3:
            st.write("Zipped results")
            data = _read_bytes(results_zip)
            if data:
                st.download_button("Download results.zip", data=data, file_name="results.zip", mime="application/zip")
            else:
                st.info("Not found.")

        st.subheader("Preview (first 50 rows)")
        if combined_csv.exists():
            try:
                df = pd.read_csv(combined_csv)
                st.dataframe(df.head(50), use_container_width=True)
            except Exception as e:
                st.warning(f"Could not preview CSV: {e}")

st.divider()
st.caption("Run command: streamlit run ui/app.py")
