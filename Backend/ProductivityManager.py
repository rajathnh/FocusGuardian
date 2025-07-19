# ProductivityManager.py (Final - Subprocess Analytics)
# This is the main application entry point.
# It runs data collectors, AI models, the database logger, and the Flask API.
# Analytics are handled by launching analytics_engine.py as a separate process.

import multiprocessing
import time
import sys
import queue
import threading
from flask import Flask, jsonify
import subprocess # For running external scripts
import json       # For parsing the output from the analytics script

# Import your custom modules
from fd6 import FocusDetector
from screen_recorder_with_ocr import WindowMonitor
from productivity_classifier import ProductivityClassifier
from service_extractor import ServiceExtractor
from database_manager import DatabaseManager
# NOTE: AnalyticsEngine is NO LONGER imported here.

# --- Configuration ---
ANALYSIS_INTERVAL_SECONDS = 5 # How often the screen tracker runs and triggers an analysis

# --- Flask API & Session State Setup ---
app = Flask(__name__)
state = {
    "session_id": None,
    "is_session_active": False,
    "latest_status": {
        "timestamp": None,
        "service": "Initializing",
        "emotion": "N/A",
        "productivity": "Unknown"
    }
}
state_lock = threading.Lock()

@app.route('/api/status')
def get_status():
    """Provides the latest real-time status to the frontend."""
    with state_lock:
        return jsonify(state["latest_status"])

@app.route('/api/session/start', methods=['POST'])
def start_session():
    """Starts a new logging session."""
    with state_lock:
        state["session_id"] = f"session_{int(time.time())}"
        state["is_session_active"] = True
        print(f"API: Session '{state['session_id']}' started.")
    return jsonify({"status": "session_started", "session_id": state["session_id"]})

@app.route('/api/session/end', methods=['POST'])
def end_session():
    """Ends the current logging session."""
    ended_session_id = None
    with state_lock:
        if state["is_session_active"]:
            ended_session_id = state["session_id"]
            state["session_id"] = None
            state["is_session_active"] = False
            print(f"API: Session '{ended_session_id}' ended.")
    return jsonify({"status": "session_ended", "session_id": ended_session_id})

# --- NEW, ROBUST API ENDPOINT FOR SUMMARY ---
@app.route('/api/session/summary/<session_id>')
def get_session_summary(session_id):
    """
    Launches the analytics engine as a separate process to calculate and return the summary.
    This is the most robust way to avoid database locking issues.
    """
    print(f"API: Received request for summary of session '{session_id}'")
    try:
        # We find the python executable of our current virtual environment to ensure
        # the subprocess has the same dependencies (like pandas).
        python_executable = sys.executable

        # Construct the command to run the analytics script
        command = [python_executable, "analytics_engine.py", session_id]

        # Run the command and capture its output
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
        
        # The output of the script is a JSON string, so we parse it
        summary_data = json.loads(result.stdout)
        
        return jsonify(summary_data)

    except subprocess.CalledProcessError as e:
        print(f"API Error: Analytics script failed with error:\n{e.stderr}", file=sys.stderr)
        return jsonify({"error": "Analytics script failed.", "details": e.stderr}), 500
    except json.JSONDecodeError:
        print(f"API Error: Could not decode JSON from analytics script's output.", file=sys.stderr)
        return jsonify({"error": "Failed to parse analytics data."}), 500
    except Exception as e:
        print(f"API Error: An unexpected error occurred during summary generation: {e}", file=sys.stderr)
        return jsonify({"error": "An internal server error occurred."}), 500

# --- Main Application Logic ---
def main_application_loop(stop_event):
    print("CORE: Main application loop starting.")
    
    # Initialize core AI and DB components
    try:
        productivity_classifier = ProductivityClassifier()
        service_extractor = ServiceExtractor()
        db_manager = DatabaseManager()
    except Exception as e:
        print(f"FATAL: Failed to initialize core components: {e}", file=sys.stderr)
        stop_event.set()
        return

    # Setup and start background data collector processes
    data_queue = multiprocessing.Queue()
    focus_detector = FocusDetector(show_window=False)
    window_monitor = WindowMonitor(interval_seconds=ANALYSIS_INTERVAL_SECONDS)
    
    fd_process = multiprocessing.Process(target=focus_detector.run, args=(data_queue, stop_event), name="FocusDetector")
    wm_process = multiprocessing.Process(target=window_monitor.run, args=(data_queue, stop_event), name="WindowMonitor")
    processes = [fd_process, wm_process]
    for p in processes:
        p.start()
    print("CORE: Background processes for face and screen tracking have been started.")

    # The Main Analysis Loop
    latest_focus_data = {}
    
    while not stop_event.is_set():
        try:
            data = data_queue.get(timeout=1.0)
            
            if data.get('source') == 'focus_detector':
                latest_focus_data = data
            elif data.get('source') == 'screen_tracker':
                if not latest_focus_data: continue
                
                # --- AI Pipeline ---
                app = data.get('app_name', 'N/A')
                title = data.get('window_title', '')
                url = data.get('url', '')
                
                service_name = service_extractor.predict(app, title, url)
                productivity_label = productivity_classifier.predict(latest_focus_data, data)

                # --- Data Logging and Display ---
                ts_str = time.strftime('%H:%M:%S')
                emotion = latest_focus_data.get('emotion', 'N/A')

                with state_lock:
                    session_is_active = state["is_session_active"]
                    active_session_id = state["session_id"]

                log_status = "(Not Logging)"
                if session_is_active:
                    log_packet = {
                        'timestamp': data.get('timestamp'), 'session_id': active_session_id,
                        'focus_status': latest_focus_data.get('status'), 'focus_reason': latest_focus_data.get('reason'),
                        'emotion': emotion, 'app_name': app, 'window_title': title,
                        'ocr_content': data.get('screen_content_ocr'), 'service_name': service_name,
                        'productivity_label': productivity_label
                    }
                    db_manager.log_activity(log_packet)
                    log_status = "(Logged)"

                with state_lock:
                    state["latest_status"].update({
                        "timestamp": ts_str, "service": service_name,
                        "emotion": emotion, "productivity": productivity_label
                    })

                print(f"[{ts_str}] Service: {service_name:<25} | Emotion: {emotion:<10} | PRODUCTIVITY: {productivity_label} {log_status}")

        except queue.Empty:
            if not all(p.is_alive() for p in processes):
                print("CORE Error: A background process has stopped. Shutting down.", file=sys.stderr)
                stop_event.set()
            continue

    # Cleanup after the loop ends
    print("CORE: Shutting down background processes...", file=sys.stderr)
    for p in processes:
        p.join(timeout=5)
    if db_manager:
        db_manager.close()

# --- Main Entry Point ---
if __name__ == "__main__":
    multiprocessing.freeze_support()
    stop_event = multiprocessing.Event()
    
    print("--- Focus Guardian Backend Service ---")
    
    flask_thread = threading.Thread(target=lambda: app.run(host='127.0.0.1', port=5000), daemon=True)
    flask_thread.start()
    print("API: Flask server started on http://127.0.0.1:5000")

    try:
        main_application_loop(stop_event)
    except KeyboardInterrupt:
        print("\nCORE: User interrupt detected. Initiating shutdown.")
    finally:
        stop_event.set()
        print("CORE: Application stopped.")