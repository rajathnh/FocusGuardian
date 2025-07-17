# screen_tracker_with_ocr.py (Version 2 - More Robust)
# MERGED: Combines robust window tracking with screenshot and OCR.
# FIX: Uses a single, reliable method (win32gui) to get window info and geometry.

import time, platform, sys, multiprocessing, queue
# --- MERGED IMPORTS ---
try:
    import psutil
    import pyautogui
    import pytesseract
    from PIL import Image
    # This is the key new import for the fix
    import win32gui, win32process
except ImportError:
    print("Error: Missing required libraries. Run:", file=sys.stderr)
    print("pip install psutil pyautogui pytesseract Pillow pywin32", file=sys.stderr)
    sys.exit(1)

# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

class WindowMonitor:
    def __init__(self, interval_seconds=5):
        self.interval_seconds = interval_seconds
        self.current_os = platform.system()
        if self.current_os != "Windows":
            print("Warning: This robust version is optimized for Windows. Other OS may have limited functionality.", file=sys.stderr)

    # --- THE NEW, UNIFIED METHOD FOR WINDOWS ---
    def _get_active_window_data_windows(self):
        """Gets app name, title, AND geometry using the reliable win32gui method."""
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd: return "Unknown", "No Foreground Window", None

            # Get App Name and Title
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process_name = psutil.Process(pid).name() if psutil and pid != 0 else "System Process"
            window_title = win32gui.GetWindowText(hwnd)

            # Get Geometry
            rect = win32gui.GetWindowRect(hwnd)
            x = rect[0]
            y = rect[1]
            w = rect[2] - x
            h = rect[3] - y
            
            # Check for invalid states (e.g., minimized window)
            if w <= 0 or h <= 0:
                return process_name, window_title, None

            return process_name, window_title, (x, y, w, h)
        except Exception as e:
            # This can happen if the window closes while we're inspecting it
            # print(f"WM Error (_get_active_window_data_windows): {e}", file=sys.stderr)
            return "Unknown", "Error getting window data", None

    def _perform_ocr(self, region):
        """Performs OCR on a specific region of the screen."""
        if not region: return "[No Valid Window Region]"
        try:
            screenshot = pyautogui.screenshot(region=region)
            raw_text = pytesseract.image_to_string(screenshot, timeout=2.5)
            # We'll return the raw text and let the consumer handle cleaning if needed
            return raw_text if raw_text.strip() else "[No Text Detected]"
        except Exception as e:
            # print(f"WM Error (OCR): {e}", file=sys.stderr)
            return "[OCR FAILED]"

    # --- THE NEW, ROBUST `run` METHOD ---
    def run(self, output_queue: multiprocessing.Queue, stop_event: multiprocessing.Event):
        print(f"WM: Window Monitor process started (Interval: {self.interval_seconds}s).", file=sys.stderr)

        while not stop_event.is_set():
            app_name, window_title, region = "Unknown", "", None

            if self.current_os == "Windows":
                app_name, window_title, region = self._get_active_window_data_windows()
            else:
                app_name, window_title = "Unsupported OS", ""
                # Could add a pyautogui fallback for other OSes here if needed
            
            ocr_text = self._perform_ocr(region)
            
            output_data = {
                'source': 'screen_tracker',
                'timestamp': time.time(),
                'app_name': app_name,
                'window_title': window_title,
                'screen_content_ocr': ocr_text,
            }
            try:
                output_queue.put_nowait(output_data)
            except queue.Full:
                print("WM Warning: Output queue is full.", file=sys.stderr)
            
            if stop_event.wait(self.interval_seconds):
                break
        print("WM: Window Monitor process finished.", file=sys.stderr)

# --- Standalone Test Block (Unchanged but will now work correctly) ---
if __name__ == '__main__':
    # ... (The __main__ block can stay exactly as it was) ...
    print("Running Merged Screen Tracker in standalone test mode...")
    test_q = multiprocessing.Queue()
    stop_ev = multiprocessing.Event()
    monitor = WindowMonitor(interval_seconds=5)
    monitor_process = multiprocessing.Process(target=monitor.run, args=(test_q, stop_ev))
    monitor_process.start()
    print("Test running. Switch to the window you want to OCR.")
    try:
        time.sleep(20)
    finally:
        print("\nStopping process...")
        stop_ev.set()
        monitor_process.join(5)
        print("\n--- Data Collected ---")
        while not test_q.empty():
            data = test_q.get()
            print(f"\nTimestamp: {time.strftime('%H:%M:%S', time.localtime(data['timestamp']))}")
            print(f"App: {data['app_name']}, Title: {data['window_title']}")
            ocr_preview = data['screen_content_ocr'].replace('\n', ' ').strip()
            print(f"OCR Content (first 100 chars): '{ocr_preview[:100]}...'")
        print("\n--- Test Finished ---")