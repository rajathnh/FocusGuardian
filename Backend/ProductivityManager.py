# ProductivityManager.py
# The final backend service: runs collectors, AI model, database logging, and an API.

import multiprocessing
import time
import sys
import queue
import threading
from flask import Flask, jsonify

# Import your custom modules
from fd6 import FocusDetector
from screen_recorder_with_ocr import WindowMonitor
from productivity_classifier import ProductivityClassifier
from database_manager import DatabaseManager

# --- Configuration ---
ANALYSIS_INTERVAL_SECONDS = 5 # How often to analyze and log the user's state

# --- Helper Function for Title Parsing ---
def parse_window_title(app_name, window_title):
    app_name = app_name.lower()
    if "chrome.exe" in app_name or "firefox.exe" in app_name or "msedge.exe" in app_name:
        parts = window_title.split(' - ')
        if len(parts) > 1: return " - ".join(parts[:-1]).strip()
    if "code.exe" in app_name:
        parts = window_title.split(' - ')
        if len(parts) > 1: return parts[0].strip()
    return window_title

# --- Flask API Setup ---
app = Flask(__name__)
# A simple thread-safe way to hold the latest state for the API
latest_app_state = {}
state_lock = threading.Lock()

@app.route('/api/status')
def get_status():
    with state_lock:
        return jsonify(latest_app_state)

# --- Main Application Logic ---
def main_application_loop(stop_event):
    print("CORE: Main application loop started.")
    
    # 1. Initialize core components
    try:
        classifier = ProductivityClassifier()
        db_manager = DatabaseManager()
    except Exception as e:
        print(f"FATAL: Failed to initialize core components: {e}", file=sys.stderr)
        stop_event.set()
        return

    # 2. Setup and start background processes
    data_queue = multiprocessing.Queue()
    focus_detector = FocusDetector(show_window=False)
    window_monitor = WindowMonitor(interval_seconds=ANALYSIS_INTERVAL_SECONDS)
    
    fd_process = multiprocessing.Process(target=focus_detector.run, args=(data_queue, stop_event), name="FocusDetector")
    wm_process = multiprocessing.Process(target=window_monitor.run, args=(data_queue, stop_event), name="WindowMonitor")
    processes = [fd_process, wm_process]
    for p in processes:
        p.start()

    # 3. The Main Analysis Loop
    latest_focus_data = {}
    latest_screen_data = {}
    
    while not stop_event.is_set():
        try:
            data = data_queue.get(timeout=1.0)
            
            if data.get('source') == 'focus_detector':
                latest_focus_data = data
            elif data.get('source') == 'screen_tracker':
                latest_screen_data = data
                
                if latest_focus_data and latest_screen_data:
                    # Run AI prediction
                    productivity_label = classifier.predict(latest_focus_data, latest_screen_data)
                    
                    # Prepare data packet for logging and API
                    ts = time.strftime('%H:%M:%S')
                    app = latest_screen_data.get('app_name', 'N/A')
                    title = latest_screen_data.get('window_title', '')
                    specific_detail = parse_window_title(app, title)
                    emotion = latest_focus_data.get('emotion', 'N/A')
                    
                    # Log to database
                    log_packet = {
                        'timestamp': latest_screen_data.get('timestamp'),
                        'focus_status': latest_focus_data.get('status'),
                        'focus_reason': latest_focus_data.get('reason'),
                        'emotion': emotion,
                        'app_name': app,
                        'window_title': title,
                        'ocr_content': latest_screen_data.get('screen_content_ocr'),
                        'productivity_label': productivity_label
                    }
                    db_manager.log_activity(log_packet)
                    
                    # Update state for the API
                    with state_lock:
                        latest_app_state.update({
                            "timestamp": ts,
                            "detail": specific_detail,
                            "emotion": emotion,
                            "productivity": productivity_label
                        })

                    # Print to console
                    print(f"[{ts}] Detail: {specific_detail:<40} | Emotion: {emotion:<10} | PRODUCTIVITY: {productivity_label} (Logged)")

        except queue.Empty:
            if not all(p.is_alive() for p in processes):
                print("CORE Error: A background process has stopped. Shutting down.", file=sys.stderr)
                stop_event.set()
            continue

    # Cleanup after the loop ends
    print("CORE: Shutting down background processes...", file=sys.stderr)
    for p in processes:
        p.join(timeout=5)
    db_manager.close()

# --- Main Entry Point ---
if __name__ == "__main__":
    multiprocessing.freeze_support()
    stop_event = multiprocessing.Event()
    
    print("--- Focus Guardian Backend Service ---")
    
    # Start the Flask server in a separate thread
    flask_thread = threading.Thread(target=lambda: app.run(host='127.0.0.1', port=5000), daemon=True)
    flask_thread.start()
    print("API: Flask server started on http://127.0.0.1:5000")

    try:
        # Run the main application loop in the main thread
        main_application_loop(stop_event)
    except KeyboardInterrupt:
        print("\nCORE: User interrupt detected. Initiating shutdown.")
    finally:
        stop_event.set()
        print("CORE: Application stopped.")