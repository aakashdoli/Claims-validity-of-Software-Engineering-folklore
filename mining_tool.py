import pdfplumber
import pandas as pd
import google.generativeai as genai
import time
import json
import os
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from dotenv import load_dotenv  # <--- NEW IMPORT

# --- CONFIGURATION ---

# 1. Load the variables from the .env file
load_dotenv() 

# 2. Get the key securely
api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    raise ValueError("API Key not found! Make sure you have a .env file with GOOGLE_API_KEY in it.")

genai.configure(api_key=api_key)

# --- 1. TEXT EXTRACTORS ---
def extract_text_from_pdf(pdf_path):
    """Yields page number and text from PDF."""
    print(f"Processing PDF: {pdf_path}...")
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            page_number = f"Page {i + 1}"
            
            if text and len(text) > 100: 
                yield page_number, text

def extract_text_from_epub(epub_path):
    """Yields chapter title and text from EPUB."""
    print(f"Processing EPUB: {epub_path}...")
    try:
        book = epub.read_epub(epub_path)
    except Exception as e:
        print(f"Error reading EPUB: {e}")
        return

    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            text = soup.get_text()
            chapter_title = item.get_name()
            
            if len(text) > 100:
                yield f"File: {chapter_title}", text

# --- 2. THE BRAIN (GEMINI API) ---

def analyze_chunk_with_gemini(text, location_id, book_title):
    """Sends text to Gemini to find folklore & citations."""
    
    prompt = f"""
    You are a Software Engineering Researcher. Analyze this text from "{book_title}" ({location_id}).

    YOUR TASK:
    1. Identify "causal claims" (e.g., "X improves Y", "doing A leads to B") or named software laws/principles (e.g., "Conway's Law", "Brooks's Law").
    2. Identify "folklore" (common beliefs stated as facts without citing evidence).
    3. DETECT CITATIONS: Is this specific claim backed by a citation marker (e.g., [1], (Name, 2020)) *in this text snippet*?

    INPUT TEXT:
    \"\"\"{text[:4000]}\"\"\" 

    OUTPUT FORMAT:
    Return ONLY a valid JSON list. Example:
    [
        {{
            "Claim Text": "TDD reduces defect density by 40%.",
            "Has Citation (Yes/No)": "Yes",
            "Confidence": 0.95
        }},
        {{
            "Claim Text": "Conway's Law states that organizations which design systems are constrained to produce designs which are copies of the communication structures of these organizations.",
            "Has Citation (Yes/No)": "No",
            "Confidence": 0.99
        }}
    ]
    If nothing relevant is found, return []
    """

    try:
        response = model.generate_content(prompt)
        raw = response.text.strip()
        
        # Clean up Markdown formatting if Gemini adds it
        if raw.startswith("```json"):
            raw = raw.replace("```json", "").replace("```", "")
        
        return json.loads(raw)
        
    except Exception as e:
        # If it fails, print a small error but keep running
        print(f"  [!] Error on {location_id}: {e}")
        return []

# --- 3. MAIN PIPELINE ---

def process_book(file_path):
    book_title = os.path.basename(file_path)
    all_claims = []
    
    # Select Extractor
    if file_path.lower().endswith('.pdf'):
        iterator = extract_text_from_pdf(file_path)
    elif file_path.lower().endswith('.epub'):
        iterator = extract_text_from_epub(file_path)
    else:
        print(f"Unsupported file type: {file_path}")
        return []

    # Run Analysis
    print(f"--- Starting Analysis for {book_title} ---")
    for location, text in iterator:
        print(f"  Scanning {location}...")
        
        claims = analyze_chunk_with_gemini(text, location, book_title)
        
        if claims:
            print(f"    -> Found {len(claims)} claims!")
            for c in claims:
                c['Page Number'] = location
                c['Book Title'] = book_title
                all_claims.append(c)
        
        # Sleep slightly to be polite to the API
        time.sleep(0.5)

    return all_claims

# --- 4. EXECUTION ---

if __name__ == "__main__":
    # --- INPUT YOUR BOOK FILENAME HERE ---
    target_book = "test_conway.pdf"  # <--- CHANGE THIS to your actual file name
    
    if os.path.exists(target_book):
        results = process_book(target_book)
        
        if results:
            df = pd.DataFrame(results)
            # Ensure correct column order
            desired_order = ['Claim Text', 'Book Title', 'Page Number', 'Has Citation (Yes/No)', 'Confidence']
            # Only select columns that exist to avoid errors if the LLM hallucinated keys
            final_cols = [c for c in desired_order if c in df.columns]
            df = df[final_cols]
            
            csv_name = "mined_claims.csv"
            df.to_csv(csv_name, index=False)
            print(f"\nSUCCESS! Saved {len(results)} claims to '{csv_name}'.")
            print(df.head()) # Show preview
        else:
            print("\nAnalysis complete. No claims found.")
    else:
        print(f"\n[ERROR] File '{target_book}' not found.")
        print("Please place a PDF or EPUB in this folder and update line 135.")