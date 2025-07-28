# In: local_engine/run_local_analysis.py

import requests # To make API calls
import time
import sys
import json
import argparse
import multiprocessing
import queue

# --- IMPORTANT: Import your original, local analysis modules ---
from fd6 import FocusDetector
from screen_recorder_with_ocr import WindowMonitor
from productivity_classifier import ProductivityClassifier
from service_extractor import ServiceExtractor

# --- Configuration ---
API_BASE_URL = "http://localhost:5000" # Change to your deployed backend URL in production
ANALYSIS_INTERVAL_SECONDS = 5 # This MUST match the `timeIncrement` in your Node.js backend

def analysis_loop(session_id, jwt_token, stop_event):
    """The main loop that collects, analyzes, and sends data."""
    print("--- Local Analysis Engine Started ---")
    print(f"Targeting Session ID: {session_id}")
    print("Initializing local AI models...")

    try:
        # Initialize your local AI/data components
        productivity_classifier = ProductivityClassifier()
        service_extractor = ServiceExtractor()
        #print("PYTHON_ENGINE_READY", flush=True)
    except Exception as e:
        print(f"FATAL: Failed to initialize core models: {e}", file=sys.stderr)
        print("PYTHON_ENGINE_FAILED", flush=True)
        return

    # Setup and start background data collectors (from your original ProductivityManager.py)
    data_queue = multiprocessing.Queue()
    focus_detector = FocusDetector(show_window=False) # Keep the window hidden for this
    window_monitor = WindowMonitor(interval_seconds=ANALYSIS_INTERVAL_SECONDS)

    fd_process = multiprocessing.Process(target=focus_detector.run, args=(data_queue, stop_event))
    wm_process = multiprocessing.Process(target=window_monitor.run, args=(data_queue, stop_event))

    processes = [fd_process, wm_process]
    for p in processes:
        p.start()
    #print("--- Main script pausing for 25 seconds to allow children to initialize... ---")
    #time.sleep(25)
    print("PYTHON_ENGINE_READY", flush=True)

    print("--- Background data collectors are running. Starting main analysis loop. ---")
    latest_focus_data = {}

    
    while not stop_event.is_set():
        try:
            # This logic is almost identical to your original main loop
            data = data_queue.get(timeout=1.0)
            
            if data.get('source') == 'focus_detector':
                latest_focus_data = data
            
            elif data.get('source') == 'screen_tracker':
                if not latest_focus_data:
                    continue # Wait until we have face data

                # --- Run Local AI Pipeline ---
                app = data.get('app_name', 'N/A')
                title = data.get('window_title', '')
                url = data.get('url', '')
                
                service_name = service_extractor.predict(app, title, url)
                productivity_label = productivity_classifier.predict(latest_focus_data, data)
                
                # --- Prepare the JSON payload for the Node.js backend ---
                payload = {
                    "focus": True if productivity_label == "Productive" else False,
                    "appName": service_name,
                    "activity": latest_focus_data.get('reason', 'N/A') or productivity_label
                }
                
                print(f"Analyzed: {json.dumps(payload)}")

                # --- Send the data to the Node.js Backend ---
                try:
                    headers = {
                        "Authorization": f"Bearer {jwt_token}",
                        "Content-Type": "application/json"
                    }
                    api_url = f"{API_BASE_URL}/api/sessions/data/{session_id}"
                    
                    response = requests.post(api_url, headers=headers, json=payload, timeout=10)

                    if response.status_code == 200:
                        print("--> Data point sent successfully.")
                    elif response.status_code == 404:
                        # The server is telling us this session is no longer active.
                        # This happens if the user stopped it from the UI.
                        print("\n!!! SERVER REPORTED SESSION NOT FOUND (404). SHUTTING DOWN LOCAL ENGINE. !!!\n")
                        stop_event.set() # This will gracefully stop the while loop and all child processes.
                    else:
                        # Handle other potential server errors
                        print(f"!! Server Error: {response.status_code} - {response.text} !!")

                except requests.exceptions.RequestException as e:
                    print(f"!! Network Error: Could not connect to server. {e} !!")

        except queue.Empty:
            # Check if background processes are still alive
            if not all(p.is_alive() for p in processes):
                print("!! A background data collector has stopped. Shutting down. !!", file=sys.stderr)
                stop_event.set()
            continue
        except Exception as e:
            print(f"An unexpected error occurred in the main loop: {e}", file=sys.stderr)


    # Cleanup
    print("--- Analysis loop stopped. Cleaning up background processes... ---")
    for p in processes:
        p.join(timeout=5)
        if p.is_alive():
            p.terminate()
    print("--- Local Analysis Engine Finished ---")


if __name__ == '__main__':
    # This allows us to run the script from the command line
    # Example: python run_local_analysis.py --session <session_id> --token <jwt_token>
    multiprocessing.freeze_support() # Important for PyInstaller/packaged apps

    parser = argparse.ArgumentParser(description="Focus Guardian Local Analysis Engine")
    parser.add_argument("--session", required=True, help="The session ID to send data to.")
    parser.add_argument("--token", required=True, help="The user's JWT authentication token.")
    args = parser.parse_args()

    stop_event = multiprocessing.Event()
    
    try:
        analysis_loop(args.session, args.token, stop_event)
    except KeyboardInterrupt:
        print("\n--- User interrupted. Shutting down... ---")
        stop_event.set()