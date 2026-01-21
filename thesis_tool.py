import streamlit as st
from openai import AzureOpenAI
import pandas as pd
import PyPDF2
import json
import time
import os
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Claims Extractor", layout="wide")
st.title("📚 Claims Extractor (BTH Azure OpenAI)")

with st.sidebar:
    st.header("BTH Azure Settings")
    
    # We grab these defaults from the environment so you don't have to type them every time you reload
    env_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "https://bth-ai.azure-api.net/student")
    env_key = os.getenv("AZURE_OPENAI_API_KEY", "")
    env_deployment = os.getenv("AZURE_DEPLOYMENT_NAME", "gpt-4o-mini")
    env_version = os.getenv("AZURE_API_VERSION", "2024-02-15-preview")

    azure_endpoint = st.text_input("Azure Endpoint", value=env_endpoint)
    api_key = st.text_input("Azure API Key", value=env_key, type="password")
    deployment_name = st.text_input("Deployment Name", value=env_deployment)
    api_version = st.text_input("API Version", value=env_version)
    
    st.info(f"Targeting Deployment: {deployment_name}")
    
    st.markdown("---")
    strategy = st.selectbox(
        "Select Analysis Strategy",
        ("Strict Academic (Definitions)", "Few-Shot (Examples)")
    )

def extract_text_from_pdf(uploaded_file):
    try:
        pdf_reader = PyPDF2.PdfReader(uploaded_file)
        text_data = []
        for i, page in enumerate(pdf_reader.pages):
            text = page.extract_text()
            if text:
                text_data.append({"page": i + 1, "text": text})
        return text_data
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return []

def analyze_with_azure(client, model_name, prompt, page_num):
    try:
        # We explicitly enforce JSON mode here.
        # This prevents the model from adding conversational fluff like "Here is your JSON:" which breaks parsing.
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a helpful research assistant. Output only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"} 
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        st.error(f"Error on Page {page_num}: {e}")
        return []

def construct_prompt(text_chunk, page_num, strategy_type):
    if strategy_type == "Strict Academic (Definitions)":
        return f"""
        Analyze text from Page {page_num}. Extract "Academic Claims" (arguable assertions, causal relationships, strong opinions).
        Ignore simple facts or table of contents.
        
        Return a JSON object with this exact structure:
        {{ "claims": [
            {{"claim": "Exact text of the claim", "has_citation": "Yes/No", "source_context": "Author (Year)"}}
        ] }}
        
        TEXT TO ANALYZE:
        {text_chunk}
        """
    else:
        return f"""
        Extract claims from Page {page_num}.
        
        EXAMPLES:
        Input: "Jay is 21." -> Output: []
        Input: "Cognitive pollution is a better model (See: Asbestos)." -> Output: [{{"claim": "Cognitive pollution is a better model.", "has_citation": "No", "source_context": "Author synthesis"}}]
        
        Return a JSON object with this exact structure:
        {{ "claims": [ ...list of claims... ] }}

        TEXT TO ANALYZE:
        {text_chunk}
        """

uploaded_file = st.file_uploader("Upload PDF Document", type=["pdf"])

if uploaded_file:
    if not api_key:
        st.warning("Please enter your BTH API Key in the sidebar or .env file.")
    else:
        if st.button("Start Analysis"):
            
            client = AzureOpenAI(
                api_key=api_key,
                api_version=api_version,
                azure_endpoint=azure_endpoint
            )

            with st.spinner("Reading PDF..."):
                pages_data = extract_text_from_pdf(uploaded_file)
            
            all_claims = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            total_pages = len(pages_data)
            
            for index, item in enumerate(pages_data):
                progress = (index + 1) / total_pages
                progress_bar.progress(progress)
                status_text.text(f"Processing Page {item['page']} of {total_pages}...")
                
                prompt = construct_prompt(item['text'], item['page'], strategy)
                result_json = analyze_with_azure(client, deployment_name, prompt, item['page'])
                
                if result_json:
                    # Sometimes the API wraps the list in a key like "claims", sometimes it returns the list directly.
                    # This check handles both cases so the app doesn't crash.
                    claims_list = result_json.get("claims", []) if isinstance(result_json, dict) else result_json
                    
                    for entry in claims_list:
                        entry['page_number'] = item['page']
                        all_claims.append(entry)
                
                # A small sleep to prevent overwhelming the BTH student server
                time.sleep(0.1)
            
            status_text.text("Done!")
            st.success("Analysis Complete!")
            
            if all_claims:
                df = pd.DataFrame(all_claims)
                
                # Normalize columns to ensure the CSV structure is consistent even if some fields are missing
                desired_cols = ['page_number', 'claim', 'has_citation', 'source_context']
                for c in desired_cols:
                    if c not in df.columns: df[c] = "N/A"
                df = df[desired_cols]
                
                st.dataframe(df, use_container_width=True)
                
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download BTH Claims CSV", csv, "thesis_claims.csv", "text/csv")
            else:
                st.warning("No claims found in this document.")