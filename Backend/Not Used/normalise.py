# normalize_labels.py
import pandas as pd
import re

INPUT_FILENAME = "service_dataset_gemini_labeled.csv"
OUTPUT_FILENAME = "service_dataset_final.csv"

def normalize_and_consolidate(row):
    label = str(row['label'])
    text = str(row['text'])
    
    # --- Rule 1: Prioritize URL for known services ---
    # This is the most powerful rule.
    if 'youtube.com' in text: return 'YouTube'
    if 'github.com' in text: return 'GitHub'
    if 'stackoverflow.com' in text: return 'Stack Overflow'
    if 'chatgpt.com' in text: return 'ChatGPT'
    if 'gemini.google.com' in text: return 'Gemini'
    if 'aistudio.google.com' in text: return 'Google AI Studio'
    if 'mail.google.com' in text: return 'Gmail'
    if 'drive.google.com' in text: return 'Google Drive'
    if 'postman.co' in text: return 'Postman'
    if 'mongodb.com' in text: return 'MongoDB'
    if 'x.com' in text or 'twitter.com' in text: return 'X'
    if 'discord.com' in text: return 'Discord'
    
    # --- Rule 2: Use App Name for desktop apps ---
    if 'Code.exe' in text: return 'VS Code'
    if 'vlc.exe' in text: return 'VLC'
    if 'explorer.exe' in text: return 'File Explorer'
    if 'Photos.exe' in text: return 'Image Viewer'
    if 'WINWORD.EXE' in text: return 'Microsoft Word'
    if 'POWERPNT.EXE' in text: return 'PowerPoint'
    if 'Notepad.exe' in text: return 'Notepad'

    # --- Rule 3: Handle Local Files viewed in browser ---
    if re.search(r"\[URL\]: (C:|/Users/|file:///)", text, re.IGNORECASE):
        if '.pdf' in text.lower(): return 'PDF Viewer'
        if any(ext in text.lower() for ext in ['.jpg', '.jpeg', '.png']): return 'Image Viewer'
        return 'Local File'

    # --- Fallback ---
    # If no rule matches, we can trust the Gemini label, but we'll standardize its casing.
    return label.title().replace('Github', 'GitHub').replace('Vs Code', 'VS Code')

def main():
    df = pd.read_csv(INPUT_FILENAME).dropna()
    df['label'] = df.apply(normalize_and_consolidate, axis=1)
    
    print("--- New, Cleaned Label Distribution ---")
    print(df['label'].value_counts())
    
    df.to_csv(OUTPUT_FILENAME, index=False)
    print(f"\nCleaned dataset with {len(df['label'].unique())} unique labels saved to '{OUTPUT_FILENAME}'")

if __name__ == '__main__':
    main()