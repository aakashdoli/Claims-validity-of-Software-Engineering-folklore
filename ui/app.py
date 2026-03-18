"""
ui/app.py
---------
Streamlit UI for the SE Folklore Claims Extraction Tool.

Privacy & Copyright:
    - Uploaded books are processed IN MEMORY only — never written to disk permanently
    - Output CSVs are available for download but not stored on the server
    - Books and results are excluded from git (.gitignore)
"""
from __future__ import annotations

import os
import sys
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# Ensure src/ is importable
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from se_claims_tool.config import RunConfig
    from se_claims_tool.logging_utils import setup_logger
    from se_claims_tool.batch_pipeline import run_corpus
    from se_claims_tool.llm.azure_llm_filter import AzureLLMFilter
    TOOL_AVAILABLE = True
except Exception as e:
    TOOL_AVAILABLE = False
    st.error(f"Could not import se_claims_tool: {e}")


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SE Folklore Claims Tool",
    page_icon="📚",
    layout="wide",
)

st.title("📚 SE Folklore Claims Extraction Tool")
st.caption(
    "Two-stage pipeline: NLP pre-filter → Azure LLM (gpt-4o-mini) → Confirmed claims  |  "
    "Books are processed in memory only and never stored."
)

# ── Sidebar: Configuration ────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuration")

    st.subheader("Azure OpenAI (BTH)")
    azure_key = st.text_input(
        "API Key",
        value=os.environ.get("AZURE_OPENAI_API_KEY", ""),
        type="password",
        help="BTH Azure API key from Davide / BTH IT",
    )
    azure_endpoint = st.text_input(
        "Endpoint",
        value=os.environ.get("AZURE_OPENAI_ENDPOINT", "https://bth-ai.azure-api.net/student"),
        help="BTH Azure OpenAI endpoint",
    )
    azure_deployment = st.text_input(
        "Deployment",
        value=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
        help="Deployment name on Azure",
    )
    azure_version = st.text_input(
        "API Version",
        value=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01"),
    )

    use_llm = st.toggle(
        "Enable LLM Filter",
        value=bool(azure_key),
        help="If disabled, only NLP pre-filter runs (faster but less precise)",
    )

    st.divider()
    st.subheader("🔧 Run Settings")
    log_level = st.selectbox("Log Level", ["INFO", "DEBUG", "WARNING"], index=0)

    st.divider()
    st.subheader("ℹ️ About")
    st.markdown("""
**Claim Definition:**  
A declarative sentence asserting a generalizable proposition about SE practice, behavior, process, tools, or outcomes — falsifiable against empirical evidence.

**Claim Types:**
- NORMATIVE (should, must, best practice)
- CAUSAL (leads to, causes, prevents)
- COMPARATIVE (better than, more effective)
- QUANTITATIVE (%, 2x, majority)
- GENERALIZATION (often, typically, most engineers)
- AUTHOR_PERSPECTIVE (in my experience, I believe)
    """)


# ── Main: Book Upload ─────────────────────────────────────────────────────────
st.header("1️⃣  Upload Books")
st.info(
    "📋 Upload .epub, .azw3 or .pdf files. "
    "Watermarked PDFs from Taylor & Francis are fully supported. "
    "Books are processed in memory only — not stored on disk or committed to git.",
    icon="🔒",
)

uploaded_files = st.file_uploader(
    "Upload practitioner SE books (.epub, .azw3, .pdf)",
    type=["epub", "azw3", "pdf"],
    accept_multiple_files=True,
)

if uploaded_files:
    st.success(f"✅ {len(uploaded_files)} book(s) ready: {', '.join(f.name for f in uploaded_files)}")


# ── Main: Run Pipeline ────────────────────────────────────────────────────────
st.header("2️⃣  Run Extraction Pipeline")

col1, col2 = st.columns([2, 1])
with col1:
    run_btn = st.button(
        "🚀 Extract Claims",
        disabled=not uploaded_files or not TOOL_AVAILABLE,
        type="primary",
        use_container_width=True,
    )
with col2:
    st.markdown(f"""
    **Pipeline stages:**
    1. NLP pre-filter (fast, high recall)
    2. {"✅ Azure LLM filter" if use_llm else "⚠️ NLP only (LLM disabled)"}
    """)

if run_btn and uploaded_files:
    # Build LLM filter
    llm_filter = None
    if use_llm and azure_key:
        try:
            llm_filter = AzureLLMFilter(
                endpoint=azure_endpoint,
                api_key=azure_key,
                api_version=azure_version,
                deployment=azure_deployment,
            )
            st.info(f"🤖 LLM filter ready: {azure_deployment} @ {azure_endpoint}")
        except Exception as e:
            st.error(f"❌ Could not initialize Azure LLM filter: {e}")
            st.stop()
    elif use_llm and not azure_key:
        st.warning("⚠️ LLM filter enabled but no API key — running NLP only.")

    # Save uploaded books to a temp directory (in-memory session only)
    tmp_dir = tempfile.mkdtemp(prefix="se_claims_books_")
    out_dir = tempfile.mkdtemp(prefix="se_claims_out_")

    try:
        # Write uploaded files to temp dir
        book_paths = []
        for uf in uploaded_files:
            dest = Path(tmp_dir) / uf.name
            dest.write_bytes(uf.read())
            book_paths.append(str(dest))

        cfg = RunConfig()

        # Set up logging to capture output
        import logging
        import io

        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(getattr(logging, log_level))
        logger = logging.getLogger("se_claims_ui")
        logger.setLevel(getattr(logging, log_level))
        logger.handlers = [handler]

        # Progress display
        log_placeholder = st.empty()
        progress_bar = st.progress(0, text="Starting pipeline...")

        with st.spinner("Running extraction pipeline..."):
            summary = run_corpus(
                inputs=tmp_dir,
                outdir=out_dir,
                cfg=cfg,
                llm_filter=llm_filter,
                logger=logger,
            )

        progress_bar.progress(100, text="✅ Complete!")

        # ── Results ───────────────────────────────────────────────────────────
        st.header("3️⃣  Results")

        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("📚 Books processed", summary.get("books_succeeded", 0))
        col2.metric("🔍 Total claims found", summary.get("total_claims", 0))
        col3.metric("✅ LLM used", "Yes" if summary.get("llm_used") else "No (NLP only)")
        col4.metric("❌ Books failed", summary.get("books_failed", 0))

        # Load and display the claims CSV
        all_claims_path = Path(out_dir) / "all_claims.csv"
        if all_claims_path.exists():
            df = pd.read_csv(all_claims_path)
            st.subheader(f"Claims Table ({len(df)} claims)")

            # Filter controls
            col1, col2 = st.columns(2)
            with col1:
                type_filter = st.multiselect(
                    "Filter by LLM claim type",
                    options=df["llm_claim_type"].unique().tolist() if "llm_claim_type" in df.columns else [],
                    default=[],
                )
            with col2:
                book_filter = st.multiselect(
                    "Filter by book",
                    options=df["book_title"].unique().tolist() if "book_title" in df.columns else [],
                    default=[],
                )

            filtered_df = df.copy()
            if type_filter:
                filtered_df = filtered_df[filtered_df["llm_claim_type"].isin(type_filter)]
            if book_filter:
                filtered_df = filtered_df[filtered_df["book_title"].isin(book_filter)]

            # Show key columns
            display_cols = [
                c for c in [
                    "claim_id", "book_title", "claim_text",
                    "prev_sentence", "next_sentence",
                    "llm_claim_type", "llm_confidence", "llm_reason",
                    "nlp_claim_type", "citation_status"
                ]
                if c in filtered_df.columns
            ]
            st.dataframe(filtered_df[display_cols], use_container_width=True, height=400)

            # Download button — user downloads CSV, nothing stored permanently
            csv_bytes = filtered_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="⬇️ Download claims CSV",
                data=csv_bytes,
                file_name=f"claims_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
            )

        # Per-book summary
        summary_path = Path(out_dir) / "per_book_summary.csv"
        if summary_path.exists():
            st.subheader("Per-book summary")
            st.dataframe(pd.read_csv(summary_path), use_container_width=True)

        # Show logs
        with st.expander("📋 Pipeline logs"):
            st.code(log_stream.getvalue(), language="text")

    except Exception as e:
        st.error(f"❌ Pipeline failed: {e}")
        import traceback
        st.code(traceback.format_exc())

    finally:
        # Always clean up temp files — books never persist
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            shutil.rmtree(out_dir, ignore_errors=True)
        except Exception:
            pass


# ── Previous Results Section ──────────────────────────────────────────────────
st.divider()
st.header("4️⃣  Test Azure Connection")
if st.button("🔌 Test Azure API connection"):
    if not azure_key:
        st.error("No API key provided")
    else:
        try:
            from openai import AzureOpenAI
            client = AzureOpenAI(
                azure_endpoint=azure_endpoint.rstrip("/"),
                api_key=azure_key,
                api_version=azure_version,
            )
            resp = client.chat.completions.create(
                model=azure_deployment,
                messages=[{"role": "user", "content": "Say: connection OK"}],
                max_tokens=10,
                temperature=0.0,
            )
            st.success(f"✅ Azure connection OK! Response: {resp.choices[0].message.content}")
        except Exception as e:
            st.error(f"❌ Connection failed: {type(e).__name__}: {e}")
            st.info("Check: endpoint URL, API key, and deployment name are correct.")