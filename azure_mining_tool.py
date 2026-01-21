import streamlit as st
import pdfplumber
import pandas as pd
from openai import AzureOpenAI
import time
import json
import os
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Thesis Miner (BTH Azure)", page_icon="🎓", layout="wide")

# --- LOAD ENVIRONMENT VARIABLES ---
load_dotenv()
env_api_key = os.getenv("AZURE_OPENAI_API_KEY")
env_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
env_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

# --- SIDEBAR SETTINGS ---
with st.sidebar:
    st.header("🎓 BTH Azure Settings")
    
    # Auto-fill from .env or let user type
    api_key = st.text_input("Azure API Key", value=env_api_key if env_api_key else "", type="password")
    endpoint = st.text_input("Azure Endpoint", value=env_endpoint if env_endpoint else "https://bth-ai.azure-api.net/student")
    # CRITICAL: This must match your deployment name exactly
    deployment = st.text_input("Deployment Name", value=env_deployment if env_deployment else "gpt-4o-mini")
    
    # Standard Azure version
    api_version = st.text_input("API Version", value="2024-02-15-preview")

    st.divider()
    st.info("ℹ️ **Model:** GPT-4o Mini (Fast & Accurate)")
    
    # Speed Control
    cooldown = st.slider("Safety Pause (seconds)", 0.0, 2.0, 0.5)
    show_debug = st.checkbox("Show Raw AI Output", value=False)

    # Initialize Client
    client = None
    if api_key and endpoint and deployment:
        try:
            client = AzureOpenAI(
                api_key=api_key,
                api_version=api_version,
                azure_endpoint=endpoint
            )
            st.success("✅ BTH Client Configured")
        except Exception as e:
            st.error(f"Config Error: {e}")

# --- HELPER: ROBUST JSON PARSER ---
def extract_and_repair_json(text):
    text = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except:
        start = text.find('[')
        end = text.rfind(']') + 1
        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end])
            except:
                pass
    return []

# --- HELPER: DEEP ANALYSIS (GPT-4o Mini Optimized) ---
def analyze_page_azure(text, page_label, retries=3):
    """
    Sends a single page to Azure OpenAI GPT-4o Mini.
    """
    system_prompt = "You are a Research Assistant. Extract claims in JSON format."
    
    user_prompt = f"""
    Analyze the text from "{page_label}".
    
    GOAL: Identify "Causal Claims" (X affects Y) and "Folklore" (beliefs stated as fact).
    
    RULES:
    1. EXTRACT: Any sentence claiming "A improves B", "X causes Y", or stating a rule of thumb.
    2. CHECK CITATION: Is there a citation (e.g. [1], (Name, 2020)) immediately supporting it?
    3. FILTER: Ignore general definitions. Keep only Causal Claims.

    INPUT TEXT:
    \"\"\"{text}\"\"\"

    OUTPUT JSON:
    [
        {{
            "claim_text": "Exact sentence found.",
            "simplified_claim": "X causes Y",
            "type": "Folklore" or "Cited Fact",
            "has_citation": "Yes" or "No",
            "location": "{page_label}"
        }}
    ]
    """

    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=deployment, 
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.0, 
                response_format={ "type": "json_object" } 
            )
            
            raw_text = response.choices[0].message.content
            
            if show_debug:
                with st.sidebar:
                    st.text(f"Raw Output {page_label}")
                    st.code(raw_text[:200], language="json")

            data = extract_and_repair_json(raw_text)
            
            if isinstance(data, dict):
                for key in data:
                    if isinstance(data[key], list): return data[key]
                return [] 
                
            return data

        except Exception as e:
            if "429" in str(e): # Rate Limit
                time.sleep(2 * (attempt + 1))
            else:
                if show_debug: st.sidebar.error(f"Error: {e}")
                return []
    return []

# --- EXTRACTORS ---
def extract_text_from_pdf(uploaded_file):
    chunks = []
    with pdfplumber.open(uploaded_file) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text and len(text) > 50:
                chunks.append((f"Page {i+1}", text))
    return chunks

def extract_text_from_epub(uploaded_file):
    try:
        temp_filename = "temp_book.epub"
        with open(temp_filename, "wb") as f: f.write(uploaded_file.getbuffer())
        book = epub.read_epub(temp_filename)
        chunks = []
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                soup = BeautifulSoup(item.get_content(), 'html.parser')
                text = soup.get_text()
                title = item.get_name()
                if len(text) > 50:
                    chunks.append((f"File: {title}", text))
        if os.path.exists(temp_filename): os.remove(temp_filename)
        return chunks
    except: return []

# --- MAIN APP ---
st.title("🎓 Thesis Miner: BTH Azure Edition")
st.markdown("Automated Folklore Detection using **GPT-4o Mini**.")

uploaded_file = st.file_uploader("Upload Book", type=["pdf", "epub"])

if uploaded_file and st.button("Start Analysis"):
    if not client:
        st.warning("Please configure Azure credentials in the sidebar.")
    else:
        st.divider()
        
        with st.spinner("Extracting text..."):
            if uploaded_file.name.endswith(".pdf"):
                pages = extract_text_from_pdf(uploaded_file)
            else:
                pages = extract_text_from_epub(uploaded_file)
        
        st.info(f"Loaded {len(pages)} pages. Sending to Azure ({deployment})...")
        
        all_claims = []
        progress_bar = st.progress(0)
        status_box = st.empty()
        
        for i, (label, text) in enumerate(pages):
            progress_bar.progress((i + 1) / len(pages))
            status_box.markdown(f"**Scanning:** `{label}`")
            
            results = analyze_page_azure(text, label)
            
            if results:
                for r in results:
                    r['location'] = label
                    r['source_book'] = uploaded_file.name
                    all_claims.append(r)
            
            time.sleep(cooldown)

        st.success("✅ Analysis Complete!")
        
        if all_claims:
            df = pd.DataFrame(all_claims)
            st.subheader(f"Found {len(df)} Claims")
            
            cols = [c for c in ['location', 'type', 'simplified_claim', 'has_citation', 'claim_text'] if c in df.columns]
            st.dataframe(df[cols], use_container_width=True)
            
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("Download CSV", csv, "bth_mined_claims.csv", "text/csv")
        else:
            st.warning("No claims found.")