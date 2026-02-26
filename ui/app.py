from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd
import streamlit as st

# Ensure src/ is importable when running from repo root
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Import your pipeline entrypoint
try:
    from se_claims_tool.config import RunConfig
    from se_claims_tool.logging_utils import setup_logger
    from se_claims_tool.batch_pipeline import run_corpus
    from se_claims_tool.llm.claim_detector import RuleBasedClaimDetector
except Exception as e:
    run_corpus = None
    RuleBasedClaimDetector = None
    RunConfig = None
    setup_logger = None
    st.warning(f"Could not import se_claims_tool modules. Import error: {e}")

try:
    from se_claims_tool.llm.gemini_filter import GeminiClaimFilter, list_available_models
except Exception as e:
    GeminiClaimFilter = None
    list_available_models = None

try:
    from se_claims_tool.llm.azure_filter import AzureClaimFilter
except Exception as e:
    AzureClaimFilter = None


def run_cmd(cmd: list[str], cwd: Optional[Path] = None) -> tuple[int, str]:
    """Run a shell command and return (returncode, combined_output)."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src") + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc.returncode, proc.stdout


def list_books(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    exts = {".epub", ".azw3", ".zip"}
    files = [p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in exts]
    return sorted(files)


def safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


st.set_page_config(page_title="SE Folklore Claims Tool", layout="wide")
st.title("SE Folklore Claims Tool")
st.caption(
    "Deterministic claim extraction, traceability, and manual validation workflow"
)


with st.sidebar:
    st.header("Paths")

    default_books_dir = REPO_ROOT / "books_upload"
    default_out_dir = REPO_ROOT / "out"

    books_dir = Path(st.text_input("Books folder", value=str(default_books_dir)))
    out_dir = Path(st.text_input("Output folder", value=str(default_out_dir)))

    safe_mkdir(out_dir)

    st.divider()
    st.header("Run settings")
    log_level = st.selectbox(
        "Log level", ["INFO", "DEBUG", "WARNING", "ERROR"], index=0
    )
    max_calls = st.number_input(
        "Max detector calls (optional)", min_value=0, value=0, step=1
    )
    max_calls_value = None if max_calls == 0 else int(max_calls)

    st.divider()
    st.header("Validation settings")
    sample_n = st.number_input("Sample size", min_value=1, value=50, step=1)
    sample_seed = st.number_input("Sample seed", min_value=0, value=42, step=1)


tabs = st.tabs(
    ["1) Extract", "2) Validate sample", "3) Score validation", "4) Browse outputs", "5) Gemini Filter"]
)


# -------------------------
# 1) Extract
# -------------------------
with tabs[0]:
    st.subheader("1) Extract claims from a book")

    uploaded_book = st.file_uploader(
        "Upload a book (.epub or .azw3)", type=["epub", "azw3"]
    )
    if uploaded_book is not None:
        safe_mkdir(books_dir)  # ensure folder exists before writing
        dest = books_dir / uploaded_book.name
        dest.write_bytes(uploaded_book.getvalue())
        st.success(f"Saved to: {dest}")

        # Remember uploaded file and rerun so it appears in the dropdown
        st.session_state["last_uploaded_book"] = dest.name
        st.rerun()

    books = list_books(books_dir)
    if not books:
        st.error(f"No .epub/.azw3 files found in: {books_dir}")
        st.stop()

    book_names = [p.name for p in books if p.suffix.lower() != ".zip"]
    book_map = {p.name: p for p in books}

    run_scope = st.radio(
        "What do you want to run?",
        [
            "Run one selected book",
            "Run multiple selected books",
            "Run all uploaded books",
        ],
        index=0,
    )

    selected_path = None
    selected_multi = []

    if run_scope == "Run one selected book":
        default_idx = 0
        last = st.session_state.get("last_uploaded_book")
        if last and last in book_names:
            default_idx = book_names.index(last)

        selected = st.selectbox(
            "Select a book file",
            book_names,
            index=default_idx,
            key="book_selectbox",
        )
        selected_path = books_dir / selected
        st.caption(f"DEBUG selected_path: {selected_path}")

    elif run_scope == "Run multiple selected books":
        stems = [p.stem for p in books if p.suffix.lower() != ".zip"]
        selected_multi = st.multiselect(
            "Select books (by stem)", options=stems, default=[]
        )

    run_mode = st.radio(
        "Run mode", ["Use Python API (recommended)", "Use CLI (subprocess)"], index=0
    )

    if st.button("Run extraction", type="primary"):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_out_dir = out_dir / f"run_{ts}"
        safe_mkdir(run_out_dir)

        st.info(f"Outputs will be written to: {run_out_dir}")

        if run_mode.startswith("Use Python API"):
            if run_corpus is None:
                st.error("Python API import failed. Switch to CLI mode or fix imports.")
            else:
                try:
                    logger, handler = setup_logger(
                        log_level
                    )  # capture logs into Streamlit
                    cfg = RunConfig(max_llm_calls=max_calls_value)
                    detector = RuleBasedClaimDetector()

                    if run_scope == "Run one selected book":
                        summary = run_corpus(
                            inputs=str(selected_path),
                            outdir=str(run_out_dir),
                            cfg=cfg,
                            detector=detector,
                            logger=logger,
                            pilot_books=None,
                        )
                    elif run_scope == "Run multiple selected books":
                        summary = run_corpus(
                            inputs=str(books_dir),
                            outdir=str(run_out_dir),
                            cfg=cfg,
                            detector=detector,
                            logger=logger,
                            pilot_books=selected_multi if selected_multi else None,
                        )
                    else:
                        summary = run_corpus(
                            inputs=str(books_dir),
                            outdir=str(run_out_dir),
                            cfg=cfg,
                            detector=detector,
                            logger=logger,
                            pilot_books=None,
                        )

                    st.success(f"Extraction completed. Outputs: {run_out_dir}")
                    st.subheader("Logs")
                    st.code(
                        "\n".join(handler.lines[-400:])
                        if handler.lines
                        else "No logs captured."
                    )

                    combined_csv = run_out_dir / "all_claims.csv"
                    if combined_csv.exists():
                        df = pd.read_csv(combined_csv)
                        st.subheader("Preview (first 50 rows)")
                        st.dataframe(df.head(50), width="stretch")
                    else:
                        st.error(
                            "Run finished but all_claims.csv was not created. Check logs above."
                        )

                    st.subheader("Run summary")
                    st.json(summary if summary else {"summary": "None returned"})

                except Exception as e:
                    st.error("Python API extraction failed.")
                    st.exception(e)
        else:
            if run_scope == "Run one selected book":
                target_inputs = str(selected_path)
                target_pilots = ""
            elif run_scope == "Run multiple selected books":
                target_inputs = str(books_dir)
                target_pilots = ",".join(selected_multi)
            else:
                target_inputs = str(books_dir)
                target_pilots = ""

            cmd = [
                sys.executable,
                "-m",
                "se_claims_tool",
                "extract-batch",
                "--inputs",
                target_inputs,
                "--outdir",
                str(run_out_dir),
                "--log-level",
                log_level,
            ]
            if max_calls_value is not None:
                cmd += ["--max-calls", str(max_calls_value)]
            if target_pilots.strip():
                cmd += ["--pilot-books", target_pilots.strip()]

            rc, out = run_cmd(cmd, cwd=REPO_ROOT)
            st.code(" ".join(cmd))
            st.text_area("Console output", out, height=260)
            if rc == 0:
                st.success("Extraction completed.")
            else:
                st.error(
                    f"Extraction failed (exit code {rc}). See console output above."
                )

        # Quick link to combined CSV if present
        combined = run_out_dir / "all_claims.csv"
        if combined.exists():
            st.success(f"Found: {combined.name}")
            df = pd.read_csv(combined)
            st.write("Preview of extracted claims:")
            st.dataframe(df.head(50), width="stretch")
        else:
            st.warning(
                "No all_claims.csv found in this run folder. Check console output and output files."
            )


# -------------------------
# 2) Validate sample
# -------------------------
with tabs[1]:
    st.subheader("2) Generate a deterministic validation sample")

    # Pick run folder and claims CSV
    run_folders = sorted([p for p in out_dir.glob("run_*") if p.is_dir()], reverse=True)
    if not run_folders:
        st.info("No run folders found. Run extraction first.")
    else:
        run_folder = st.selectbox(
            "Select a run folder", [str(p.name) for p in run_folders]
        )
        run_path = out_dir / run_folder

        # Prefer all_claims.csv, but allow user to choose
        csv_files = sorted(run_path.glob("*.csv"))
        default_csv = run_path / "all_claims.csv"
        choices = [default_csv] if default_csv.exists() else []
        choices += [p for p in csv_files if p.name != "all_claims.csv"]

        if not choices:
            st.error("No CSV files found in this run folder.")
        else:
            selected_csv = st.selectbox(
                "Select extracted claims CSV", [str(p.name) for p in choices]
            )
            input_csv = run_path / selected_csv

            st.write("Input CSV:", str(input_csv))

            out_sample_name = st.text_input(
                "Output sample filename",
                value=f"validation_sample_seed{int(sample_seed)}_n{int(sample_n)}.csv",
            )
            out_sample_path = run_path / out_sample_name

            if st.button("Generate validation sample", type="primary"):
                cmd = [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "validate_sample.py"),
                    "--input",
                    str(input_csv),
                    "--out",
                    str(out_sample_path),
                    "--n",
                    str(int(sample_n)),
                    "--seed",
                    str(int(sample_seed)),
                ]
                rc, out = run_cmd(cmd, cwd=REPO_ROOT)
                st.code(" ".join(cmd))
                st.text_area("Console output", out, height=200)
                if rc == 0 and out_sample_path.exists():
                    st.success(f"Sample created: {out_sample_path.name}")
                    df = pd.read_csv(out_sample_path)
                    st.dataframe(df.head(50), width="stretch")
                else:
                    st.error("Sample generation failed. See output above.")


# -------------------------
# 3) Score validation
# -------------------------
with tabs[2]:
    st.subheader("3) Score a filled validation sample and generate a report")

    run_folders = sorted([p for p in out_dir.glob("run_*") if p.is_dir()], reverse=True)
    if not run_folders:
        st.info("No run folders found. Run extraction first.")
    else:
        run_folder = st.selectbox(
            "Select a run folder for scoring",
            [str(p.name) for p in run_folders],
            key="score_run_folder",
        )
        run_path = out_dir / run_folder

        # Let user upload a filled CSV
        uploaded = st.file_uploader("Upload filled validation sample CSV", type=["csv"])
        if uploaded is not None:
            filled_path = run_path / "validation_sample_filled_uploaded.csv"
            filled_path.write_bytes(uploaded.getvalue())
            st.success(f"Uploaded to: {filled_path.name}")

            report_name = st.text_input("Report filename", value="validation_report.md")
            report_path = run_path / report_name

            if st.button("Score and generate report", type="primary"):
                cmd = [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "score_validation.py"),
                    "--input",
                    str(filled_path),
                    "--out_md",
                    str(report_path),
                ]
                rc, out = run_cmd(cmd, cwd=REPO_ROOT)
                st.code(" ".join(cmd))
                st.text_area("Console output", out, height=200)

                if rc == 0 and report_path.exists():
                    st.success(f"Report created: {report_path.name}")
                    st.markdown(report_path.read_text(encoding="utf-8"))
                else:
                    st.error("Scoring failed. See output above.")


# -------------------------
# 4) Browse outputs
# -------------------------
with tabs[3]:
    st.subheader("4) Browse outputs")

    run_folders = sorted([p for p in out_dir.glob("run_*") if p.is_dir()], reverse=True)
    if not run_folders:
        st.info("No run folders found yet.")
    else:
        run_folder = st.selectbox(
            "Select a run folder to browse",
            [str(p.name) for p in run_folders],
            key="browse_run_folder",
        )
        run_path = out_dir / run_folder
        st.write("Folder:", str(run_path))

        files = sorted([p for p in run_path.iterdir() if p.is_file()])
        if not files:
            st.info("No files in this run folder.")
        else:
            chosen = st.selectbox("Select a file", [p.name for p in files])
            fpath = run_path / chosen

            if fpath.suffix.lower() == ".csv":
                df = pd.read_csv(fpath)
                st.dataframe(df, width="stretch")
            elif fpath.suffix.lower() in {".md", ".txt", ".log"}:
                st.markdown(f"### {fpath.name}")
                st.text_area(
                    "Content",
                    fpath.read_text(encoding="utf-8", errors="ignore"),
                    height=450,
                )
            else:
                st.info("File preview not supported. You can download it below.")

            st.download_button(
                label="Download file",
                data=fpath.read_bytes(),
                file_name=fpath.name,
            )



# -------------------------
# 5) LLM Filter (Azure or Gemini)
# -------------------------
with tabs[4]:
    st.subheader("5) Filter claims with LLM (secondary filter)")
    st.caption(
        "Reads all_claims.csv and writes all_claims_filtered.csv. "
        "Each claim is classified as keep (genuine SE claim) or reject (false positive). "
        "The original CSV is never modified."
    )

    # ── Provider selector ────────────────────────────────────────────────────
    provider = st.radio(
        "Choose LLM provider",
        ["BTH Azure OpenAI (recommended)", "Google Gemini"],
        index=0,
        horizontal=True,
    )

    # ── Run folder + batch size ──────────────────────────────────────────────
    run_folders_llm = sorted(
        [p for p in out_dir.glob("run_*") if p.is_dir()], reverse=True
    )
    if not run_folders_llm:
        st.info("No run folders found. Run extraction first (Tab 1).")
    else:
        run_folder_llm  = st.selectbox(
            "Select a run folder to filter",
            [str(p.name) for p in run_folders_llm],
            key="llm_run_folder",
        )
        run_path_llm   = out_dir / run_folder_llm
        input_csv_llm  = run_path_llm / "all_claims.csv"
        output_csv_llm = run_path_llm / "all_claims_filtered.csv"

        st.write("Input:", str(input_csv_llm))
        st.write("Output:", str(output_csv_llm))

        batch_size_llm = st.number_input(
            "Batch size", min_value=1, max_value=50, value=20, step=1,
            help="Claims sent per API call. 20 is a safe default.",
            key="llm_batch_size",
        )

        st.divider()

        # ── Azure credentials ────────────────────────────────────────────────
        if provider.startswith("BTH Azure"):
            st.markdown("**Azure OpenAI credentials** — fill in values from BTH IT (4th floor J-building)")

            col1, col2 = st.columns(2)
            with col1:
                az_endpoint = st.text_input(
                    "Endpoint",
                    value=os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
                    placeholder="https://bth-ai.azure-api.net/student",
                )
                az_version = st.text_input(
                    "API Version",
                    value=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
                )
            with col2:
                az_key = st.text_input(
                    "API Key",
                    type="password",
                    value=os.environ.get("AZURE_OPENAI_API_KEY", ""),
                )
                az_deployment = st.text_input(
                    "Deployment name",
                    value=os.environ.get("AZURE_OPENAI_DEPLOYMENT", ""),
                    placeholder="e.g. gpt-4o or gpt-4.1",
                )

            st.caption(
                "Tip: Add these to a `.env` file in your project root so you don't "
                "have to paste them every time. See `.env.example` for the format."
            )

            ready = all([az_endpoint.strip(), az_key.strip(), az_version.strip(), az_deployment.strip()])
            if not ready:
                st.warning("Fill in all four Azure fields above to enable the filter.")

        # ── Gemini credentials ───────────────────────────────────────────────
        else:
            gemini_key_llm = st.text_input(
                "Gemini API key",
                type="password",
                value=os.environ.get("GEMINI_API_KEY", ""),
                help="Get a free key at https://aistudio.google.com/app/apikey",
                key="gemini_key_llm",
            )

            if gemini_key_llm.strip() and list_available_models:
                if st.button("Load available Gemini models"):
                    with st.spinner("Fetching model list..."):
                        try:
                            found = list_available_models(gemini_key_llm.strip())
                            st.session_state["gemini_models_llm"] = found
                            st.success(f"Found {len(found)} models.")
                        except Exception as e:
                            st.error(f"Failed: {e}")

            raw_models_llm = st.session_state.get("gemini_models_llm", [])
            if raw_models_llm:
                flash_first_llm = sorted(raw_models_llm, key=lambda m: (0 if "flash" in m else 1, m))
                gemini_model_llm = st.selectbox("Select model", flash_first_llm, key="gemini_model_llm")
            else:
                gemini_model_llm = None

            ready = bool(gemini_key_llm.strip() and gemini_model_llm)
            if not ready:
                st.warning("Enter API key and load models to enable the filter.")

        # ── Preview + Run ────────────────────────────────────────────────────
        if not input_csv_llm.exists():
            st.error(f"all_claims.csv not found in {run_folder_llm}. Run extraction first.")
        else:
            df_preview_llm = pd.read_csv(input_csv_llm)
            st.info(f"Found {len(df_preview_llm)} claims to filter.")
            st.dataframe(
                df_preview_llm[["claim_id", "claim_text", "trigger_rule"]].head(10)
            )

            if st.button("Run LLM filter", type="primary", disabled=not ready, key="run_llm_filter"):
                with st.spinner("Running LLM filter... this may take a minute."):
                    try:
                        logger_llm, handler_llm = setup_logger(log_level)

                        if provider.startswith("BTH Azure"):
                            if AzureClaimFilter is None:
                                st.error("AzureClaimFilter could not be imported.")
                                st.stop()
                            lf = AzureClaimFilter(
                                endpoint=az_endpoint.strip(),
                                api_key=az_key.strip(),
                                api_version=az_version.strip(),
                                deployment=az_deployment.strip(),
                                batch_size=int(batch_size_llm),
                            )
                        else:
                            if GeminiClaimFilter is None:
                                st.error("GeminiClaimFilter could not be imported.")
                                st.stop()
                            lf = GeminiClaimFilter(
                                api_key=gemini_key_llm.strip(),
                                model=gemini_model_llm,
                                batch_size=int(batch_size_llm),
                            )

                        summary_llm = lf.filter_csv(
                            input_csv=str(input_csv_llm),
                            output_csv=str(output_csv_llm),
                            logger=logger_llm,
                        )

                        model_info = summary_llm.get("deployment") or summary_llm.get("model_used", "")
                        st.success(
                            f"Done! ({model_info}) — "
                            f"Kept **{summary_llm['kept']}**, "
                            f"rejected **{summary_llm['rejected']}**, "
                            f"unverified {summary_llm['unverified']} "
                            f"out of {summary_llm['total']} claims."
                        )

                        st.subheader("Logs")
                        log_text = "\n".join(handler_llm.lines[-200:]) or "No logs."
                        if any("ERROR" in l for l in handler_llm.lines):
                            st.warning("Some API calls failed — see logs below.")
                        st.code(log_text)

                        df_out_llm = pd.read_csv(output_csv_llm)
                        st.subheader("Filtered results preview")
                        col_k, col_r = st.columns(2)
                        with col_k:
                            st.write(f"**Kept ({summary_llm['kept']})**")
                            st.dataframe(
                                df_out_llm[df_out_llm["llm_verdict"] == "keep"][
                                    ["claim_id", "claim_text", "trigger_rule", "llm_reason"]
                                ],
                                height=300,
                            )
                        with col_r:
                            st.write(f"**Rejected ({summary_llm['rejected']})**")
                            st.dataframe(
                                df_out_llm[df_out_llm["llm_verdict"] == "reject"][
                                    ["claim_id", "claim_text", "trigger_rule", "llm_reason"]
                                ],
                                height=300,
                            )
                        st.download_button(
                            label="Download all_claims_filtered.csv",
                            data=output_csv_llm.read_bytes(),
                            file_name="all_claims_filtered.csv",
                            mime="text/csv",
                            key="dl_filtered_llm",
                        )

                    except Exception as e:
                        st.error("LLM filter failed.")
                        st.exception(e)

        # ── Show previous results ────────────────────────────────────────────
        if output_csv_llm.exists():
            st.divider()
            st.subheader("Previous filtered results")
            df_prev = pd.read_csv(output_csv_llm)
            if "llm_verdict" in df_prev.columns:
                kept_n = (df_prev["llm_verdict"] == "keep").sum()
                rej_n  = (df_prev["llm_verdict"] == "reject").sum()
                st.info(f"Existing file: {kept_n} kept, {rej_n} rejected.")
                st.dataframe(
                    df_prev[["claim_id", "claim_text", "trigger_rule", "llm_verdict", "llm_reason"]],
                    height=350,
                )
                st.download_button(
                    label="Download existing all_claims_filtered.csv",
                    data=output_csv_llm.read_bytes(),
                    file_name="all_claims_filtered.csv",
                    mime="text/csv",
                    key="dl_existing_llm",
                )