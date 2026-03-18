from __future__ import annotations

import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    from se_claims_tool.batch_pipeline import run_corpus
    from se_claims_tool.config import RunConfig
    from se_claims_tool.llm.azure_llm_filter import AzureLLMFilter
    READY = True
except Exception as e:
    READY = False
    st.error(f"Import error: {e}")


st.set_page_config(
    page_title="SE Folklore Claims Extraction",
    page_icon="📖",
    layout="wide",
)

st.title("SE Folklore Claims Extraction Tool")
st.caption(
    "Master's Thesis: *Claims Validity of Software Engineering Folklore* · "
    "Blekinge Institute of Technology · PA2534 VT26"
)
st.divider()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Azure OpenAI Configuration")

    api_key = st.text_input(
        "API Key",
        value=os.environ.get("AZURE_OPENAI_API_KEY", ""),
        type="password",
    )
    endpoint = st.text_input(
        "Endpoint",
        value=os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
    )
    deployment = st.text_input(
        "Deployment",
        value=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
    )
    api_version = st.text_input(
        "API Version",
        value=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01"),
    )
    use_llm = st.toggle("Enable LLM Filter", value=bool(api_key))

    st.divider()
    st.subheader("Pipeline")
    st.markdown("""
**Stage 1 — NLP Pre-filter**  
Regex patterns detect claim candidates across six types:
NORMATIVE, CAUSAL, COMPARATIVE, QUANTITATIVE, GENERALIZATION, AUTHOR_PERSPECTIVE.

**Stage 2 — LLM Filter**  
Azure OpenAI (gpt-4o) verifies each candidate with surrounding context (prev + sentence + next).

**Claim definition:**  
*A declarative sentence asserting a generalizable proposition about SE practice, behavior, process, tools, or outcomes — falsifiable against empirical evidence.*
    """)

    st.divider()
    if st.button("Test Azure Connection"):
        if not api_key:
            st.error("No API key provided.")
        else:
            try:
                from openai import AzureOpenAI
                client = AzureOpenAI(
                    azure_endpoint=endpoint.rstrip("/"),
                    api_key=api_key,
                    api_version=api_version,
                )
                resp = client.chat.completions.create(
                    model=deployment,
                    messages=[{"role": "user", "content": "Reply: OK"}],
                    max_tokens=5,
                    temperature=0.0,
                )
                st.success(f"Connected: {resp.choices[0].message.content}")
            except Exception as e:
                st.error(f"Failed: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────
st.header("1 · Upload Books")
st.info(
    "Accepted: .epub · .azw3 · .pdf (including watermarked PDFs from Taylor & Francis). "
    "Files are processed in memory only — never stored on disk.",
    icon="🔒",
)

uploaded = st.file_uploader(
    "Upload practitioner SE books",
    type=["epub", "azw3", "pdf"],
    accept_multiple_files=True,
)

if uploaded:
    st.success(f"{len(uploaded)} file(s) ready: {', '.join(f.name for f in uploaded)}")

st.divider()
st.header("2 · Run Extraction")

col1, col2 = st.columns([3, 1])
with col1:
    run_btn = st.button(
        "Extract Claims",
        disabled=not uploaded or not READY,
        type="primary",
        use_container_width=True,
    )
with col2:
    st.markdown(f"**LLM:** {'✅ enabled' if use_llm else '⚠️ disabled (NLP only)'}")

if run_btn and uploaded:
    llm_filter = None
    if use_llm:
        if not api_key:
            st.warning("LLM enabled but no API key — running NLP only.")
        else:
            try:
                llm_filter = AzureLLMFilter(
                    endpoint=endpoint,
                    api_key=api_key,
                    api_version=api_version,
                    deployment=deployment,
                )
            except Exception as e:
                st.error(f"LLM filter init failed: {e}")
                st.stop()

    tmp_in  = tempfile.mkdtemp(prefix="se_books_")
    tmp_out = tempfile.mkdtemp(prefix="se_out_")

    try:
        for uf in uploaded:
            (Path(tmp_in) / uf.name).write_bytes(uf.read())

        import logging, io
        log_buf = io.StringIO()
        handler = logging.StreamHandler(log_buf)
        logger  = logging.getLogger("se_claims")
        logger.setLevel(logging.INFO)
        logger.handlers = [handler]

        with st.spinner("Running pipeline…"):
            summary = run_corpus(
                inputs=tmp_in,
                outdir=tmp_out,
                cfg=RunConfig(),
                llm_filter=llm_filter,
                logger=logger,
            )

        st.divider()
        st.header("3 · Results")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Books processed", summary.get("books_succeeded", 0))
        c2.metric("Total claims",    summary.get("total_claims", 0))
        c3.metric("LLM used",        "Yes" if summary.get("llm_used") else "No")
        c4.metric("Errors",          summary.get("books_failed", 0))

        csv_path = Path(tmp_out) / "all_claims.csv"
        if csv_path.exists():
            df = pd.read_csv(csv_path)

            st.subheader(f"Claims ({len(df)})")

            col_a, col_b = st.columns(2)
            with col_a:
                type_opts = sorted(df["llm_claim_type"].dropna().unique().tolist()) if "llm_claim_type" in df.columns else []
                type_sel  = st.multiselect("Filter by claim type", type_opts)
            with col_b:
                book_opts = sorted(df["book_title"].dropna().unique().tolist()) if "book_title" in df.columns else []
                book_sel  = st.multiselect("Filter by book", book_opts)

            view = df.copy()
            if type_sel:
                view = view[view["llm_claim_type"].isin(type_sel)]
            if book_sel:
                view = view[view["book_title"].isin(book_sel)]

            show = [c for c in [
                "claim_id", "book_title", "chapter_title",
                "claim_text", "prev_sentence", "next_sentence",
                "llm_claim_type", "llm_confidence", "llm_reason",
                "citation_status",
            ] if c in view.columns]

            st.dataframe(view[show], use_container_width=True, height=420)

            st.download_button(
                "Download claims CSV",
                data=view.to_csv(index=False).encode("utf-8"),
                file_name=f"claims_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
            )

        sum_path = Path(tmp_out) / "per_book_summary.csv"
        if sum_path.exists():
            st.subheader("Per-book summary")
            st.dataframe(pd.read_csv(sum_path), use_container_width=True)

        with st.expander("Pipeline logs"):
            st.code(log_buf.getvalue(), language="text")

    except Exception as e:
        st.error(f"Pipeline failed: {e}")
        import traceback
        st.code(traceback.format_exc())
    finally:
        shutil.rmtree(tmp_in,  ignore_errors=True)
        shutil.rmtree(tmp_out, ignore_errors=True)