# In: Backend/run_local_analysis.py (Corrected and Final Version)

import requests
import time
import sys
import json
import argparse
import multiprocessing
import queue

# Your Project's Modules
from fd6 import FocusDetector
from screen_recorder_with_ocr import WindowMonitor
from productivity_classifier import ProductivityClassifier
from service_extractor import ServiceExtractor

API_BASE_URL = "http://localhost:5000" # Ensure this port is correct
ANALYSIS_INTERVAL_SECONDS = 5

def analysis_loop(session_id, jwt_token, stop_event, ready_event):
    """The main analysis loop."""
    print("--- Starting main analysis loop. ---", flush=True)
    
    # Setup data queue for collectors
    data_queue = multiprocessing.Queue()

    # --- THIS IS THE FIX ---
    # We create INSTANCES of the classes first.
    focus_detector = FocusDetector(show_window=False)
    window_monitor = WindowMonitor(interval_seconds=ANALYSIS_INTERVAL_SECONDS)

    # Then we start processes with the instance's `run` method as the target.
    # The `args` tuple is for the `run` method, NOT the `__init__` method.
    fd_process = multiprocessing.Process(target=focus_detector.run, args=(data_queue, stop_event))
    wm_process = multiprocessing.Process(target=window_monitor.run, args=(data_queue, stop_event))
    # --- END OF FIX ---

    processes = [fd_process, wm_process]
    for p in processes:
        p.start()

    # --- Robust Readiness Check ---
    # We give the child processes a moment to start up and initialize.
    time.sleep(10) # Wait for camera and models to load
    
    # Check if they are still alive after the startup period.
    if not fd_process.is_alive() or not wm_process.is_alive():
        print("FATAL: A data collector process failed to start in time.", file=sys.stderr, flush=True)
        ready_event.set() # Signal main script that we failed
        return # Exit this function

    # If they are alive, we are ready to go.
    print("--- Data collectors are running. ---", flush=True)
    ready_event.set() # Signal main script that we are ready!

    latest_focus_data = {}
    while not stop_event.is_set():
        try:
            data = data_queue.get(timeout=1.0)
            
            if data.get('source') == 'focus_detector':
                latest_focus_data = data
            elif data.get('source') == 'screen_tracker':
                if not latest_focus_data:
                    continue
                
                # --- This is your AI pipeline from the original script ---
                # It's being moved inside this function.
                app = data.get('app_name', 'N/A')
                title = data.get('window_title', '')
                url = data.get('url', '')
                
                # We need to initialize the classifiers here, within the context
                # where they will be used.
                # NOTE: This assumes classifiers are lightweight to init. If they are heavy,
                # they should be passed as arguments. For now, this is safer.
                productivity_classifier = ProductivityClassifier()
                service_extractor = ServiceExtractor()

                service_name = service_extractor.predict(app, title, url)
                productivity_label = productivity_classifier.predict(latest_focus_data, data)
                
                is_focused = True if productivity_label == "Productive" else False
                activity_reason = latest_focus_data.get('reason', '') or productivity_label
                
                payload = {
                    "focus": is_focused,
                    "appName": service_name,
                    "activity": activity_reason
                }
                print(f"Analyzed: {json.dumps(payload)}", flush=True)

                # --- API Call Logic (Unchanged) ---
                try:
                    headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}
                    api_url = f"{API_BASE_URL}/api/sessions/data/{session_id}"
                    response = requests.post(api_url, headers=headers, json=payload, timeout=10)
                    if response.status_code == 404:
                        print("!!! SERVER SESSION ENDED. Stopping local monitoring. !!!", flush=True)
                        stop_event.set()
                    elif response.status_code != 200:
                        print(f"!! Server Error: {response.status_code} - {response.text} !!", flush=True)
                except requests.exceptions.RequestException:
                    print(f"!! NETWORK ERROR !!", flush=True)

        except queue.Empty:
            if not all(p.is_alive() for p in processes):
                print("!! A background process died. Shutting down. !!", file=sys.stderr, flush=True)
                stop_event.set()
            continue
    
    # Cleanup
    print("--- Analysis loop stopped. Cleaning up... ---", flush=True)
    for p in processes:
        if p.is_alive():
            p.terminate()
        p.join(timeout=3)

if __name__ == '__main__':
    if sys.platform.startswith('win'):
        multiprocessing.freeze_support()

    parser = argparse.ArgumentParser(description="Focus Guardian Local Analysis Engine")
    parser.add_argument("--session", required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()

    stop_event = multiprocessing.Event()
    ready_event = multiprocessing.Event() # For handshake

    try:
        print("--- Local Analysis Engine Started ---", flush=True)
        print(f"Targeting Session ID: {args.session}", flush=True)
        print("Initializing main AI models...", flush=True)
        
        # We start the main analysis loop in its own process so the main script
        # can wait for the 'ready' signal.
        main_process = multiprocessing.Process(target=analysis_loop, args=(args.session, args.token, stop_event, ready_event))
        main_process.start()
        
        print("--- Main script is now waiting for child processes to confirm they are ready... ---", flush=True)
        
        # Wait for the ready signal from the analysis_loop
        ready_event.wait(timeout=60) # Wait up to 60 seconds

        if ready_event.is_set():
             # Check if the main process is still alive. If it died, it means it failed.
            if main_process.is_alive():
                print("PYTHON_ENGINE_READY", flush=True)
            else:
                # The process started, set the event, but then crashed.
                print("PYTHON_ENGINE_FAILED", flush=True)
        else:
            # We timed out waiting for the ready signal.
            print("PYTHON_ENGINE_FAILED", flush=True)
            print("FATAL: Timed out waiting for data collectors to become ready.", file=sys.stderr, flush=True)
            if main_process.is_alive():
                main_process.terminate()

        # Keep the main script alive while the analysis process is running
        if main_process.is_alive():
            main_process.join()

    except KeyboardInterrupt:
        print("\n--- User interruption detected. Shutting down... ---", flush=True)
    finally:
        stop_event.set()

    print("--- Local Analysis Engine Finished ---", flush=True)