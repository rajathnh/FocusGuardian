# data_recorder.py
# The "Conductor" script to run both modules and record data for labeling.

import multiprocessing
import time
import sys
import queue
import csv
import os

# Import the classes from your working modules
from fd6 import FocusDetector
from screen_recorder_with_ocr import WindowMonitor # Use the new, robust version

# --- Configuration ---
DATA_COLLECTION_INTERVAL_SECONDS = 5 # How often to save a combined data point. 10s is good to avoid too much data.
CSV_FILENAME = "raw_productivity_data.csv"

def main():
    print("--- Data Recorder Starting ---")

    # 1. Create shared resources for multiprocessing
    data_queue = multiprocessing.Queue()
    stop_event = multiprocessing.Event()

    # 2. Instantiate the modules
    # Focus detector runs fast. The WindowMonitor's interval will be our trigger.
    focus_detector = FocusDetector(show_window=True)
    window_monitor = WindowMonitor(interval_seconds=DATA_COLLECTION_INTERVAL_SECONDS)

    # 3. Create the processes
    fd_process = multiprocessing.Process(
        target=focus_detector.run,
        args=(data_queue, stop_event),
        name="FocusDetectorProcess"
    )

    wm_process = multiprocessing.Process(
        target=window_monitor.run,
        args=(data_queue, stop_event),
        name="WindowMonitorProcess"
    )

    processes = [fd_process, wm_process]

    # 4. Prepare the CSV file for appending data
    file_exists = os.path.isfile(CSV_FILENAME)
    # Use 'a' for append mode.
    with open(CSV_FILENAME, 'a', newline='', encoding='utf-8') as csv_file:
        # Define the columns. This order will be used for the CSV header.
        fieldnames = ['timestamp', 'focus_status', 'focus_reason', 'emotion', 'app_name', 'window_title', 'ocr_content']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        
        if not file_exists:
            writer.writeheader()
            print(f"Created new data file: {CSV_FILENAME}")
        else:
            print(f"Appending to existing data file: {CSV_FILENAME}")

        # 5. Start the processes
        for p in processes:
            p.start()

        # 6. Main loop to listen for data and record it
        latest_focus_data = {}
        latest_screen_data = {}

        print("\nData collection is running. Use your computer normally. Press Ctrl+C in this terminal to stop.")
        try:
            while not stop_event.is_set():
                try:
                    # Block and wait for the next piece of data to arrive
                    data = data_queue.get(timeout=1.0)
                    
                    # Store the latest data from each source
                    if data.get('source') == 'focus_detector':
                        latest_focus_data = data
                    elif data.get('source') == 'screen_tracker':
                        latest_screen_data = data
                        
                        # TRIGGER: A new screen capture is our signal to write a row.
                        if latest_focus_data and latest_screen_data:
                            print(f"[{time.strftime('%H:%M:%S')}] Recording data point for app: {latest_screen_data.get('app_name')}")
                            
                            combined_row = {
                                'timestamp': latest_screen_data.get('timestamp'),
                                'focus_status': latest_focus_data.get('status', 'N/A'),
                                'focus_reason': latest_focus_data.get('reason', ''),
                                'emotion': latest_focus_data.get('emotion', 'N/A'),
                                'app_name': latest_screen_data.get('app_name', 'N/A'),
                                'window_title': latest_screen_data.get('window_title', ''),
                                'ocr_content': latest_screen_data.get('screen_content_ocr', '')
                            }
                            
                            writer.writerow(combined_row)
                            csv_file.flush() # Make sure it's written to disk right away

                except queue.Empty:
                    # Check if a process died unexpectedly
                    if not all(p.is_alive() for p in processes):
                        print("Error: A child process has terminated. Shutting down.", file=sys.stderr)
                        stop_event.set()
                    continue
        
        except KeyboardInterrupt:
            print("\n--- User interrupted. Initiating graceful shutdown... ---", file=sys.stderr)
        
        finally:
            # 7. Graceful shutdown
            print("Setting stop event for all processes.", file=sys.stderr)
            stop_event.set()

            for p in processes:
                print(f"Waiting for {p.name} to join...", file=sys.stderr)
                p.join(timeout=5)

            print(f"--- Data Recorder Shut Down. Data saved to {CSV_FILENAME} ---", file=sys.stderr)

if __name__ == "__main__":
    main()