import streamlit as st
import google.generativeai as genai
import pandas as pd
import PyPDF2
import json
import time
import os
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Thesis Batch Tool (Gemini)", layout="wide")
st.title("📚 Thesis Batch Processor (Gemini Edition)")
st.markdown("Created for Doli Aakash & Ekshith Satnur | **Optimized for High Volume**")
st.info("ℹ️ This tool runs slower to prevent crashing, but it can process unlimited books for free.")

with st.sidebar:
    st.header("Settings")
    
    # Grab the key from the environment if available so we don't have to paste it every time
    env_gemini_key = os.getenv("GEMINI_API_KEY", "")
    api_key = st.text_input("Gemini API Key", value=env_gemini_key, type="password")
    
    model_name = st.selectbox("Select Model", ["gemini-2.5-flash", "gemini-1.5-pro"])
    
    strategy = st.selectbox(
        "Select Strategy",
        ("Strict Academic (Definitions)", "Few-Shot (Examples)")
    )
    
    if api_key:
        genai.configure(api_key=api_key)

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
        st.error(f"Error reading {uploaded_file.name}: {e}")
        return []

def analyze_with_retry(model, prompt, page_num):
    # The API throws a 429 error if we go too fast. 
    # This loop catches that specific error, waits a bit, and tries again.
    max_retries = 5
    base_wait = 10 
    
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            # Cleanup the response to ensure it's valid JSON
            return json.loads(response.text.replace("```json", "").replace("```", "").strip())
        except Exception as e:
            error_msg = str(e)
            
            if "429" in error_msg or "resource_exhausted" in error_msg.lower():
                wait_time = base_wait * (attempt + 1)
                st.warning(f"⏳ Rate limit on Page {page_num}. Pausing {wait_time}s...")
                time.sleep(wait_time)
            else:
                # If it's a non-recoverable error, just skip this page
                return []
    
    return []

def construct_prompt(text_chunk, page_num, strategy_type):
    if strategy_type == "Strict Academic (Definitions)":
        return f"""
        Analyze Page {page_num}. Extract "Academic Claims" (arguable assertions).
        Return JSON: [{{"claim": "text", "has_citation": "Yes/No", "source_context": "Source"}}]
        TEXT: {text_chunk}
        """
    else:
        return f"""
        Extract claims from Page {page_num}.
        EXAMPLES:
        Input: "Jay is 21." -> Output: []
        Input: "Cognitive pollution is a better model (See: Asbestos)." -> Output: [{{"claim": "Cognitive pollution is a better model.", "has_citation": "No", "source_context": "Author synthesis"}}]
        Return JSON: [{{"claim": "text", "has_citation": "Yes/No", "source_context": "Source"}}]
        TEXT: {text_chunk}
        """

uploaded_files = st.file_uploader("Upload 10+ PDF Books", type=["pdf"], accept_multiple_files=True)

if uploaded_files and api_key:
    if st.button(f"Start Batch Analysis ({len(uploaded_files)} Books)"):
        
        model = genai.GenerativeModel(model_name)
        master_claims_list = []
        
        total_bar = st.progress(0)
        status_text = st.empty()
        
        for file_idx, file in enumerate(uploaded_files):
            status_text.text(f"📖 Reading Book {file_idx+1}: {file.name}...")
            pages = extract_text_from_pdf(file)
            
            for i, page in enumerate(pages):
                # Update the progress bar relative to total work (files * pages)
                prog = (file_idx / len(uploaded_files)) + ((i / len(pages)) / len(uploaded_files))
                total_bar.progress(min(prog, 1.0))
                
                prompt = construct_prompt(page['text'], page['page'], strategy)
                result = analyze_with_retry(model, prompt, page['page'])
                
                if result:
                    claims = result.get("claims", []) if isinstance(result, dict) else result
                    for c in claims:
                        c['filename'] = file.name
                        c['page_number'] = page['page']
                        master_claims_list.append(c)
                
                # Crucial: The free tier usually allows ~15 calls/min. 
                # This pause keeps us safe from hitting the limit.
                time.sleep(4) 
        
        total_bar.progress(1.0)
        st.success("Analysis of all books complete!")
        
        if master_claims_list:
            df = pd.DataFrame(master_claims_list)
            st.dataframe(df)
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Master CSV", csv, "all_books_claims.csv", "text/csv")