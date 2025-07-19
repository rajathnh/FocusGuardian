# collect_titles.py
# Runs in the background to collect raw, unlabeled window titles for later processing.

import csv
import os
import time
import platform

# Use the reliable platform-specific libraries
if platform.system() == "Windows":
    try:
        import win32gui
        import psutil
        import win32process
    except ImportError:
        print("Please run 'pip install pywin32 psutil'")
        exit()
else:
    # This script is optimized for Windows, but you could add Mac/Linux getters here
    print("This script is optimized for Windows.")
    exit()

# --- Configuration ---
CAPTURE_INTERVAL_SECONDS = 10
OUTPUT_FILENAME = "unlabeled_titles.csv"

def get_active_window_data_windows():
    """Gets the active window's app name and title on Windows."""
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None, None
        
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid == 0:
            return None, None
            
        process_name = psutil.Process(pid).name()
        window_title = win32gui.GetWindowText(hwnd)
        
        if not window_title: # Skip empty titles
            return None, None
            
        return process_name, window_title
    except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
        return None, None

def main():
    print("--- Raw Title Collector ---")
    print(f"Capturing active window title every {CAPTURE_INTERVAL_SECONDS} seconds.")
    print(f"Data will be saved to '{OUTPUT_FILENAME}'.")
    print("Use your computer normally. Press Ctrl+C in this terminal to stop.")

    # Use a set to keep track of seen (app, title) pairs to avoid duplicates
    seen_data = set()
    
    # Load existing data to avoid re-capturing
    if os.path.exists(OUTPUT_FILENAME):
        with open(OUTPUT_FILENAME, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None) # Skip header
            for row in reader:
                seen_data.add(tuple(row))
        print(f"Loaded {len(seen_data)} existing records to avoid duplication.")

    try:
        with open(OUTPUT_FILENAME, 'a', newline='', encoding='utf-8') as csv_file:
            writer = csv.writer(csv_file)
            # Write header only if the file is new/empty
            if os.path.getsize(OUTPUT_FILENAME) == 0:
                writer.writerow(['app_name', 'window_title'])
            
            while True:
                time.sleep(CAPTURE_INTERVAL_SECONDS)
                
                app, title = get_active_window_data_windows()
                
                if app and title:
                    data_pair = (app, title)
                    if data_pair not in seen_data:
                        writer.writerow([app, title])
                        csv_file.flush()
                        seen_data.add(data_pair)
                        print(f"[{time.strftime('%H:%M:%S')}] Captured: {title}")
                        
    except KeyboardInterrupt:
        print("\n--- Capture Stopped ---")
        print(f"Total unique records in '{OUTPUT_FILENAME}': {len(seen_data)}")
    except Exception as e:
        print(f"\nAn error occurred: {e}")

if __name__ == "__main__":
    main()