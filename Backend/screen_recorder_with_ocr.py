# screen_tracker_with_ocr.py (Version 3 - URL Aware)
# MERGED: Combines robust window tracking, OCR, and URL extraction.

import time, platform, sys, multiprocessing, queue
import warnings
warnings.filterwarnings("ignore", message="SymbolDatabase.GetPrototype() is deprecated")
# --- MERGED IMPORTS ---
try:
    import psutil
    import pyautogui
    import pytesseract
    from PIL import Image
    # Windows-specific imports for robust tracking
    import win32gui, win32process
    # NEW: Import for robust URL extraction
    import pywinauto
except ImportError:
    print("Error: Missing required libraries. Run:", file=sys.stderr)
    print("pip install psutil pyautogui pytesseract Pillow pywin32 pywinauto", file=sys.stderr)
    sys.exit(1)

# You might need to set the path to the Tesseract executable
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

class WindowMonitor:
    def __init__(self, interval_seconds=5):
        self.interval_seconds = interval_seconds
        self.current_os = platform.system()
        if self.current_os != "Windows":
            print("Warning: This robust version is optimized for Windows. Other OS may have limited functionality.", file=sys.stderr)

    # --- NEW: URL Extraction Function using pywinauto ---
    def _get_url_from_browser(self):
        """
        Gets the URL from the active tab of Chrome or Edge using pywinauto.
        Returns the URL as a string or None if it fails.
        """
        try:
            hwnd = win32gui.GetForegroundWindow()
            app = pywinauto.Desktop(backend="uia").window(handle=hwnd)
            
            # This is the most reliable target for modern browsers
            url_bar = app.child_window(title="Address and search bar", control_type="Edit").wait('ready', timeout=2)
            url = url_bar.get_value()
            if url:
                return url
        except (pywinauto.findwindows.ElementNotFoundError, pywinauto.timings.TimeoutError, Exception):
            # Fail silently if it's not a browser or the element isn't found
            return None
        return None

    # --- Unified Method for Window Data (App Name, Title, Geometry) ---
    def _get_active_window_data_windows(self):
        """Gets app name, title, AND geometry using the reliable win32gui method."""
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd: return "Unknown", "No Foreground Window", None

            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process_name = psutil.Process(pid).name() if psutil and pid != 0 else "System Process"
            window_title = win32gui.GetWindowText(hwnd)

            rect = win32gui.GetWindowRect(hwnd)
            x, y, w, h = rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]
            
            if w <= 0 or h <= 0: return process_name, window_title, None

            return process_name, window_title, (x, y, w, h)
        except Exception:
            return "Unknown", "Error getting window data", None

    # --- OCR Method (Unchanged) ---
    def _perform_ocr(self, region):
        """Performs OCR on a specific region of the screen."""
        if not region: return "[No Valid Window Region]"
        try:
            screenshot = pyautogui.screenshot(region=region)
            raw_text = pytesseract.image_to_string(screenshot, timeout=2.5)
            return raw_text if raw_text.strip() else "[No Text Detected]"
        except Exception:
            return "[OCR FAILED]"

    # --- THE FINAL, UPGRADED `run` METHOD ---
    def run(self, output_queue: multiprocessing.Queue, stop_event: multiprocessing.Event, handshake_queue: multiprocessing.Queue = None):
        if handshake_queue:
            handshake_queue.put("wm_ready")
        print(f"WM: Window Monitor process started (Interval: {self.interval_seconds}s).", file=sys.stderr)

        while not stop_event.is_set():
            app_name, window_title, region, url = "Unknown", "", None, None

            if self.current_os == "Windows":
                app_name, window_title, region = self._get_active_window_data_windows()
                # Check if the active app is a browser to get the URL
                if app_name.lower() in ["chrome.exe", "msedge.exe", "firefox.exe"]:
                    url = self._get_url_from_browser()
            else:
                app_name, window_title = "Unsupported OS", ""
            
            ocr_text = self._perform_ocr(region)
            
            # Construct the complete data packet
            output_data = {
                'source': 'screen_tracker',
                'timestamp': time.time(),
                'app_name': app_name,
                'window_title': window_title,
                'url': url if url else "", # Ensure URL is an empty string if None
                'screen_content_ocr': ocr_text,
            }

            try:
                output_queue.put_nowait(output_data)
            except queue.Full:
                print("WM Warning: Output queue is full.", file=sys.stderr)
            
            if stop_event.wait(self.interval_seconds):
                break
        print("WM: Window Monitor process finished.", file=sys.stderr)

def run_window_monitor_process(interval_seconds: int, output_queue: 'multiprocessing.Queue', stop_event: 'multiprocessing.Event', handshake_queue: 'multiprocessing.Queue'):
    """This function is the target for the multiprocessing.Process."""
    try:
        monitor = WindowMonitor(interval_seconds=interval_seconds)
        monitor.run(output_queue, stop_event, handshake_queue)
    except Exception as e:
        print(f"WM PROCESS CRASHED: {e}", file=sys.stderr)
# --- Standalone Test Block ---
if __name__ == '__main__':
    print("Running Upgraded Screen Tracker in standalone test mode...")
    test_q = multiprocessing.Queue()
    stop_ev = multiprocessing.Event()
    
    monitor = WindowMonitor(interval_seconds=5)
    monitor_process = multiprocessing.Process(target=monitor.run, args=(test_q, stop_ev))
    
    monitor_process.start()
    
    print("Test running for 20 seconds. Switch to different browser tabs and applications.")
    try:
        time.sleep(20)
    finally:
        print("\nStopping process...")
        stop_ev.set()
        monitor_process.join(5)
        
        print("\n--- Data Collected ---")
        while not test_q.empty():
            data = test_q.get()
            print("\n--------------------")
            print(f"Timestamp: {time.strftime('%H:%M:%S', time.localtime(data['timestamp']))}")
            print(f"App: {data['app_name']}, Title: {data['window_title']}")
            print(f"URL: {data['url']}")
            ocr_preview = data['screen_content_ocr'].replace('\n', ' ').strip()
            print(f"OCR (preview): '{ocr_preview[:80]}...'")
        print("\n--- Test Finished ---")