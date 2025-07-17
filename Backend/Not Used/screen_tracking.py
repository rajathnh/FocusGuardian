# window_monitor_module.py
# Refactored active window tracker designed to be run in a separate thread.

import time
import platform
import subprocess
import sys
import threading
import queue # Expecting a queue for output

try:
    import psutil # Used on Windows and potentially Linux for better process names
except ImportError:
    print("Warning: psutil library not found. Functionality may be limited. Install using: pip install psutil")
    psutil = None # Define it as None to check existence later

# --- WindowMonitor Class ---

class WindowMonitor:
    def __init__(self, interval_seconds=3):
        """
        Initializes the WindowMonitor.

        Args:
            interval_seconds (int): How often to check for the active window.
        """
        self.interval_seconds = interval_seconds
        self._is_running = False
        self._stop_event = threading.Event()
        self.current_os = platform.system()
        self._last_app_name = None
        self._last_window_title = None
        self.latest_app = "Initializing"
        self.latest_title = ""

        print(f"WindowMonitor: Initialized for OS: {self.current_os}")
        self._check_dependencies()

    def _check_dependencies(self):
        """Checks for OS-specific dependencies needed for tracking."""
        print("WindowMonitor: Checking dependencies...")
        if self.current_os == "Windows":
            try:
                import win32gui
                import win32process
                print("WindowMonitor: pywin32 found.")
            except ImportError:
                print("Warning: WindowMonitor: pywin32 not found. Install using 'pip install pywin32'. Window tracking on Windows will fail.")
        elif self.current_os == "Darwin": # macOS
            try:
                 # Check if osascript exists and is executable
                 result = subprocess.run(['which', 'osascript'], capture_output=True, text=True, check=True)
                 print(f"WindowMonitor: 'osascript' found at {result.stdout.strip()}.")
            except (subprocess.CalledProcessError, FileNotFoundError):
                 print("Warning: WindowMonitor: 'osascript' command not found or not executable. Window tracking on macOS will fail.")
        elif self.current_os == "Linux":
            tools_missing = []
            try: subprocess.run(['which', 'xdotool'], check=True, capture_output=True)
            except (subprocess.CalledProcessError, FileNotFoundError): tools_missing.append('xdotool')
            try: subprocess.run(['which', 'xprop'], check=True, capture_output=True)
            except (subprocess.CalledProcessError, FileNotFoundError): tools_missing.append('xprop')

            if tools_missing:
                print(f"Warning: WindowMonitor: Required tools not found: {', '.join(tools_missing)}. "
                      "Install them (e.g., 'sudo apt install xdotool xprop'). "
                      "Window tracking on Linux/X11 will likely fail.")
            else:
                 print("WindowMonitor: 'xdotool' and 'xprop' found.")

            # Simple Wayland check (not foolproof)
            import os
            if os.environ.get('WAYLAND_DISPLAY'):
                print("Warning: WindowMonitor: Wayland detected. Accurate window tracking might be limited "
                      "as standard X11 tools (xdotool, xprop) may not work correctly.")
        else:
            print(f"Warning: WindowMonitor: Unsupported OS ({self.current_os}). Window tracking is disabled.")


    # --- Platform Specific Getters ---

    def _get_active_window_windows(self):
        """Gets active window title and process name on Windows."""
        try:
            import win32gui
            import win32process
        except ImportError:
            return "Error", "pywin32 missing"

        process_name = "Unknown"
        window_title = ""
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None, None # No foreground window or desktop focused

            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid == 0: # Some system processes might have PID 0 or access denied early
                 process_name = "System Process" # Or classify differently
            elif psutil: # Use psutil if available
                try:
                    process = psutil.Process(pid)
                    process_name = process.name()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    process_name = "Unknown/Restricted" # Handle permission errors
                except Exception as e_psutil:
                     print(f"WindowMonitor: psutil error for PID {pid}: {e_psutil}")
                     process_name = "Error getting name"
            # else: No psutil fallback - could try GetModuleFileNameEx, but less reliable

            window_title = win32gui.GetWindowText(hwnd)
            return process_name, window_title

        except SystemError as e: # Catches specific errors like "GetWindowThreadProcessId failed" sometimes seen
             # print(f"WindowMonitor: SystemError getting window info on Windows: {e}")
             return None, None # Treat as unable to get info
        except Exception as e:
            # print(f"WindowMonitor: Error getting window info on Windows: {e}")
            return "Error", str(e) # Report generic errors


    def _get_active_window_macos(self):
        """Gets active app name and window title on macOS using AppleScript."""
        app_name = "Unknown"
        window_title = ""
        try:
            # Improved script with error handling for no front window
            script = '''
            on getFrontmostAppInfo()
                try
                    tell application "System Events"
                        set frontAppProcess to first application process whose frontmost is true
                        if frontAppProcess is null then return {"", ""}
                        set frontAppName to name of frontAppProcess
                        try
                            # This part can fail if the app has no windows or focus issues
                            set frontWindow to front window of frontAppProcess
                            set frontWindowTitle to name of frontWindow
                            if frontWindowTitle is missing value then set frontWindowTitle to ""
                            return {frontAppName, frontWindowTitle}
                        on error errMsg number errNum
                            # If getting window failed, return just the app name
                            # Ignore errors like -1728 (no such element, i.e., no window)
                            # Or -1701 (some object not found, privilege error possible)
                            # Careful logging might be needed here for specific error numbers
                            return {frontAppName, ""}
                        end try
                    end tell
                on error errMsg number errNum
                     # If getting front App failed entirely
                     # Usually permissions problem (Accessibility access)
                     return {"Error", "Accessibility Access?"}
                end try
            end getFrontmostAppInfo
            getFrontmostAppInfo()
            '''
            # timeout added to prevent hangs if script fails
            result = subprocess.run(['osascript', '-e', script],
                                    capture_output=True, text=True, check=False, timeout=2)

            if result.returncode != 0:
                 stderr_output = result.stderr.strip()
                 if "osascript: command not found" in stderr_output:
                       return "Error", "osascript missing"
                 # Basic check for permissions error (may need refinement)
                 elif "access" in stderr_output.lower() or "not allowed" in stderr_output.lower():
                     return "Error", "Accessibility Permissions Required"
                 else:
                      # Other error, return the stderr message if short enough
                      err_msg = stderr_output.split('\n')[0] if stderr_output else f"Return Code {result.returncode}"
                      return "Error", err_msg[:100] # Truncate long messages


            output = result.stdout.strip()
            # Example output: {"Safari", "Google Search"} or {"Terminal", ""}
            if output.startswith('{') and output.endswith('}') and ',' in output:
                parts = output[1:-1].split(',', 1)
                app_name_raw = parts[0].strip()
                window_title_raw = parts[1].strip()

                # Clean potential quoting
                app_name = app_name_raw.strip('"')
                window_title = window_title_raw.strip('"')
                # Handle {"AppName", missing value} case -> Title is empty string
                if window_title.lower() == "missing value":
                    window_title = ""

            elif output: # Unexpected format? Log or handle as best possible
                # print(f"WindowMonitor: Unexpected AppleScript output: {output}")
                # Try to treat it as just the app name if no comma
                app_name = output.strip('"{')


            # Special case: Finder might not report a window title
            if app_name == "Finder" and not window_title:
                 pass # Title might genuinely be empty

            # Filter out "Desktop" activity maybe? This is subjective.
            # if app_name == "Finder" and "Desktop" in window_title: return None, None

            return app_name, window_title

        except subprocess.TimeoutExpired:
             print("WindowMonitor: osascript command timed out (macOS).")
             return "Error", "osascript timeout"
        except Exception as e:
            # print(f"WindowMonitor: Unexpected error getting window info on macOS: {e}")
            return "Error", f"Unexpected: {str(e)[:50]}"

    def _get_active_window_linux_x11(self):
        """Gets active window title and class on Linux (X11) using xdotool and xprop."""
        try:
            # Get active window ID using xdotool
            active_window_id = subprocess.check_output(
                ['xdotool', 'getactivewindow'], text=True, timeout=1
            ).strip()
            if not active_window_id or not active_window_id.isdigit():
                 # Could happen if desktop/panel is focused without a distinct window ID
                 return "Desktop/Panel", "" # Classify this explicitly

            # Get window title (_NET_WM_NAME or WM_NAME) using xprop
            window_title = "Unknown Title"
            try:
                # Prefer _NET_WM_NAME as it usually handles UTF-8 better
                title_prop_output = subprocess.check_output(
                    ['xprop', '-id', active_window_id, '_NET_WM_NAME'],
                    text=True, stderr=subprocess.DEVNULL, timeout=1 # Hide stderr if prop not found
                ).strip()
                # Example: _NET_WM_NAME(UTF8_STRING) = "Window Title Here"
                if '"' in title_prop_output:
                    window_title = title_prop_output.split('"', 1)[1].rsplit('"', 1)[0]
                else:
                    # If format is unexpected, try WM_NAME fallback
                    raise subprocess.CalledProcessError(1, "xprop") # Simulate error to go to except block

            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                try:
                    # Fallback to older WM_NAME
                    title_prop_output = subprocess.check_output(
                        ['xprop', '-id', active_window_id, 'WM_NAME'],
                         text=True, stderr=subprocess.DEVNULL, timeout=1
                    ).strip()
                    if '"' in title_prop_output:
                         window_title = title_prop_output.split('"', 1)[1].rsplit('"', 1)[0]
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                     pass # Keep "Unknown Title" if both fail

            # Get window class (WM_CLASS) using xprop
            app_name = "Unknown App"
            try:
                class_prop_output = subprocess.check_output(
                    ['xprop', '-id', active_window_id, 'WM_CLASS'],
                     text=True, stderr=subprocess.DEVNULL, timeout=1
                ).strip()
                # Example: WM_CLASS(STRING) = "navigator", "Firefox"
                if '"' in class_prop_output:
                    # Often the second part (instance name) is more specific/useful
                    # parts = class_prop_output.split('"') # -> ['', 'navigator', ', ', 'Firefox', '']
                    parts = [p for p in class_prop_output.split('"') if p.strip() and p != ', ']
                    if len(parts) >= 1:
                       app_name = parts[-1] # Take the last quoted string (often the class)
                else: # Handle format like: WM_CLASS(STRING) = Plank
                      app_name = class_prop_output.split("=")[-1].strip()

            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass # Keep "Unknown App"

            # --- Alternative: Try getting PID and using psutil (if available) ---
            # This might give a better process name in some cases.
            if psutil:
                 try:
                      pid_str = subprocess.check_output(
                           ['xdotool', 'getwindowpid', active_window_id],
                           text=True, stderr=subprocess.DEVNULL, timeout=1
                           ).strip()
                      if pid_str.isdigit():
                           pid = int(pid_str)
                           process = psutil.Process(pid)
                           pname = process.name()
                           # Only override if psutil gave a seemingly better name
                           # Simple check: if xprop result is generic, use psutil's
                           if app_name == "Unknown App" or app_name.islower(): # Heuristic
                                app_name = pname
                 except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                         psutil.NoSuchProcess, psutil.AccessDenied):
                      pass # Ignore errors here, stick with xprop result

            return app_name, window_title

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            # FileNotFoundError if xdotool/xprop aren't installed
            if isinstance(e, FileNotFoundError):
                err_msg = f"{e.filename} not found"
                print(f"WindowMonitor: {err_msg}") # Print this critical error
            elif isinstance(e, subprocess.TimeoutExpired):
                err_msg = f"{e.cmd} timed out"
            else:
                err_msg = f"Command failed: {' '.join(e.cmd)}"
            return "Error", err_msg
        except Exception as e:
            # print(f"WindowMonitor: Unexpected error getting window info on Linux: {e}")
            return "Error", f"Unexpected: {str(e)[:50]}"

    # --- Main Running Loop ---

    def run(self, output_queue: queue.Queue):
        """
        Starts the window monitoring loop. Periodically checks the active window,
        detects changes, and puts the information on the output queue.

        Args:
            output_queue (queue.Queue): Queue to send the results to.
                                        Format: {'type': 'activity', 'timestamp': float,
                                                 'app_name': str, 'window_title': str}
                                        or {'type': 'error', 'source': 'window', 'message': str}
        """
        print(f"WindowMonitor: Run loop starting (OS: {self.current_os}, Interval: {self.interval_seconds}s).")
        self._is_running = True
        self._stop_event.clear()
        self._last_app_name = None # Reset state on start
        self._last_window_title = None

        while self._is_running and not self._stop_event.is_set():
            # --- Get platform-specific window info ---
            app_name, window_title = None, None
            error_reported = False
            try:
                if self.current_os == "Windows":
                    app_name, window_title = self._get_active_window_windows()
                elif self.current_os == "Darwin": # macOS
                    app_name, window_title = self._get_active_window_macos()
                elif self.current_os == "Linux":
                    app_name, window_title = self._get_active_window_linux_x11()
                    # Basic check for Wayland where X11 tools might fail often
                    # Add specific handling/warning for Wayland if get_active returns None often?
                else:
                    msg = f"Unsupported OS: {self.current_os}"
                    output_queue.put({'type': 'error', 'source': 'window', 'message': msg})
                    print(f"WindowMonitor: {msg}")
                    error_reported = True
                    self.stop() # Stop the thread if OS is not supported
                    break

                # Handle explicit "Error" return values from getters
                if app_name == "Error":
                     msg = f"Failed getting window info: {window_title}"
                     output_queue.put({'type': 'error', 'source': 'window', 'message': msg})
                     print(f"WindowMonitor: {msg}") # Print locally too
                     # Reset to prevent logging the same error repeatedly
                     app_name, window_title = None, None
                     error_reported = True # Flag that an error was reported this cycle


            except Exception as e:
                msg = f"Unexpected error in window getter: {e}"
                try: output_queue.put({'type': 'error', 'source': 'window', 'message': msg})
                except Exception as q_err: print(f"WindowMonitor: Could not put error on queue: {q_err}")
                print(f"WindowMonitor: {msg}")
                # Reset to avoid processing invalid data
                app_name, window_title = None, None
                error_reported = True

            # --- Process result and send if changed ---
            if not error_reported:
                # Normalize Nones for comparison and storage
                # Treat failure to get info (None) as "Unknown", empty title
                current_app_name = app_name if app_name is not None else "Unknown"
                current_window_title = window_title if window_title is not None else ""

                self.latest_app = current_app_name
                self.latest_title = current_window_title

                # Check if the activity has *meaningfully* changed
                # Only send update if App Name or Window Title changed
                if current_app_name != self._last_app_name or current_window_title != self._last_window_title:
                    timestamp = time.time()
                    output_data = {
                        'type': 'activity',
                        'timestamp': timestamp,
                        'app_name': current_app_name,
                        'window_title': current_window_title,
                    }
                    try:
                        output_queue.put(output_data)
                    except Exception as q_err:
                         print(f"WindowMonitor: Could not put activity data on queue: {q_err}")


                    # print(f"WM Debug: Change Detected: App='{current_app_name}', Title='{current_window_title}'") # Debug Print

                    # Update last known state *after* sending the change
                    self._last_app_name = current_app_name
                    self._last_window_title = current_window_title

            # --- Wait for next interval or stop signal ---
            # Use stop_event.wait() for interruptible sleep
            stopped = self._stop_event.wait(self.interval_seconds)
            if stopped: # If wait() returned True, it was set externally
                break

        # --- Cleanup after loop exits ---
        self._cleanup()
        print("WindowMonitor: Run loop finished.")


    def stop(self):
        """Signals the run loop to stop."""
        print("WindowMonitor: Stop requested.")
        self._is_running = False
        self._stop_event.set() # This will interrupt the wait() in the run loop

    def _cleanup(self):
        """Performs cleanup (currently minimal for this class)."""
        print("WindowMonitor: Cleaning up...")
        # No specific resources like webcam or files to close here,
        # but this is where you'd add such cleanup if needed later.
        print("WindowMonitor: Cleanup complete.")


# --- Standalone Test (Optional) ---
if __name__ == "__main__":
    print("Running Window Monitor in standalone test mode...")
    test_queue = queue.Queue()
    monitor = WindowMonitor(interval_seconds=3)

    # Run the monitor in a separate thread for testing
    test_thread = threading.Thread(target=monitor.run, args=(test_queue,), daemon=True)
    test_thread.start()

    last_print_time = 0
    try:
        while test_thread.is_alive():
            try:
                data = test_queue.get(timeout=0.1)
                print(f"Received from monitor: {data}")
                last_print_time = time.time()
            except queue.Empty:
                # Print current status periodically if no change detected for a while
                if time.time() - last_print_time > 10:
                     print(f"Monitor Idle. Latest: App='{monitor.latest_app}', Title='{monitor.latest_title}'")
                     last_print_time = time.time() # Reset timer
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nStandalone test interrupted. Stopping monitor...")
        monitor.stop()
        test_thread.join(timeout=5)
        print("Monitor stopped by test harness.")
    finally:
        # Ensure cleanup if loop exited unexpectedly
        if test_thread.is_alive():
             print("Forcing final stop...")
             monitor.stop()
             test_thread.join(timeout=2)
        print("Standalone test finished.")