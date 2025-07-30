# In: Backend/run_local_analysis.py (Complete, Corrected, Final Version)

import requests, time, sys, json, argparse, multiprocessing, queue, warnings
from fd6 import run_focus_detector_process # Import the wrapper function
from screen_recorder_with_ocr import run_window_monitor_process # Import the wrapper function
from productivity_classifier import ProductivityClassifier
from service_extractor import ServiceExtractor

# Silence harmless warnings to clean up logs
warnings.filterwarnings("ignore", category=UserWarning, message="SymbolDatabase.GetPrototype() is deprecated.")

API_BASE_URL = "http://localhost:5000"
ANALYSIS_INTERVAL_SECONDS = 5

def analysis_loop(session_id, jwt_token, stop_event):
    print("--- Local Analysis Engine Started ---")
    print(f"Targeting Session ID: {session_id}")
    try:
        print("Initializing main AI models...")
        productivity_classifier = ProductivityClassifier()
        service_extractor = ServiceExtractor()
    except Exception as e:
        print(f"FATAL: Failed to initialize core models: {e}", file=sys.stderr)
        print("PYTHON_ENGINE_FAILED", flush=True)
        return

    data_queue = multiprocessing.Queue()
    handshake_queue = multiprocessing.Queue()

    # --- THIS IS THE FIX ---
    # We target the wrapper functions, not the classes directly.
    fd_process = multiprocessing.Process(target=run_focus_detector_process, args=(data_queue, stop_event, handshake_queue))
    wm_process = multiprocessing.Process(target=run_window_monitor_process, args=(ANALYSIS_INTERVAL_SECONDS, data_queue, stop_event, handshake_queue))
    
    processes = [fd_process, wm_process]
    for p in processes:
        p.start()

    print("--- Main script is now waiting for child processes to confirm they are ready... ---")
    expected_ready_signals = {"fd_ready", "wm_ready"}
    try:
        for _ in range(len(expected_ready_signals)):
            signal = handshake_queue.get(timeout=90)
            if signal in expected_ready_signals:
                print(f"--- CONFIRMATION RECEIVED: {signal} ---")
                expected_ready_signals.remove(signal)
        
        if not expected_ready_signals:
            print("--- Both child processes are ready. Engine is now fully operational. ---")
            print("PYTHON_ENGINE_READY", flush=True)
        else:
            raise Exception("Did not receive all ready signals from child processes.")
    except (queue.Empty, Exception) as e:
        print(f"FATAL: A data collector process failed to start in time. {e}", file=sys.stderr)
        print("PYTHON_ENGINE_FAILED", flush=True)
        stop_event.set()

    print("--- Starting main analysis loop. ---")
    latest_focus_data = {}
    
    while not stop_event.is_set():
        try:
            data = data_queue.get(timeout=1.0)
            if data.get('source') == 'focus_detector':
                latest_focus_data = data
            elif data.get('source') == 'screen_tracker':
                if not latest_focus_data: continue
                app = data.get('app_name', 'N/A')
                title = data.get('window_title', '')
                url = data.get('url', '')
                service_name = service_extractor.predict(app, title, url)
                productivity_label = productivity_classifier.predict(latest_focus_data, data)
                payload = {"focus": True if productivity_label == "Productive" else False, "appName": service_name, "activity": latest_focus_data.get('reason', 'N/A') or productivity_label}
                try:
                    headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}
                    api_url = f"{API_BASE_URL}/api/sessions/data/{session_id}"
                    response = requests.post(api_url, headers=headers, json=payload, timeout=10)
                    if response.status_code == 404:
                        stop_event.set()
                except requests.exceptions.RequestException: pass
        except queue.Empty:
            if not all(p.is_alive() for p in processes): stop_event.set()
            continue
        except Exception: pass

    print("--- Analysis loop stopped. Cleaning up... ---")
    try:
        for p in processes:
            if p.is_alive(): p.terminate()
            p.join(timeout=3)
    except Exception: pass
    print("--- Local Analysis Engine Finished ---")

if __name__ == '__main__':
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description="Focus Guardian Local Analysis Engine")
    parser.add_argument("--session", required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()
    stop_event = multiprocessing.Event()
    try:
        analysis_loop(args.session, args.token, stop_event)
    except KeyboardInterrupt:
        stop_event.set()