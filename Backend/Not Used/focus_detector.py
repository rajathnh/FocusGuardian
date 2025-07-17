# focus_detector_module.py
# Refactored focus detector designed to be run in a separate thread.

import cv2
import mediapipe as mp
import numpy as np
import math
from collections import deque
import time
from scipy.spatial.transform import Rotation as R
import threading
import queue # Expecting a queue for output

# --- Configuration Constants ---
# Adjust these thresholds based on testing and desired sensitivity
HEAD_YAW_THRESHOLD = 40      # Degrees left/right head turn considered distracted
HEAD_PITCH_THRESHOLD = 40    # Degrees up/down head turn considered distracted (TUNE THIS)
EYE_AR_THRESH = 0.23         # Below this EAR = potential blink/closure
EYE_AR_CONSEC_FRAMES = 3   # Number of consecutive frames below threshold for eyes closed status
HISTORY_BUFFER_SIZE = 30   # Number of frames for calculating distraction % (approx 1-2s)

# --- MediaPipe Initialization (Constants) ---
# These drawing specs are optional if you don't display the window
mp_face_mesh = mp.solutions.face_mesh
mp_drawing = mp.solutions.drawing_utils
drawing_spec = mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=1, circle_radius=1)
connection_drawing_spec = mp_drawing.DrawingSpec(color=(0, 128, 0), thickness=1)

# Landmark indices based on MediaPipe standard face mesh (non-refined)
# You might need to adjust these slightly if you change MediaPipe versions or settings
# Or use named constants provided by MediaPipe if available and clearer
LEFT_EYE_INDICES = [362, 382, 381, 380, 374, 373] # Common non-refined indices
RIGHT_EYE_INDICES = [33, 7, 163, 144, 145, 153]  # Common non-refined indices

# Landmark indices for head pose PnP algorithm
PNP_LANDMARK_INDICES = [
    1,   # Nose tip
    152, # Chin
    33,  # Left eye left corner
    263, # Right eye right corner
    61,  # Left Mouth corner
    291  # Right mouth corner
]

# 3D model points for head pose estimation (average human head model)
PNP_MODEL_POINTS = np.array([
    (0.0, 0.0, 0.0),             # Nose tip
    (0.0, -330.0, -65.0),        # Chin
    (-225.0, 170.0, -135.0),     # Left eye left corner
    (225.0, 170.0, -135.0),      # Right eye right corner
    (-150.0, -150.0, -125.0),    # Left Mouth corner
    (150.0, -150.0, -125.0)      # Right mouth corner
])

# --- Helper Functions ---

def calculate_ear(eye_landmark_coords):
    """Calculates the Eye Aspect Ratio (EAR) for a single eye from coordinates."""
    try:
        # Vertical distances
        A = np.linalg.norm(eye_landmark_coords[1] - eye_landmark_coords[5])
        B = np.linalg.norm(eye_landmark_coords[2] - eye_landmark_coords[4])
        # Horizontal distance
        C = np.linalg.norm(eye_landmark_coords[0] - eye_landmark_coords[3])
        if C == 0: return 0.3 # Avoid division by zero, return reasonable "open" value
        ear = (A + B) / (2.0 * C)
        return ear
    except Exception as e:
        # print(f"Error calculating EAR: {e}") # Optional: Debug logging
        return None

def extract_landmark_coords(facial_landmarks, indices, image_width, image_height):
    """Extracts pixel coordinates for specified landmark indices."""
    if facial_landmarks is None:
        return None
    try:
        coords = np.array([(facial_landmarks.landmark[i].x * image_width,
                            facial_landmarks.landmark[i].y * image_height)
                           for i in indices], dtype=np.float64) # Use float64 for solvePnP
        return coords
    except IndexError:
        # print(f"Warning: Landmark index out of bounds during extraction.") # Optional: Debug logging
        return None
    except Exception as e:
        # print(f"Error extracting landmark coords: {e}") # Optional: Debug logging
        return None

def estimate_head_pose(image_points, image_shape):
    """Estimates head pose (yaw, pitch, roll) using solvePnP."""
    if image_points is None or len(image_points) != len(PNP_MODEL_POINTS):
        return None, None, None, None, None

    image_height, image_width = image_shape[:2]
    focal_length = float(image_width) # Approximate focal length
    center = (image_width / 2.0, image_height / 2.0)

    camera_matrix = np.array([
        [focal_length, 0, center[0]],
        [0, focal_length, center[1]],
        [0, 0, 1]
    ], dtype=np.float64) # Use float64

    dist_coeffs = np.zeros((4, 1)) # Assuming no lens distortion

    try:
        (success, rotation_vector, translation_vector) = cv2.solvePnP(
            PNP_MODEL_POINTS, image_points, camera_matrix, dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE
        )

        if not success:
            return None, None, None, None, None

        # Convert rotation vector to rotation matrix and then Euler angles
        rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
        scipy_r = R.from_matrix(rotation_matrix)
        # Using 'YXZ' order commonly represents yaw, pitch, roll intuitively for head pose
        euler_angles = scipy_r.as_euler('YXZ', degrees=True)

        yaw = euler_angles[0]
        pitch = euler_angles[1]
        roll = euler_angles[2]

        # Optional Yaw Correction: Handle gimbal lock or alternative solution near +/- 180
        # If yaw jumps wildly between positive and negative large values, this can help.
        if abs(yaw) > 160: # Heuristic threshold, adjust if needed
             yaw = yaw - np.sign(yaw) * 180

        return yaw, pitch, roll, rotation_vector, translation_vector

    except cv2.error as e:
        # print(f"OpenCV error in solvePnP: {e}") # Optional: Debug logging
        return None, None, None, None, None
    except Exception as e:
        # print(f"Error estimating head pose: {e}") # Optional: Debug logging
        return None, None, None, None, None


def draw_pose_axis(image, rotation_vector, translation_vector, camera_matrix):
    """Draws the 3D pose axis (X:Blue, Y:Green, Z:Red) on the image."""
    if rotation_vector is None or translation_vector is None:
        return

    axis_length = 75
    axis_points_3d = np.float32([
        [axis_length, 0, 0],    # X-axis end
        [0, axis_length, 0],    # Y-axis end
        [0, 0, -axis_length],   # Z-axis end (negative Z often points outwards)
        [0, 0, 0]               # Origin
    ]).reshape(-1, 3)

    try:
        # Project 3D points to 2D image plane
        image_points_2d, _ = cv2.projectPoints(axis_points_3d, rotation_vector,
                                               translation_vector, camera_matrix,
                                               np.zeros((4, 1))) # No distortion

        # Ensure points are valid tuples of integers
        origin = tuple(np.round(image_points_2d[3].ravel()).astype(int))
        x_axis_end = tuple(np.round(image_points_2d[0].ravel()).astype(int))
        y_axis_end = tuple(np.round(image_points_2d[1].ravel()).astype(int))
        z_axis_end = tuple(np.round(image_points_2d[2].ravel()).astype(int))

        # Draw lines (BGR color format for OpenCV)
        cv2.line(image, origin, x_axis_end, (255, 0, 0), 3) # Blue for X
        cv2.line(image, origin, y_axis_end, (0, 255, 0), 3) # Green for Y
        cv2.line(image, origin, z_axis_end, (0, 0, 255), 3) # Red for Z
    except OverflowError:
        # print("Warning: OverflowError drawing axis (points might be outside view)")
        pass # Ignore if points project way off screen
    except Exception as e:
        # print(f"Error drawing pose axis: {e}") # Optional: Debug logging
        pass


# --- FocusDetector Class ---

class FocusDetector:
    def __init__(self, show_window=False, history_size=HISTORY_BUFFER_SIZE):
        """
        Initializes the FocusDetector.

        Args:
            show_window (bool): Whether to display the OpenCV window with annotations.
            history_size (int): Number of frames used to calculate distraction percentage.
        """
        self.show_window = show_window
        self.history_size = history_size
        self._is_running = False
        self._stop_event = threading.Event()
        self._cap = None
        self._face_mesh = None
        self._distraction_history = deque(maxlen=self.history_size)
        self.latest_status = "Initializing"
        self.latest_percentage = 0.0
        self.latest_reason = ""
        self._frame_counter = 0 # For potential future use (e.g., frame skipping)
        self._eye_closure_counter = 0

    def initialize_resources(self):
        """Initializes webcam and MediaPipe face mesh."""
        print("FocusDetector: Initializing resources...")
        try:
            self._face_mesh = mp_face_mesh.FaceMesh(
                max_num_faces=1,          # Assuming single user
                refine_landmarks=False,   # Use standard landmarks for less computation
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            )
            print("FocusDetector: Face Mesh model loaded.")

            # Check multiple camera indices if 0 fails
            for cam_idx in [0, 1, -1]:
                 self._cap = cv2.VideoCapture(cam_idx)
                 if self._cap and self._cap.isOpened():
                     print(f"FocusDetector: Webcam opened successfully (Index: {cam_idx}).")
                     # Optionally set camera properties (resolution, FPS) if needed
                     # self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                     # self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                     return True
                 if self._cap:
                      self._cap.release() # Release if opened but invalid

            print("Error: FocusDetector: Cannot open any webcam.")
            self._cap = None
            return False

        except Exception as e:
            print(f"Error: FocusDetector: Failed during initialization: {e}")
            self._face_mesh = None
            self._cap = None
            return False

    def _process_frame(self, image):
        """Processes a single frame for face landmarks and pose."""
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        image_height, image_width = image_rgb.shape[:2]

        # Make image non-writeable for potentially faster processing
        image_rgb.flags.writeable = False
        results = self._face_mesh.process(image_rgb)
        image_rgb.flags.writeable = True

        if results.multi_face_landmarks:
            return results.multi_face_landmarks[0], (image_height, image_width)
        else:
            return None, (image_height, image_width)

    def _analyze_landmarks(self, face_landmarks, image_shape):
        """Analyzes landmarks to determine focus status, pose, EAR."""
        image_height, image_width = image_shape

        # Extract landmark coordinates for pose and eyes
        pnp_points_2d = extract_landmark_coords(face_landmarks, PNP_LANDMARK_INDICES, image_width, image_height)
        left_eye_coords = extract_landmark_coords(face_landmarks, LEFT_EYE_INDICES, image_width, image_height)
        right_eye_coords = extract_landmark_coords(face_landmarks, RIGHT_EYE_INDICES, image_width, image_height)

        # Estimate head pose
        yaw, pitch, roll, rvec, tvec = estimate_head_pose(pnp_points_2d, image_shape)

        # Calculate Eye Aspect Ratio
        left_ear = calculate_ear(left_eye_coords) if left_eye_coords is not None else None
        right_ear = calculate_ear(right_eye_coords) if right_eye_coords is not None else None
        ear_avg = (left_ear + right_ear) / 2.0 if left_ear is not None and right_ear is not None else None

        # Rule-based classification
        is_distracted = False
        reasons_list = []

        if yaw is not None and pitch is not None:
            if abs(yaw) > HEAD_YAW_THRESHOLD:
                is_distracted = True
                reasons_list.append("Yaw")
            if abs(pitch) > HEAD_PITCH_THRESHOLD:
                is_distracted = True
                reasons_list.append("Pitch")

        if ear_avg is not None:
            if ear_avg < EYE_AR_THRESH:
                self._eye_closure_counter += 1
            else:
                self._eye_closure_counter = 0 # Reset if eyes are open

            if self._eye_closure_counter >= EYE_AR_CONSEC_FRAMES:
                is_distracted = True
                if "Eyes Closed" not in reasons_list:
                    reasons_list.append("Eyes Closed")
        else:
            # If EAR couldn't be calculated, reset the counter
            self._eye_closure_counter = 0

        # Determine final status and reason string
        if is_distracted:
            status = "Distracted"
            reason = " & ".join(reasons_list) if reasons_list else "Unknown"
            self._distraction_history.append(1)
        else:
            status = "Focused"
            reason = ""
            self._distraction_history.append(0)

        # Calculate distraction percentage
        distraction_perc = 0
        if len(self._distraction_history) > 0:
            distraction_perc = (sum(self._distraction_history) / len(self._distraction_history)) * 100

        return status, reason, distraction_perc, yaw, pitch, roll, ear_avg, rvec, tvec, face_landmarks

    def _update_display(self, image, analysis_result, face_landmarks_mp, cam_matrix):
        """Draws annotations on the image for display."""
        (status, reason, distraction_perc,
         yaw, pitch, _, ear_avg, rvec, tvec, _) = analysis_result

        image_height, image_width = image.shape[:2]

        # Draw face landmarks (optional, can be performance intensive/cluttering)
        # mp_drawing.draw_landmarks(
        #     image=image,
        #     landmark_list=face_landmarks_mp, # Use the direct mediapipe landmark list
        #     connections=mp_face_mesh.FACEMESH_TESSELATION, # TESSELATION or CONTOURS
        #     landmark_drawing_spec=drawing_spec,
        #     connection_drawing_spec=connection_drawing_spec)

        # Draw Pose Axis
        draw_pose_axis(image, rvec, tvec, cam_matrix)

        # Display Status Text
        status_color = (0, 0, 255) if status != "Focused" else (0, 255, 0)
        cv2.putText(image, f"Status: {status}", (30, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, status_color, 2)
        if reason:
            cv2.putText(image, f"Reason: {reason}", (30, 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.putText(image, f"Distraction: {distraction_perc:.1f}%", (30, 110),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

        # Display Debug Info (optional)
        text_y_offset = 50
        if yaw is not None:
            cv2.putText(image, f"Yaw: {yaw:.1f}", (image_width - 180, text_y_offset),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 1)
            text_y_offset += 20
        if pitch is not None:
            cv2.putText(image, f"Pitch: {pitch:.1f}", (image_width - 180, text_y_offset),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 1)
            text_y_offset += 20
        if ear_avg is not None:
            cv2.putText(image, f"EAR: {ear_avg:.2f}", (image_width - 180, text_y_offset),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 1)

        # Show the window
        cv2.imshow('Focus Detector', image)


    def run(self, output_queue: queue.Queue):
        """
        Starts the focus detection loop. Reads frames, analyzes, puts results
        on the output queue, and optionally displays the window.

        Args:
            output_queue (queue.Queue): Queue to send the results to.
                                        Format: {'type': 'focus', 'timestamp': float,
                                                 'status': str, 'percentage': float,
                                                 'reason': str}
                                        or {'type': 'error', 'source': 'focus', 'message': str}
        """
        if not self.initialize_resources():
            print("FocusDetector: Exiting run loop due to initialization failure.")
            try:
                output_queue.put({'type': 'error', 'source': 'focus',
                                  'message': 'Webcam or Face Mesh initialization failed'})
            except Exception as q_err:
                 print(f"FocusDetector: Could not put init error on queue: {q_err}")
            return

        print("FocusDetector: Run loop starting.")
        self._is_running = True
        self._stop_event.clear()
        self._distraction_history.clear()
        self._eye_closure_counter = 0
        self._frame_counter = 0

        window_name = 'Focus Detector'
        if self.show_window:
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL) # Make resizable if desired

        while self._is_running and not self._stop_event.is_set() and self._cap.isOpened():
            frame_start_time = time.time()

            # Check if window was closed by user if display is enabled
            if self.show_window:
                 if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                     print("FocusDetector: Window closed by user.")
                     self.stop() # Trigger stop if user closes window
                     break

            success, image = self._cap.read()
            if not success:
                # print("FocusDetector: Ignoring empty camera frame.")
                # Limit spin rate if continuously failing to read frames
                time.sleep(0.1)
                continue

            self._frame_counter += 1
            # Flip the image horizontally for a mirror effect
            image = cv2.flip(image, 1)

            # --- Core Analysis ---
            face_landmarks_mp, image_shape = self._process_frame(image)
            image_height, image_width = image_shape[:2] # Need dimensions here too

            analysis_result = None
            cam_matrix = None # Declare outside conditional block
            if face_landmarks_mp:
                # Calculate Camera Matrix here as it depends on image dimensions
                focal_length = float(image_width)
                center = (image_width / 2.0, image_height / 2.0)
                cam_matrix = np.array([[focal_length, 0, center[0]],
                                      [0, focal_length, center[1]],
                                      [0, 0, 1]], dtype=np.float64)

                analysis_result = self._analyze_landmarks(face_landmarks_mp, image_shape)
                status, reason, distraction_perc, _,_,_,_,_,_,_ = analysis_result
                self.latest_status = status
                self.latest_percentage = distraction_perc
                self.latest_reason = reason
            else:
                # No face detected - Treat as distraction
                self.latest_status = "No Face"
                self.latest_percentage = 100.0 # Or calculate based on history trend?
                self.latest_reason = ""
                self._distraction_history.append(1) # Append distraction
                # Recalculate percentage based on history including this frame
                if len(self._distraction_history) > 0:
                    self.latest_percentage = (sum(self._distraction_history) / len(self._distraction_history)) * 100

            # --- Send Data to Queue ---
            output_data = {
                'type': 'focus',
                'timestamp': time.time(),
                'status': self.latest_status,
                'percentage': self.latest_percentage,
                'reason': self.latest_reason
            }
            try:
                output_queue.put(output_data)
            except Exception as q_err:
                print(f"FocusDetector: Could not put data on queue: {q_err}")

            # --- Update Display (if enabled) ---
            if self.show_window and image is not None:
                display_image = image.copy() # Draw on a copy
                if analysis_result and cam_matrix is not None:
                     self._update_display(display_image, analysis_result, face_landmarks_mp, cam_matrix)
                else: # Handle display when no face is detected
                      cv2.putText(display_image, f"Status: {self.latest_status}", (30, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                      cv2.putText(display_image, f"Distraction: {self.latest_percentage:.1f}%", (30, 110),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
                      cv2.imshow(window_name, display_image)


            # --- Frame Rate Control & Exit Check ---
            # Introduce a small delay; waitKey also processes GUI events.
            # The value (e.g., 1 ms) allows the loop to run near max speed
            # while still checking for stop signals and GUI events.
            key = cv2.waitKey(1) & 0xFF
            if key == 27: # Allow ESC key in window to stop
                print("FocusDetector: ESC key pressed.")
                self.stop()

            # Optional: Calculate and print FPS for debugging
            # frame_end_time = time.time()
            # fps = 1.0 / (frame_end_time - frame_start_time + 1e-6) # Avoid div by zero
            # print(f"FPS: {fps:.1f}")

        # --- Cleanup after loop exit ---
        self._cleanup()
        print("FocusDetector: Run loop finished.")

    def stop(self):
        """Signals the run loop to stop and cleans up resources."""
        print("FocusDetector: Stop requested.")
        self._is_running = False
        self._stop_event.set()

    def _cleanup(self):
        """Releases webcam and destroys OpenCV windows."""
        print("FocusDetector: Cleaning up resources...")
        if self._cap:
            self._cap.release()
            self._cap = None
            print("FocusDetector: Webcam released.")
        if self._face_mesh:
             # MediaPipe doesn't have an explicit close usually needed unless using context manager
             self._face_mesh = None
             print("FocusDetector: Face Mesh object released.")

        # Attempt to destroy the specific window if it was shown
        if self.show_window:
             # Add error handling in case window doesn't exist
             try:
                  # Check if window exists - Note: getWindowProperty might cause issues
                  # if called after the window is implicitly destroyed (e.g. parent thread exits).
                  # Relying on destroyWindow with error suppression is safer.
                  # if cv2.getWindowProperty('Focus Detector', cv2.WND_PROP_VISIBLE) >= 1:
                  cv2.destroyWindow('Focus Detector')
                  print("FocusDetector: OpenCV window destroyed.")
                  # Add a tiny waitKey to allow GUI event processing for closing
                  cv2.waitKey(1)
             except cv2.error:
                 # print("FocusDetector: Warning - Could not destroy window (already closed?).")
                 pass
             except Exception as e:
                 # print(f"FocusDetector: Error destroying window: {e}")
                 pass
        print("FocusDetector: Cleanup complete.")

# --- Standalone Test (Optional) ---
# This block allows testing the module directly.
if __name__ == "__main__":
    print("Running Focus Detector in standalone test mode...")
    test_queue = queue.Queue()
    detector = FocusDetector(show_window=True)

    # Run the detector in a separate thread for testing
    test_thread = threading.Thread(target=detector.run, args=(test_queue,), daemon=True)
    test_thread.start()

    try:
        # Keep the main thread alive to view the window and receive data
        while test_thread.is_alive():
            try:
                data = test_queue.get(timeout=0.1) # Check queue periodically
                print(f"Received from detector: {data}")
            except queue.Empty:
                pass
            time.sleep(0.05) # Reduce main thread busy-waiting
    except KeyboardInterrupt:
        print("\nStandalone test interrupted. Stopping detector...")
        detector.stop()
        test_thread.join(timeout=5) # Wait for thread to finish
        print("Detector stopped by test harness.")
    finally:
        # Ensure cleanup happens even if loop exits unexpectedly
        if test_thread.is_alive():
            print("Forcing final stop...")
            detector.stop()
            test_thread.join(timeout=2)
        print("Standalone test finished.")