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

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

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

    default_books_dir = Path.home() / "se-books"
    default_out_dir = REPO_ROOT / "out"

    books_dir = Path(st.text_input("Books folder", value=str(default_books_dir)))
    out_dir = Path(st.text_input("Output folder", value=str(default_out_dir)))

    safe_mkdir(books_dir)
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
    [
        "1) Extract",
        "2) Label with API",
        "3) Validate sample",
        "4) Score validation",
        "5) Browse outputs",
    ]
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
        books_dir.mkdir(parents=True, exist_ok=True)
        dest = books_dir / uploaded_book.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(uploaded_book.getvalue())
        st.success(f"Saved uploaded book to: {dest}")

        # Remember uploaded file and rerun so it appears in the dropdown
        st.session_state["last_uploaded_book"] = dest.name
        st.rerun()

    books = list_books(books_dir)
    if not books:
        st.error(f"No .epub/.azw3 files found in: {books_dir}")
        st.stop()

    book_files = [p for p in books if p.suffix.lower() != ".zip"]
    book_names = [p.name for p in book_files]
    book_map = {p.name: p for p in book_files}

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
        selected_path = book_map[selected]
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
# -------------------------
# 2) Label with API
# -------------------------
with tabs[1]:
    st.header("Label claims with API (BTH Azure)")
    st.write(
        "This reads all_claims.csv from a run folder and writes all_claims_labeled.csv."
    )

    run_folders = sorted([p for p in out_dir.glob("run_*") if p.is_dir()], reverse=True)
    if not run_folders:
        st.info("No run folders found. Run extraction first.")
        st.stop()

    run_folder = st.selectbox(
        "Select a run folder to label",
        [p.name for p in run_folders],
        key="label_run_folder",
    )
    run_path = out_dir / run_folder

    input_csv = run_path / "all_claims.csv"
    if not input_csv.exists():
        st.error(f"Missing all_claims.csv in {run_path}")
        st.stop()

    st.write("Input:", str(input_csv))

    batch_size = st.number_input(
        "Batch size", min_value=5, max_value=50, value=20, step=5
    )
    min_conf = st.slider("Min confidence for strict keep", 0.0, 1.0, 0.7, 0.05)

    out_csv = run_path / "all_claims_labeled.csv"
    meta_json = run_path / "openai_label_metadata.json"

    if st.button("Extract real claims (API)", type="primary"):
        import time
        import json
        import pandas as pd
        from se_claims_tool.llm.azure_client import AzureChatClient
        from se_claims_tool.llm.claim_labeler import label_claims_with_azure

        df = pd.read_csv(input_csv)
        df = df.fillna("")

        if "claim_id" not in df.columns or "claim_text" not in df.columns:
            st.error("all_claims.csv must contain claim_id and claim_text columns.")
            st.stop()

        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
        api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
        api_version = os.getenv(
            "AZURE_OPENAI_API_VERSION", "2024-02-15-preview"
        ).strip()
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini").strip()

        missing = []
        if not endpoint:
            missing.append("AZURE_OPENAI_ENDPOINT")
        if not api_key:
            missing.append("AZURE_OPENAI_API_KEY")
        if not deployment:
            missing.append("AZURE_OPENAI_DEPLOYMENT")
        if missing:
            st.error(f"Missing .env values: {missing}")
            st.stop()

        client = AzureChatClient()

        rows = df.to_dict(orient="records")

        with st.spinner("Labelling rows using API"):
            labels, meta = label_claims_with_azure(
                azure_client=client,
                rows=rows,
                model_name=deployment,
                batch_size=int(batch_size),
            )

        by_id = {x.claim_id: x for x in labels}

        df["api_is_claim"] = False
        df["api_is_author_perspective"] = False
        df["api_claim_type"] = ""
        df["api_confidence"] = 0.0
        df["api_reason"] = ""
        df["api_model"] = deployment
        df["api_run_id"] = time.strftime("%Y-%m-%dT%H-%M-%S")

        for i, r in df.iterrows():
            cid = str(r["claim_id"])
            lab = by_id.get(cid)
            if not lab:
                continue
            df.at[i, "api_is_claim"] = bool(lab.is_claim)
            df.at[i, "api_is_author_perspective"] = bool(lab.is_author_perspective)
            df.at[i, "api_claim_type"] = lab.claim_type
            df.at[i, "api_confidence"] = float(lab.confidence)
            df.at[i, "api_reason"] = lab.reason

        df["api_keep_strict"] = (
            (df["api_is_claim"] == True)
            & (df["api_is_author_perspective"] == False)
            & (df["api_confidence"] >= float(min_conf))
        )

        df.to_csv(out_csv, index=False)

        meta_out = {
            **(meta or {}),
            "endpoint": endpoint,
            "deployment": deployment,
            "api_version": api_version,
            "input_csv": str(input_csv),
            "output_csv": str(out_csv),
            "min_confidence": float(min_conf),
            "total_rows": int(len(df)),
            "strict_kept_rows": int(df["api_keep_strict"].sum()),
        }
        meta_json.write_text(
            json.dumps(meta_out, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        st.success(
            f"Wrote {out_csv.name}. Strict kept {int(df['api_keep_strict'].sum())} / {len(df)} rows."
        )
        st.dataframe(df[df["api_keep_strict"] == True].head(200), width="stretch")


# -------------------------
# 3) Validate sample
# -------------------------
with tabs[2]:
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

        csv_files = sorted(run_path.glob("*.csv"))

        preferred = []
        labeled = run_path / "all_claims_labeled.csv"
        raw = run_path / "all_claims.csv"

        if labeled.exists():
            preferred.append(labeled)
        if raw.exists():
            preferred.append(raw)

        choices = preferred + [p for p in csv_files if p not in preferred]

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
# 4) Score validation
# -------------------------
with tabs[3]:
    st.subheader("4) Score a filled validation sample and generate a report")

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
# 5) Browse outputs
# -------------------------
with tabs[4]:
    st.subheader("5) Browse outputs")

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
        labeled = run_path / "all_claims_labeled.csv"
        if labeled.exists():
            files = [labeled] + [p for p in files if p != labeled]
        if not files:
            st.info("No files in this run folder.")
        else:
            chosen = st.selectbox("Select a file", [p.name for p in files])
            fpath = run_path / chosen

            if fpath.suffix.lower() == ".csv":
                df = pd.read_csv(fpath)
                st.dataframe(df, width="stretch")
            elif fpath.suffix.lower() in {".md", ".txt", ".log", ".jsonl", ".json"}:
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
