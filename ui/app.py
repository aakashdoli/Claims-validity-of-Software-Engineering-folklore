# ui/app.py
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import streamlit as st

from se_claims_tool.config import RunConfig
from se_claims_tool.logging_utils import setup_logger
from se_claims_tool.batch_pipeline import run_corpus

# Offline-first (no API)
from se_claims_tool.llm.claim_detector import RuleBasedClaimDetector, AzureClaimDetector
from se_claims_tool.llm.azure_client import AzureChatClient


st.set_page_config(page_title="SE Folklore Claims Extractor", layout="wide")

st.title("Claims Validity of Software Engineering Folklore")
st.caption(
    "Upload EPUB/PDF books (or one ZIP). Extract causal claims and download CSV/JSONL results. "
    "Zero-hallucination: claims are always verbatim from the source."
)

logger = setup_logger("INFO")


# -------------------------
# Sidebar settings
# -------------------------
with st.sidebar:
    st.header("Run settings")

    use_offline = st.checkbox("Offline mode (no Azure, recommended for now)", value=True)

    max_calls = st.number_input("Max LLM calls (cost control)", min_value=0, value=0, step=100)
    max_calls = None if max_calls == 0 else int(max_calls)

    st.markdown("---")
    st.subheader("Candidate filter")
    default_cfg = RunConfig()
    cues = st.text_area(
        "Cue phrases (one per line)",
        value="\n".join(default_cfg.cue_phrases),
        height=180
    )

    st.markdown("---")
    st.subheader("Azure settings (only if Offline mode is OFF)")
    st.text_input(
        "AZURE_OPENAI_ENDPOINT",
        key="AZURE_OPENAI_ENDPOINT",
        value=os.environ.get("AZURE_OPENAI_ENDPOINT", "https://bth-ai.azure-api.net/student"),
        help="Use base endpoint WITHOUT '/openai' suffix. Example: https://bth-ai.azure-api.net/student"
    )
    st.text_input(
        "AZURE_OPENAI_API_KEY",
        key="AZURE_OPENAI_API_KEY",
        value=os.environ.get("AZURE_OPENAI_API_KEY", ""),
        type="password"
    )
    st.text_input(
        "AZURE_OPENAI_API_VERSION",
        key="AZURE_OPENAI_API_VERSION",
        value=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
    )
    st.text_input(
        "AZURE_OPENAI_DEPLOYMENT",
        key="AZURE_OPENAI_DEPLOYMENT",
        value=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
    )


# -------------------------
# Upload UI
# -------------------------
st.markdown("### Upload books")
uploaded_files = st.file_uploader(
    "Upload multiple EPUB/PDF files OR upload a single ZIP containing them.",
    type=["epub", "pdf", "zip"],
    accept_multiple_files=True
)

run_btn = st.button("Run extraction", type="primary", disabled=(not uploaded_files))


def _save_uploads_to_temp(uploaded) -> Path:
    tmpdir = Path(tempfile.mkdtemp(prefix="se_claims_upload_"))
    for uf in uploaded:
        out = tmpdir / uf.name
        out.write_bytes(uf.getbuffer())
    return tmpdir


def _find_single_zip(tmpdir: Path) -> Path | None:
    """If the upload is exactly one zip file (and nothing else), return it."""
    items = list(tmpdir.iterdir())
    if len(items) == 1 and items[0].suffix.lower() == ".zip":
        return items[0]
    return None


# -------------------------
# Run extraction
# -------------------------
if run_btn:
    # Build config
    cue_list = [c.strip() for c in cues.splitlines() if c.strip()]
    cfg = RunConfig(max_llm_calls=max_calls, store_only_snippets=True)
    cfg.cue_phrases = cue_list

    # Pick detector
    if use_offline:
        detector = RuleBasedClaimDetector()
        st.info("Using OFFLINE rule-based detector (no API calls).")
    else:
        # Apply env vars from sidebar inputs
        os.environ["AZURE_OPENAI_ENDPOINT"] = st.session_state["AZURE_OPENAI_ENDPOINT"].strip()
        os.environ["AZURE_OPENAI_API_KEY"] = st.session_state["AZURE_OPENAI_API_KEY"].strip()
        os.environ["AZURE_OPENAI_API_VERSION"] = st.session_state["AZURE_OPENAI_API_VERSION"].strip()
        os.environ["AZURE_OPENAI_DEPLOYMENT"] = st.session_state["AZURE_OPENAI_DEPLOYMENT"].strip()

        try:
            client = AzureChatClient()
            detector = AzureClaimDetector(client)
            st.success("Azure client configured.")
        except Exception as e:
            st.error(f"Azure configuration error: {e}")
            st.stop()

    with st.spinner("Saving uploads..."):
        tmpdir = _save_uploads_to_temp(uploaded_files)

    zip_input = _find_single_zip(tmpdir)
    inputs_path = str(zip_input) if zip_input else str(tmpdir)

    outdir = Path(tempfile.mkdtemp(prefix="se_claims_out_"))

    with st.spinner("Running extraction on all uploaded books..."):
        summary = run_corpus(
            inputs=inputs_path,
            outdir=str(outdir),
            cfg=cfg,
            detector=detector,
            logger=logger,
        )

    st.success("Done!")

    # Summary cards
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Books found", summary.get("books_count", 0))
    c2.metric("Succeeded", summary.get("books_succeeded", 0))
    c3.metric("Failed", summary.get("books_failed", 0))
    c4.metric("Total claims", summary.get("total_claims", 0))

    # Downloads
    all_csv = outdir / "all_claims.csv"
    all_jsonl = outdir / "all_claims.jsonl"
    results_zip = outdir / "results.zip"

    st.markdown("### Download outputs")
    colA, colB, colC = st.columns(3)

    if all_csv.exists():
        colA.download_button(
            "Download all_claims.csv",
            data=all_csv.read_bytes(),
            file_name="all_claims.csv",
            mime="text/csv"
        )
    else:
        colA.info("all_claims.csv not found (no claims extracted).")

    if all_jsonl.exists():
        colB.download_button(
            "Download all_claims.jsonl",
            data=all_jsonl.read_bytes(),
            file_name="all_claims.jsonl",
            mime="application/jsonl"
        )
    else:
        colB.info("all_claims.jsonl not found.")

    if results_zip.exists():
        colC.download_button(
            "Download results.zip (everything)",
            data=results_zip.read_bytes(),
            file_name="results.zip",
            mime="application/zip"
        )
    else:
        colC.info("results.zip not found.")

    # Errors
    errs = summary.get("errors", [])
    if errs:
        st.warning("Some files failed. See details below.")
        st.json(errs)
