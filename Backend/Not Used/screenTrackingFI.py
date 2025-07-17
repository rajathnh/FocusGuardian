# window_monitor_module_adapted.py
# ADAPTED: Uses multiprocessing.Queue and multiprocessing.Event
# best until now
# Last update: 11/06/2025 , 19:43 PM

import time
import platform
import subprocess
import sys
# ADAPTED: Import multiprocessing
import multiprocessing
import queue # Standard queue module (multiprocessing.Queue inherits/uses its exceptions like Empty)

try:
    import psutil
except ImportError:
    print("Warning: psutil library not found. Functionality may be limited. Install using: pip install psutil", file=sys.stderr)
    psutil = None

# --- WindowMonitor Class ---

class WindowMonitor:
    def __init__(self, interval_seconds=3):
        self.interval_seconds = interval_seconds
        # ADAPTED: Removed self._is_running and self._stop_event initialization here.
        # The stop_event is passed in, and loop control relies on it.
        self.current_os = platform.system()
        self._last_app_name = None
        self._last_window_title = None
        self.latest_app = "Initializing" # For standalone test display
        self.latest_title = ""         # For standalone test display

        print(f"WindowMonitor: Initialized for OS: {self.current_os}", file=sys.stderr)
        self._check_dependencies()

    def _check_dependencies(self):
        print("WindowMonitor: Checking dependencies...", file=sys.stderr)
        if self.current_os == "Windows":
            try:
                import win32gui
                import win32process
                print("WindowMonitor: pywin32 found.", file=sys.stderr)
            except ImportError:
                print("Warning: WindowMonitor: pywin32 not found. Install using 'pip install pywin32'. Window tracking on Windows will fail.", file=sys.stderr)
        elif self.current_os == "Darwin": # macOS
            try:
                 result = subprocess.run(['which', 'osascript'], capture_output=True, text=True, check=True)
                 print(f"WindowMonitor: 'osascript' found at {result.stdout.strip()}.", file=sys.stderr)
            except (subprocess.CalledProcessError, FileNotFoundError):
                 print("Warning: WindowMonitor: 'osascript' command not found or not executable. Window tracking on macOS will fail.", file=sys.stderr)
        elif self.current_os == "Linux":
            tools_missing = []
            try: subprocess.run(['which', 'xdotool'], check=True, capture_output=True)
            except (subprocess.CalledProcessError, FileNotFoundError): tools_missing.append('xdotool')
            try: subprocess.run(['which', 'xprop'], check=True, capture_output=True)
            except (subprocess.CalledProcessError, FileNotFoundError): tools_missing.append('xprop')

            if tools_missing:
                print(f"Warning: WindowMonitor: Required tools not found: {', '.join(tools_missing)}. "
                      "Install them (e.g., 'sudo apt install xdotool xprop'). "
                      "Window tracking on Linux/X11 will likely fail.", file=sys.stderr)
            else:
                 print("WindowMonitor: 'xdotool' and 'xprop' found.", file=sys.stderr)
            import os
            if os.environ.get('WAYLAND_DISPLAY'):
                print("Warning: WindowMonitor: Wayland detected. Accurate window tracking might be limited "
                      "as standard X11 tools (xdotool, xprop) may not work correctly.", file=sys.stderr)
        else:
            print(f"Warning: WindowMonitor: Unsupported OS ({self.current_os}). Window tracking is disabled.", file=sys.stderr)

    # --- Platform Specific Getters (Largely unchanged, prints to stderr) ---
    def _get_active_window_windows(self):
        try:
            import win32gui
            import win32process
        except ImportError:
            return "Error", "pywin32 missing"
        process_name = "Unknown"; window_title = ""
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd: return None, None
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid == 0: process_name = "System Process"
            elif psutil:
                try: process = psutil.Process(pid); process_name = process.name()
                except (psutil.NoSuchProcess, psutil.AccessDenied): process_name = "Unknown/Restricted"
                except Exception as e_psutil: print(f"WindowMonitor: psutil error for PID {pid}: {e_psutil}", file=sys.stderr); process_name = "Error getting name"
            window_title = win32gui.GetWindowText(hwnd)
            return process_name, window_title
        except SystemError: return None, None
        except Exception as e: print(f"WM_DEBUG Windows: {e}", file=sys.stderr); return "Error", str(e)

    def _get_active_window_macos(self):
        app_name = "Unknown"; window_title = ""
        try:
            script = '''
            on getFrontmostAppInfo()
                try
                    tell application "System Events"
                        set frontAppProcess to first application process whose frontmost is true
                        if frontAppProcess is null then return {"", ""}
                        set frontAppName to name of frontAppProcess
                        try
                            set frontWindow to front window of frontAppProcess
                            set frontWindowTitle to name of frontWindow
                            if frontWindowTitle is missing value then set frontWindowTitle to ""
                            return {frontAppName, frontWindowTitle}
                        on error errMsg number errNum
                            return {frontAppName, ""}
                        end try
                    end tell
                on error errMsg number errNum
                     return {"Error", "Accessibility Access?"}
                end try
            end getFrontmostAppInfo
            getFrontmostAppInfo()'''
            result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, check=False, timeout=2)
            if result.returncode != 0:
                 stderr_output = result.stderr.strip()
                 if "osascript: command not found" in stderr_output: return "Error", "osascript missing"
                 elif "access" in stderr_output.lower() or "not allowed" in stderr_output.lower(): return "Error", "Accessibility Permissions Required"
                 else: err_msg = stderr_output.split('\n')[0] if stderr_output else f"Return Code {result.returncode}"; return "Error", err_msg[:100]
            output = result.stdout.strip()
            if output.startswith('{') and output.endswith('}') and ',' in output:
                parts = output[1:-1].split(',', 1); app_name_raw = parts[0].strip(); window_title_raw = parts[1].strip()
                app_name = app_name_raw.strip('"'); window_title = window_title_raw.strip('"')
                if window_title.lower() == "missing value": window_title = ""
            elif output: app_name = output.strip('"{')
            return app_name, window_title
        except subprocess.TimeoutExpired: print("WindowMonitor: osascript command timed out (macOS).", file=sys.stderr); return "Error", "osascript timeout"
        except Exception as e: print(f"WM_DEBUG macOS: {e}", file=sys.stderr); return "Error", f"Unexpected: {str(e)[:50]}"

    def _get_active_window_linux_x11(self):
        try:
            active_window_id = subprocess.check_output(['xdotool', 'getactivewindow'], text=True, timeout=1).strip()
            if not active_window_id or not active_window_id.isdigit(): return "Desktop/Panel", ""
            window_title = "Unknown Title"
            try:
                title_prop_output = subprocess.check_output(['xprop', '-id', active_window_id, '_NET_WM_NAME'], text=True, stderr=subprocess.DEVNULL, timeout=1).strip()
                if '"' in title_prop_output: window_title = title_prop_output.split('"', 1)[1].rsplit('"', 1)[0]
                else: raise subprocess.CalledProcessError(1, "xprop")
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                try:
                    title_prop_output = subprocess.check_output(['xprop', '-id', active_window_id, 'WM_NAME'], text=True, stderr=subprocess.DEVNULL, timeout=1).strip()
                    if '"' in title_prop_output: window_title = title_prop_output.split('"', 1)[1].rsplit('"', 1)[0]
                except: pass
            app_name = "Unknown App"
            try:
                class_prop_output = subprocess.check_output(['xprop', '-id', active_window_id, 'WM_CLASS'], text=True, stderr=subprocess.DEVNULL, timeout=1).strip()
                if '"' in class_prop_output:
                    parts = [p for p in class_prop_output.split('"') if p.strip() and p != ', '];
                    if len(parts) >= 1: app_name = parts[-1]
                else: app_name = class_prop_output.split("=")[-1].strip()
            except: pass
            if psutil:
                 try:
                      pid_str = subprocess.check_output(['xdotool', 'getwindowpid', active_window_id], text=True, stderr=subprocess.DEVNULL, timeout=1).strip()
                      if pid_str.isdigit():
                           process = psutil.Process(int(pid_str)); pname = process.name()
                           if app_name == "Unknown App" or app_name.islower(): app_name = pname
                 except: pass
            return app_name, window_title
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            if isinstance(e, FileNotFoundError): err_msg = f"{e.filename} not found"; print(f"WindowMonitor: {err_msg}", file=sys.stderr)
            elif isinstance(e, subprocess.TimeoutExpired): err_msg = f"{e.cmd} timed out"
            else: err_msg = f"Command failed: {' '.join(e.cmd)}"
            return "Error", err_msg
        except Exception as e: print(f"WM_DEBUG Linux: {e}", file=sys.stderr); return "Error", f"Unexpected: {str(e)[:50]}"

    # --- Main Running Loop ---
    # ADAPTED: run method signature changed for multiprocessing.
    # ADAPTED: Uses passed 'stop_event' for loop control.
    # ADAPTED: Sends data to 'output_queue' with consistent 'source' key.
    def run(self, output_queue: multiprocessing.Queue, stop_event: multiprocessing.Event):
        print(f"WindowMonitor: Run loop starting (OS: {self.current_os}, Interval: {self.interval_seconds}s).", file=sys.stderr)
        self._last_app_name = None
        self._last_window_title = None

        # ADAPTED: Main loop condition relies on the passed stop_event
        while not stop_event.is_set():
            app_name, window_title = None, None
            error_message = None
            current_timestamp = time.time() # Get timestamp once per cycle

            try:
                if self.current_os == "Windows":
                    app_name, window_title = self._get_active_window_windows()
                elif self.current_os == "Darwin":
                    app_name, window_title = self._get_active_window_macos()
                elif self.current_os == "Linux":
                    app_name, window_title = self._get_active_window_linux_x11()
                else:
                    error_message = f"Unsupported OS: {self.current_os}"
                    # ADAPTED: If OS is unsupported, send error and break (stop_event will be set by parent)
                    # No need to call self.stop() here as lifecycle is managed externally.
                    
                if app_name == "Error": # Specific error from getter
                    error_message = f"Failed getting window info: {window_title}"
                    app_name, window_title = None, None # Reset for processing

            except Exception as e:
                error_message = f"Unexpected error in window getter: {e}"
                print(f"WindowMonitor: {error_message}", file=sys.stderr)
                app_name, window_title = None, None # Reset

            # --- Process result and send to queue ---
            if error_message:
                output_data = {
                    'source': 'screen_tracker',
                    'type': 'error',
                    'timestamp': current_timestamp,
                    'message': error_message
                }
                print(f"WindowMonitor: Reporting error: {error_message}", file=sys.stderr)
                if self.current_os not in ["Windows", "Darwin", "Linux"]: # For unsupported OS, stop trying
                    try: output_queue.put_nowait(output_data)
                    except Exception as q_err: print(f"WindowMonitor: Could not put error on queue: {q_err}", file=sys.stderr)
                    break # Exit loop for unsupported OS

            else: # No major error, process activity
                current_app_name = app_name if app_name is not None else "Unknown"
                current_window_title = window_title if window_title is not None else ""

                self.latest_app = current_app_name   # For standalone test display
                self.latest_title = current_window_title # For standalone test display

                if current_app_name != self._last_app_name or current_window_title != self._last_window_title:
                    output_data = {
                        'source': 'screen_tracker', # ADAPTED: Consistent 'source' key
                        'timestamp': current_timestamp,
                        'app_name': current_app_name,
                        'window_title': current_window_title,
                    }
                    try:
                        # Use put_nowait to avoid blocking if the main process is slow,
                        # though for live data, some small blocking might be acceptable.
                        output_queue.put_nowait(output_data)
                    except queue.Full:
                        print("WindowMonitor Warning: Output queue is full. Data may be lost.", file=sys.stderr)
                    except Exception as q_err:
                         print(f"WindowMonitor Error: Could not put activity data on queue: {q_err}", file=sys.stderr)
                    
                    self._last_app_name = current_app_name
                    self._last_window_title = current_window_title

            # ADAPTED: Use stop_event.wait() for interruptible sleep
            # wait returns True if the event was set during the timeout, False if timeout elapsed.
            if stop_event.wait(self.interval_seconds):
                break # Event was set, exit loop

        self._cleanup()
        print("WindowMonitor: Run loop finished.", file=sys.stderr)

    # ADAPTED: Stop method is now mainly for external direct calls if needed (e.g., from test harness),
    # but primary stop is via the stop_event set by the parent process.
    # This method becomes less critical for the integrated lifecycle.
    def stop(self):
        print("WindowMonitor: Stop method called (external signal, primary stop is via event).", file=sys.stderr)
        # The main loop control is via the stop_event passed to run().
        # This explicit stop method might not be directly used by the integrator if it solely relies on the event.

    def _cleanup(self):
        print("WindowMonitor: Cleaning up...", file=sys.stderr)
        # No specific resources like webcam or files to close in this module.
        print("WindowMonitor: Cleanup complete.", file=sys.stderr)


# --- ADAPTED Standalone Test (using multiprocessing.Process) ---
if __name__ == "__main__":
    print("Running Window Monitor (Adapted) in standalone test mode (using multiprocessing)...", file=sys.stderr)
    
    # ADAPTED: Use multiprocessing.Queue and multiprocessing.Event
    test_output_queue = multiprocessing.Queue()
    test_stop_event = multiprocessing.Event()

    monitor_instance = WindowMonitor(interval_seconds=2) # Shorter interval for testing
    
    # ADAPTED: Run the monitor in a separate process
    monitor_process = multiprocessing.Process(
        target=monitor_instance.run, 
        args=(test_output_queue, test_stop_event),
        daemon=True # Process will terminate if main program exits
    )
    
    print("Main_Test: Starting monitor process...", file=sys.stderr)
    monitor_process.start()

    last_data_print_time = time.time()
    last_known_app = "Initializing"
    last_known_title = ""

    try:
        while monitor_process.is_alive() or not test_output_queue.empty():
            latest_data = None
            try:
                # Drain queue to get the most recent item if multiple are there
                while not test_output_queue.empty(): # Check before get_nowait
                    latest_data = test_output_queue.get_nowait() # Can raise queue.Empty
            except queue.Empty: # Handles queue.Empty from get_nowait
                pass 

            current_time = time.time()

            if latest_data:
                ts_str = time.strftime('%H:%M:%S', time.localtime(latest_data.get('timestamp', current_time)))
                source = latest_data.get('source', 'N/A')
                msg_type = latest_data.get('type')
                
                if msg_type == 'error':
                    print(f"TESTER @ {ts_str}: ERROR from {source}: {latest_data.get('message', 'No details')}", file=sys.stderr)
                else: # 'activity' data from screen_tracker
                    app = latest_data.get('app_name', 'N/A')
                    title = latest_data.get('window_title', 'N/A')
                    print(f"TESTER @ {ts_str}: From {source} - App: \"{app}\", Title: \"{title}\"")
                    last_known_app = app
                    last_known_title = title
                last_data_print_time = current_time # Reset timer on new data

            # Print status periodically if no new data received (process still alive)
            elif monitor_process.is_alive() and (current_time - last_data_print_time > 5): # Check every 5s if idle
                 print(f"TESTER @ {time.strftime('%H:%M:%S')}: Monitor alive. Last known - App: \"{last_known_app}\", Title: \"{last_known_title}\"", file=sys.stderr)
                 last_data_print_time = current_time


            if not monitor_process.is_alive() and test_output_queue.empty():
                print("Main_Test: Monitor process stopped and queue is empty. Exiting test loop.", file=sys.stderr)
                break
            
            time.sleep(0.1) # Main test loop polling interval

    except KeyboardInterrupt:
        print("\nMain_Test: Standalone test interrupted by user (Ctrl+C).", file=sys.stderr)
    finally:
        print("Main_Test: Initiating shutdown sequence...", file=sys.stderr)
        if monitor_process.is_alive():
            print("Main_Test: Setting stop event for monitor process.", file=sys.stderr)
            test_stop_event.set()
            print("Main_Test: Waiting for monitor process to join (timeout 5s)...", file=sys.stderr)
            monitor_process.join(timeout=5)
            if monitor_process.is_alive():
                print("Main_Test: Monitor process did not join in time, terminating.", file=sys.stderr)
                monitor_process.terminate()
                monitor_process.join()
        
        print(f"Main_Test: Monitor process {'alive' if monitor_process.is_alive() else 'stopped'}.", file=sys.stderr)
        
        final_items_count = 0; last_item_from_q = None
        print("Main_Test: Draining any remaining items from queue...", file=sys.stderr)
        try:
            while not test_output_queue.empty(): 
                last_item_from_q = test_output_queue.get_nowait(); final_items_count += 1
        except queue.Empty: pass
        if last_item_from_q: print(f"Main_Test: Last item from queue: {last_item_from_q}", file=sys.stderr)
        if final_items_count > 0: print(f"Main_Test: Drained {final_items_count} item(s) from queue.", file=sys.stderr)
        
        print("Main_Test: Standalone test finished.", file=sys.stderr)