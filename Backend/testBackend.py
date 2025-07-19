# test_full_backend.py
# A script to perform an end-to-end test of the entire ProductivityManager service.

import requests
import time
import json

# The base URL of our running backend service
BASE_URL = "http://127.0.0.1:5000"

def start_session():
    """Sends a POST request to start a new session."""
    print("--- 1. Starting a new session ---")
    try:
        response = requests.post(f"{BASE_URL}/api/session/start")
        response.raise_for_status() # Raises an exception for bad status codes (4xx or 5xx)
        data = response.json()
        print(f"Backend Response: {data}")
        return data.get("session_id")
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Could not start session. Is the backend running? Error: {e}")
        return None

def end_session():
    """Sends a POST request to end the current session."""
    print("\n--- 3. Ending the session ---")
    try:
        response = requests.post(f"{BASE_URL}/api/session/end")
        response.raise_for_status()
        data = response.json()
        print(f"Backend Response: {data}")
        return data.get("session_id")
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Could not end session: {e}")
        return None

def get_live_status():
    """Sends a GET request to check the latest status."""
    try:
        response = requests.get(f"{BASE_URL}/api/status")
        response.raise_for_status()
        print(f"Live Status Update: {response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Could not get live status: {e}")

def get_session_summary(session_id):
    """Sends a GET request to get the final report for a session."""
    print(f"\n--- 4. Requesting summary for session '{session_id}' ---")
    try:
        response = requests.get(f"{BASE_URL}/api/session/summary/{session_id}")
        response.raise_for_status()
        data = response.json()
        print("\n===== FINAL SESSION REPORT =====")
        # Use json.dumps for pretty printing the JSON response
        print(json.dumps(data, indent=2))
        print("================================")
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Could not get session summary: {e}")


if __name__ == '__main__':
    print("="*50)
    print("   Focus Guardian - Full Backend Test Script")
    print("="*50)
    
    # --- Instructions ---
    print("\nInstructions:")
    print("1. Make sure you have started 'ProductivityManager.py' in a separate terminal.")
    print("2. Wait for it to fully initialize (you should see the 'API server started' message).")
    input("\nPress Enter to begin the test...")
    
    # --- Run the Test Sequence ---
    active_session_id = start_session()
    
    if active_session_id:
        print("\n--- 2. Simulating a 30-second work session ---")
        print("The backend is now logging data. Please switch between a few windows (e.g., your code editor and a browser).")
        
        # We'll check the live status a few times during the session
        for i in range(3):
            time.sleep(10)
            print(f"\nChecking live status ({i+1}/3)...")
            get_live_status()
            
        ended_session_id = end_session()
        
        if ended_session_id:
            # It can take a moment for the last data to be written, so a small wait is good.
            print("\nWaiting 2 seconds for final data to be processed...")
            time.sleep(2)
            get_session_summary(ended_session_id)
        else:
            print("ERROR: Session did not seem to end correctly.")
            
    print("\n--- Test complete ---")