import pdfplumber
import pandas as pd
import google.generativeai as genai
import time
import json
import os
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load environment variables early so we don't accidentally commit keys to version control
load_dotenv() 

api_key = os.getenv("GOOGLE_API_KEY")

# It's better to crash immediately if the key is missing than to fail silently later
if not api_key:
    raise ValueError("API Key not found! Make sure you have a .env file with GOOGLE_API_KEY in it.")

genai.configure(api_key=api_key)

# We use the flash model because it's faster and cheaper for high-volume text analysis
model = genai.GenerativeModel('gemini-1.5-flash')

def extract_text_from_pdf(pdf_path):
    print(f"Processing PDF: {pdf_path}...")
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            page_number = f"Page {i + 1}"
            
            # Skip empty or very short pages (like title pages) to save API tokens
            if text and len(text) > 100: 
                yield page_number, text

def extract_text_from_epub(epub_path):
    print(f"Processing EPUB: {epub_path}...")
    try:
        book = epub.read_epub(epub_path)
    except Exception as e:
        print(f"Error reading EPUB: {e}")
        return

    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            # EPUBs are basically HTML, so we need BeautifulSoup to strip tags and get clean text
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            text = soup.get_text()
            chapter_title = item.get_name()
            
            if len(text) > 100:
                yield f"File: {chapter_title}", text

def analyze_chunk_with_gemini(text, location_id, book_title):
    # This prompt forces the model to act as a filter, only returning structured JSON
    # so we don't have to parse natural language responses later.
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
        
        # Sometimes the model wraps the JSON in markdown blocks, so we clean that up just in case
        if raw.startswith("```json"):
            raw = raw.replace("```json", "").replace("```", "")
        
        return json.loads(raw)
        
    except Exception as e:
        # Don't let one bad chunk crash the whole script; just log it and move on
        print(f"  [!] Error on {location_id}: {e}")
        return []

def process_book(file_path):
    book_title = os.path.basename(file_path)
    all_claims = []
    
    # Simple router to handle different file types
    if file_path.lower().endswith('.pdf'):
        iterator = extract_text_from_pdf(file_path)
    elif file_path.lower().endswith('.epub'):
        iterator = extract_text_from_epub(file_path)
    else:
        print(f"Unsupported file type: {file_path}")
        return []

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
        
        # A small sleep helps avoid hitting the API rate limits (HTTP 429)
        time.sleep(0.5)

    return all_claims

if __name__ == "__main__":
    # Update this filename to whatever book you actually want to mine
    target_book = "test_conway.pdf"  
    
    if os.path.exists(target_book):
        results = process_book(target_book)
        
        if results:
            df = pd.DataFrame(results)
            
            # Reorder columns to make the CSV easier to read for humans
            desired_order = ['Claim Text', 'Book Title', 'Page Number', 'Has Citation (Yes/No)', 'Confidence']
            final_cols = [c for c in desired_order if c in df.columns]
            df = df[final_cols]
            
            csv_name = "mined_claims.csv"
            df.to_csv(csv_name, index=False)
            print(f"\nSUCCESS! Saved {len(results)} claims to '{csv_name}'.")
            print(df.head()) 
        else:
            print("\nAnalysis complete. No claims found.")
    else:
        print(f"\n[ERROR] File '{target_book}' not found.")
        print("Please place a PDF or EPUB in this folder and update line 135.")