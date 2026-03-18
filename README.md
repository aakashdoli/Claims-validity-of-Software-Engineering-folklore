# Claims Validity of Software Engineering Folklore

**Master's Thesis — PA2534 VT26**  
Blekinge Institute of Technology

**Authors:** Aakash Doli · Ekshith Satnur  
**Supervisors:** Davide Fucci (BTH) · Greg Wilson (Third Bit)

---

## Overview

Two-stage pipeline for extracting SE folklore claims from practitioner books.

**Stage 1 — NLP Pre-filter** (`nlp/claim_detector.py`)  
Regex-based pattern matching across six claim types. High recall, no API calls.

**Stage 2 — LLM Filter** (`llm/azure_llm_filter.py`)  
Azure OpenAI (gpt-4o) verifies each candidate with context (prev + sentence + next). Temperature = 0.0 for reproducibility.

**Claim definition:**  
A declarative sentence asserting a generalizable proposition about SE practice, behavior, process, tools, or outcomes — falsifiable against empirical evidence.

**Claim types:** NORMATIVE · CAUSAL · COMPARATIVE · QUANTITATIVE · GENERALIZATION · AUTHOR_PERSPECTIVE

---

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Copy `.env.example` to `.env` and fill in your Azure credentials.

## Running
```bash
streamlit run ui/app.py
```

---

## Structure
```
src/se_claims_tool/
  nlp/claim_detector.py       # Stage 1: NLP pre-filter
  llm/azure_llm_filter.py     # Stage 2: Azure LLM filter
  ingest/                     # EPUB, AZW3, PDF ingestion
  pipeline.py                 # Two-stage extraction logic
  batch_pipeline.py           # Multi-book corpus runner
  models_rq1.py               # Output schema (29 columns)
  citations.py                # Citation detection
  export/                     # CSV/JSONL writers
ui/app.py                     # Streamlit interface
```