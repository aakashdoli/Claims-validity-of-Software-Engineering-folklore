import streamlit as st
from openai import AzureOpenAI
import pandas as pd
import PyPDF2
import json
import time
import os
from dotenv import load_dotenv

# Load secrets from the .env file if it exists
load_dotenv()

st.set_page_config(page_title="Thesis Batch Processor", layout="wide")
st.title("📚 Thesis Batch Claim Validator (Multiple Books)")
st.markdown("Created for Doli Aakash & Ekshith Satnur | Powered by BTH AI API")

with st.sidebar:
    st.header("BTH Azure Settings")
    
    # Grab defaults from environment variables so we don't have to re-type them constantly
    env_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "https://bth-ai.azure-api.net/student")
    env_key = os.getenv("AZURE_OPENAI_API_KEY", "")
    env_deployment = os.getenv("AZURE_DEPLOYMENT_NAME", "gpt-4o-mini")
    env_version = os.getenv("AZURE_API_VERSION", "2024-02-15-preview")

    azure_endpoint = st.text_input("Azure Endpoint", value=env_endpoint)
    api_key = st.text_input("Azure API Key", value=env_key, type="password")
    deployment_name = st.text_input("Deployment Name", value=env_deployment)
    api_version = st.text_input("API Version", value=env_version)
    
    st.markdown("---")
    strategy = st.selectbox(
        "Select Analysis Strategy",
        ("Strict Academic (Definitions)", "Few-Shot (Examples)")
    )

def extract_text_from_pdf(uploaded_file):
    # Simple reader that iterates through pages and pulls raw text
    try:
        pdf_reader = PyPDF2.PdfReader(uploaded_file)
        text_data = []
        for i, page in enumerate(pdf_reader.pages):
            text = page.extract_text()
            if text:
                text_data.append({"page": i + 1, "text": text})
        return text_data
    except Exception as e:
        st.error(f"Error reading {uploaded_file.name}: {e}")
        return []

def analyze_with_azure(client, model_name, prompt):
    # We force the model to output JSON so we can easily parse the results later
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a research assistant. Output valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"} 
        )
        return json.loads(response.choices[0].message.content)
    except Exception:
        # If the API fails for one chunk, just return empty so the whole batch doesn't crash
        return []

def construct_prompt(text_chunk, page_num, strategy_type):
    if strategy_type == "Strict Academic (Definitions)":
        return f"""
        Analyze text from Page {page_num}. Extract "Academic Claims" (arguable assertions, causal relationships).
        Ignore simple facts.
        Return JSON: {{ "claims": [{{"claim": "text", "has_citation": "Yes/No", "source_context": "Author (Year)"}}] }}
        TEXT: {text_chunk}
        """
    else:
        # Giving the model examples (few-shot) usually improves accuracy
        return f"""
        Extract claims from Page {page_num}.
        EXAMPLES:
        Input: "Jay is 21." -> Output: []
        Input: "Cognitive pollution is a better model (See: Asbestos)." -> Output: [{{"claim": "Cognitive pollution is a better model.", "has_citation": "No", "source_context": "Author synthesis"}}]
        Return JSON: {{ "claims": [ ...list of claims... ] }}
        TEXT: {text_chunk}
        """

# Allow the user to upload multiple PDFs at once
uploaded_files = st.file_uploader("Upload PDF Books (Select Multiple)", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    if not api_key:
        st.warning("Please enter your BTH API Key.")
    else:
        if st.button(f"Start Batch Analysis ({len(uploaded_files)} Books)"):
            
            client = AzureOpenAI(
                api_key=api_key,
                api_version=api_version,
                azure_endpoint=azure_endpoint
            )
            
            master_claims_list = []
            
            # Setup a single progress bar to track the entire batch job
            total_progress_bar = st.progress(0)
            status_text = st.empty()
            
            for file_index, uploaded_file in enumerate(uploaded_files):
                status_text.text(f"📖 Processing Book {file_index + 1}/{len(uploaded_files)}: {uploaded_file.name}...")
                
                pages_data = extract_text_from_pdf(uploaded_file)
                total_pages = len(pages_data)
                
                for i, item in enumerate(pages_data):
                    # Calculate overall progress across all files and pages
                    current_progress = (file_index / len(uploaded_files)) + ((i / total_pages) / len(uploaded_files))
                    total_progress_bar.progress(min(current_progress, 1.0))
                    
                    prompt = construct_prompt(item['text'], item['page'], strategy)
                    result_json = analyze_with_azure(client, deployment_name, prompt)
                    
                    if result_json:
                        # Handle cases where the API returns a list directly or a dict with a 'claims' key
                        claims = result_json.get("claims", []) if isinstance(result_json, dict) else result_json
                        for c in claims:
                            c['filename'] = uploaded_file.name 
                            c['page_number'] = item['page']
                            master_claims_list.append(c)
                    
                    # Brief pause to avoid hitting the API rate limits
                    time.sleep(0.1)
            
            total_progress_bar.progress(1.0)
            status_text.text("✅ Batch Analysis Complete!")
            st.balloons()
            
            if master_claims_list:
                df = pd.DataFrame(master_claims_list)
                
                # Organize columns cleanly before showing the user
                cols = ['filename', 'page_number', 'claim', 'has_citation', 'source_context']
                for c in cols:
                    if c not in df.columns: df[c] = "-"
                df = df[cols]
                
                st.dataframe(df, use_container_width=True)
                
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download Master CSV", csv, "master_thesis_claims.csv", "text/csv")
            else:
                st.warning("No claims found in any of the uploaded books.")