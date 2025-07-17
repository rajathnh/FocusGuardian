# interactive_labeler.py
import pandas as pd
import os
import time
import csv

# --- Configuration ---
# The raw data file created by data_recorder.py
RAW_DATA_FILENAME = "raw_productivity_data.csv" 
# The final, clean training file we are creating
LABELED_DATA_FILENAME = "productivity_dataset.csv" 

def main():
    print("--- Interactive Labeling Tool ---")
    
    # Check if the raw data file exists
    if not os.path.exists(RAW_DATA_FILENAME):
        print(f"Error: Raw data file '{RAW_DATA_FILENAME}' not found.")
        print("Please run 'data_recorder.py' first to collect some data.")
        return

    # Load the unlabeled data using pandas
    try:
        df_unlabeled = pd.read_csv(RAW_DATA_FILENAME)
        # Fill any potential empty cells with empty strings to avoid errors
        df_unlabeled.fillna('', inplace=True) 
    except pd.errors.EmptyDataError:
        print(f"Error: The file '{RAW_DATA_FILENAME}' is empty. No data to label.")
        return

    # Keep track of which timestamps we have already processed and saved
    already_labeled_ts = set()
    if os.path.exists(LABELED_DATA_FILENAME):
        # This is a simple check. A more robust system would parse the text blob,
        # but for now, we'll just append and risk duplicates if run multiple times.
        # It's best to run this script once per raw data file.
        print(f"Found existing labeled file '{LABELED_DATA_FILENAME}'. New labels will be appended.")

    # Open the final dataset file in 'append' mode
    with open(LABELED_DATA_FILENAME, 'a', newline='', encoding='utf-8') as csv_file:
        fieldnames = ['text', 'label']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        
        # Write header only if the file is new or empty
        if os.path.getsize(LABELED_DATA_FILENAME) == 0:
            writer.writeheader()

        # --- The Main Labeling Loop ---
        new_records_count = 0
        for index, row in df_unlabeled.iterrows():
            
            # Display the data point for the user to label
            print("\n" + "="*60)
            try:
                ts = time.strftime('%H:%M:%S', time.localtime(float(row['timestamp'])))
                print(f"Record #{index + 1}/{len(df_unlabeled)} from {ts}")
            except (ValueError, TypeError):
                 print(f"Record #{index + 1}/{len(df_unlabeled)}")

            print(f"  APP:      {row['app_name']}")
            print(f"  TITLE:    {row['window_title']}")
            print(f"  FOCUS:    {row['focus_status']} ({row['focus_reason']})")
            print(f"  EMOTION:  {row['emotion']}")
            print("--- OCR Snippet ---")
            ocr_preview = str(row['ocr_content']).replace('\n', ' ').strip()
            print(f"  {ocr_preview[:300]}...") # Show a generous snippet
            print("="*60)

            # Get user input
            label_input = ""
            while label_input not in ['y', 'n', 's', 'q']:
                label_input = input("Productive? (y/n/s for skip, q to quit): ").lower()

            if label_input == 'q':
                print("Quitting labeling session.")
                break
            if label_input == 's':
                print("--> Skipping.")
                continue

            label = 1 if label_input == 'y' else 0
            
            # Format the text blob exactly as needed for DistilBERT training
            text_blob = (
                f"[FOCUS]: {row['focus_status']} "
                f"[REASON]: {row['focus_reason']} "
                f"[EMOTION]: {row['emotion']} "
                f"[APP]: {row['app_name']} "
                f"[TITLE]: {row['window_title']} "
                f"[CONTENT]: {row['ocr_content']}"
            )
            
            # Write the new labeled record to our final training file
            writer.writerow({'text': text_blob, 'label': label})
            new_records_count += 1
            print(f"--> Labeled as '{'Productive' if label == 1 else 'Unproductive'}'")

    print(f"\nLabeling session complete. Added {new_records_count} new records to '{LABELED_DATA_FILENAME}'.")

if __name__ == '__main__':
    main()