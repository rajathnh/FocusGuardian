# collect_titles_with_url.py (Version 3.1 - Robust pywinauto)
# Captures app name, window title, AND the browser URL for richer data.

import csv
import os
import time
import platform
import re

# --- Required Libraries ---
if platform.system() == "Windows":
    try:
        import win32gui
        import psutil
        import win32process
        # Using the more robust pywinauto library
        import pywinauto
    except ImportError:
        print("Please run 'pip install pywin32 psutil pywinauto'")
        exit()
else:
    print("This script is optimized for Windows and its UI Automation features.")
    exit()

# --- Configuration ---
CAPTURE_INTERVAL_SECONDS = 1
OUTPUT_FILENAME = "unlabeled_titles_with_url.csv"

# --- NEW, MORE ROBUST Function to get URL using pywinauto ---
def get_url_from_browser():
    """
    Gets the URL from the active tab of Chrome, Edge, or Firefox using pywinauto.
    Returns the URL as a string or None if it fails.
    """
    try:
        # Get the handle of the foreground window
        hwnd = win32gui.GetForegroundWindow()
        
        # Connect pywinauto to the window using its handle and the "uia" backend
        app = pywinauto.Desktop(backend="uia").window(handle=hwnd)
        
        # The address bar in modern browsers is often an "Edit" control named "Address and search bar".
        # We'll search for this specific combination and wait up to 3 seconds.
        url_bar = app.child_window(title="Address and search bar", control_type="Edit").wait('ready', timeout=2)
        
        # .get_value() is the method to read the text from the control
        url = url_bar.get_value()

        if url:
            return url

    except (pywinauto.findwindows.ElementNotFoundError, pywinauto.timings.TimeoutError):
        # This is the expected "error" if the window is not a browser or the element isn't found.
        # We fail silently and return None.
        return None
    except Exception:
        # Catch any other unexpected errors (e.g., window closed during check)
        return None
    
    return None

# --- Main Data Collection Logic ---
def get_active_window_data():
    """Gets app name, title, and URL."""
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd: return None, None, None
        
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid == 0: return None, None, None
            
        process_name = psutil.Process(pid).name()
        window_title = win32gui.GetWindowText(hwnd)
        
        if not window_title: return None, None, None
        
        # Call our new function to get the URL
        url = get_url_from_browser()
            
        return process_name, window_title, url
    except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
        return None, None, None

# --- Main Script Execution ---
def main():
    print("--- Title and URL Collector (pywinauto version) ---")
    print(f"Capturing active window data every {CAPTURE_INTERVAL_SECONDS} seconds.")
    print(f"Data will be saved to '{OUTPUT_FILENAME}'.")
    print("Use your computer normally. Press Ctrl+C to stop.")

    seen_data = set()
    
    if os.path.exists(OUTPUT_FILENAME):
        with open(OUTPUT_FILENAME, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            # Skip header, then load existing data to avoid duplicates
            try:
                next(reader, None) 
                for row in reader:
                    seen_data.add(tuple(row))
            except Exception:
                pass # Handle case where file is empty except for header
        print(f"Loaded {len(seen_data)} existing records to avoid duplication.")

    try:
        with open(OUTPUT_FILENAME, 'a', newline='', encoding='utf-8') as csv_file:
            writer = csv.writer(csv_file)
            if not seen_data and os.path.getsize(OUTPUT_FILENAME) == 0:
                writer.writerow(['app_name', 'window_title', 'url'])
            
            while True:
                time.sleep(CAPTURE_INTERVAL_SECONDS)
                
                app, title, url = get_active_window_data()
                
                if app and title:
                    url_to_store = url if url else ""
                    data_tuple = (app, title, url_to_store)
                    
                    if data_tuple not in seen_data:
                        writer.writerow(list(data_tuple))
                        csv_file.flush()
                        seen_data.add(data_tuple)
                        if url:
                             print(f"[{time.strftime('%H:%M:%S')}] Captured URL: {url}")
                        else:
                             print(f"[{time.strftime('%H:%M:%S')}] Captured App: {title}")
                        
    except KeyboardInterrupt:
        print("\n--- Capture Stopped ---")
        print(f"Total unique records in '{OUTPUT_FILENAME}': {len(seen_data)}")
    except Exception as e:
        print(f"\nAn error occurred: {e}")

if __name__ == "__main__":
    main()