# label_with_gemini.py (Version 7 - Zero Post-Processing)
# Relies on a powerful prompt to get clean, specific output directly from Gemini.

import os
import pandas as pd
import google.generativeai as genai
from tqdm import tqdm
import time

# --- Configuration ---
API_KEY = "AIzaSyC1YkMA4YPHjvaOCZZtPw2CwnLkk9qFr00"
INPUT_FILENAME = "unlabeled_titles_with_url.csv"
OUTPUT_FILENAME = "service_dataset_gemini_labeled.csv"
MAX_REQUESTS_PER_RUN = 1000 
REQUEST_DELAY_SECONDS = 4

# --- "Bulletproof" Gemini Prompt ---
def create_gemini_prompt(app_name, window_title, url):
    """Creates a prompt for extracting application/service names."""
    url_string = f"URL: {url}" if url else "URL: N/A"

    return f"""Extract the name of the application or service being used.

GOAL: Identify what tool/platform the user is actively using.

PRIORITY:
1. Brand/Service name (for websites/web apps): YouTube, Discord, Netflix, X, etc.
2. Application name (for desktop apps): WhatsApp, Telegram, VLC Media Player, Notepad, etc.

RULES:
- Output ONLY the name
- Use proper capitalization and common names
- For websites: extract the brand name, not the browser
- For desktop apps: use the well-known application name
- Ignore file names, document titles, or specific content

EXAMPLES:
App: chrome.exe | Title: My Favorite Song - YouTube | URL: youtube.com/watch?v=xyz
→ YouTube

App: WhatsApp.exe | Title: Chat with John - WhatsApp | URL: N/A
→ WhatsApp

App: Code.exe | Title: main.py - MyProject - Visual Studio Code | URL: N/A
→ VS Code

App: vlc.exe | Title: movie.mp4 - VLC media player | URL: N/A
→ VLC Media Player

App: notepad.exe | Title: notes.txt - Notepad | URL: N/A
→ Notepad

App: firefox.exe | Title: Dashboard - Discord | URL: discord.com/channels/123
→ Discord

App: msedge.exe | Title: Home - Netflix | URL: netflix.com/browse
→ Netflix

App: Taskmgr.exe | Title: Task Manager | URL: N/A
→ Task Manager

App: SnippingTool.exe | Title: Snipping Tool | URL: N/A
→ Snipping Tool

EXTRACT FROM:
App: {app_name}
Title: {window_title}
{url_string}

Answer:
"""

def main():
    print("--- Gemini Auto-Labeler (Zero Post-Processing) ---")

    if API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        print("Error: Please replace 'YOUR_GEMINI_API_KEY_HERE' with your actual Gemini API key.")
        return

    try:
        df_unlabeled = pd.read_csv(INPUT_FILENAME).fillna('')
    except FileNotFoundError:
        print(f"Error: Input file '{INPUT_FILENAME}' not found. Run 'collect_titles_with_url.py' first.")
        return

    # --- Logic to avoid re-labeling already processed data ---
    # We pre-format the input text to match the final output format for a reliable check.
    df_unlabeled['text'] = df_unlabeled.apply(
        lambda row: f"[APP]: {row['app_name']} [TITLE]: {row['window_title']} [URL]: {row['url']}", axis=1
    )
    
    already_labeled_texts = set()
    if os.path.exists(OUTPUT_FILENAME):
        try:
            df_labeled = pd.read_csv(OUTPUT_FILENAME)
            already_labeled_texts = set(df_labeled['text'])
            print(f"Found {len(already_labeled_texts)} already labeled records. They will be skipped.")
        except (pd.errors.EmptyDataError, FileNotFoundError):
            pass # File exists but is empty, or was deleted. No problem.

    df_to_label = df_unlabeled[~df_unlabeled['text'].isin(already_labeled_texts)]
    
    if df_to_label.empty:
        print("No new records to label. Exiting.")
        return
    
    print(f"Found {len(df_to_label)} new records to label.")

    # --- Gemini API Interaction Loop ---
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash-lite-preview-06-17')

    results = []
    requests_made = 0
    
    # Use tqdm for a progress bar, processing up to the MAX_REQUESTS_PER_RUN limit
    for index, row in tqdm(df_to_label.head(MAX_REQUESTS_PER_RUN).iterrows(), total=min(len(df_to_label), MAX_REQUESTS_PER_RUN), desc="Labeling with Gemini"):
        app_name = row['app_name']
        window_title = row['window_title']
        url = row['url']
        
        prompt = create_gemini_prompt(app_name, window_title, url)
        
        try:
            response = model.generate_content(prompt)
            # We trust the prompt. We just do a minimal cleanup of whitespace and stray punctuation.
            label = response.text.strip().strip('."')
            # If the model returns an empty string, we'll mark it as Unknown
            if not label:
                label = "Unknown"

        except Exception as e:
            print(f"\nAPI Error on row {index}: {e}. Assigning 'Unknown'.")
            label = "Unknown"
        
        text_blob = row['text'] # Use the pre-formatted text blob
        results.append({'text': text_blob, 'label': label})
        requests_made += 1
        
        time.sleep(REQUEST_DELAY_SECONDS) # Respect the RPM limit

    if not results:
        print("No new labels were generated in this run.")
        return

    # Convert new results to a DataFrame and append to the output file
    df_newly_labeled = pd.DataFrame(results)
    # The `mode='a'` appends, and `header=not os.path.exists(...)` writes the header only once.
    df_newly_labeled.to_csv(OUTPUT_FILENAME, mode='a', header=not os.path.exists(OUTPUT_FILENAME), index=False)

    print(f"\n--- Labeling Complete for this Run ---")
    print(f"Made {requests_made} API requests.")
    print(f"Appended {len(df_newly_labeled)} new records to '{OUTPUT_FILENAME}'.")

if __name__ == "__main__":
    main()