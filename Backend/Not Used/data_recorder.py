import cv2
import mediapipe as mp
import numpy as np
import math
from collections import deque
import time
from scipy.spatial.transform import Rotation as R
import csv # For saving features
import os # For creating directories
from datetime import datetime # For unique filenames

# --- Configuration ---
# (Thresholds not needed for recording, but keep for reference if desired)
# HEAD_YAW_THRESHOLD = 25
# HEAD_PITCH_THRESHOLD = 20
# EYE_AR_THRESH = 0.23
# EYE_AR_CONSEC_FRAMES = 3
# HISTORY_BUFFER_SIZE = 30 # Not directly used for recording features

# --- Output Configuration ---
OUTPUT_DIR = "focus_data" # Directory to save videos and features
FRAME_RATE_APPROX = 20 # Approximate frame rate for VideoWriter (adjust if needed)

# --- MediaPipe Initialization ---
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=False,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5)
mp_drawing = mp.solutions.drawing_utils
drawing_spec = mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=1, circle_radius=1)
connection_drawing_spec = mp_drawing.DrawingSpec(color=(0, 128, 0), thickness=1)

# --- Helper Functions (Keep the working versions from Phase 1) ---

def calculate_ear(eye_landmarks_indices, facial_landmarks, image_width, image_height):
    try:
        coords = np.array([(facial_landmarks.landmark[i].x * image_width,
                            facial_landmarks.landmark[i].y * image_height) for i in eye_landmarks_indices])
        A = np.linalg.norm(coords[1] - coords[5])
        B = np.linalg.norm(coords[2] - coords[4])
        C = np.linalg.norm(coords[0] - coords[3])
        if C == 0: return 0.3 # Avoid division by zero
        ear = (A + B) / (2.0 * C)
        return ear
    except (IndexError, TypeError, ValueError): # Catch potential errors if landmarks missing
        return None # Return None if calculation fails

def estimate_head_pose(landmarks_2d_normalized, image_shape):
    try:
        image_points = np.array([
            (landmarks_2d_normalized[1].x * image_shape[1], landmarks_2d_normalized[1].y * image_shape[0]),
            (landmarks_2d_normalized[152].x * image_shape[1], landmarks_2d_normalized[152].y * image_shape[0]),
            (landmarks_2d_normalized[33].x * image_shape[1], landmarks_2d_normalized[33].y * image_shape[0]),
            (landmarks_2d_normalized[263].x * image_shape[1], landmarks_2d_normalized[263].y * image_shape[0]),
            (landmarks_2d_normalized[61].x * image_shape[1], landmarks_2d_normalized[61].y * image_shape[0]),
            (landmarks_2d_normalized[291].x * image_shape[1], landmarks_2d_normalized[291].y * image_shape[0])
        ], dtype="double")

        model_points = np.array([
            (0.0, 0.0, 0.0), (0.0, -330.0, -65.0), (-225.0, 170.0, -135.0),
            (225.0, 170.0, -135.0), (-150.0, -150.0, -125.0), (150.0, -150.0, -125.0)
        ])

        focal_length = image_shape[1]
        center = (image_shape[1]/2, image_shape[0]/2)
        camera_matrix = np.array([[focal_length, 0, center[0]], [0, focal_length, center[1]], [0, 0, 1]], dtype="double")
        dist_coeffs = np.zeros((4,1))

        (success, rotation_vector, translation_vector) = cv2.solvePnP(
            model_points, image_points, camera_matrix, dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE)

        if not success: return None, None, None, None, None

        rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
        scipy_r = R.from_matrix(rotation_matrix)
        euler_angles = scipy_r.as_euler('YXZ', degrees=True)

        yaw = euler_angles[0]
        pitch = euler_angles[1]
        roll = euler_angles[2] # We need Roll now!

        # Yaw Correction (Keep this)
        if abs(yaw) > 150: yaw = yaw - np.sign(yaw) * 180

        return yaw, pitch, roll, rotation_vector, translation_vector

    except (IndexError, TypeError, ValueError, np.linalg.LinAlgError): # Catch potential errors
         return None, None, None, None, None

def draw_pose_axis(image, rotation_vector, translation_vector, camera_matrix):
    try:
        axis_length = 75
        axis_points_3d = np.float32([[axis_length, 0, 0], [0, axis_length, 0], [0, 0, -axis_length], [0,0,0]]).reshape(-1, 3)
        image_points_2d, _ = cv2.projectPoints(axis_points_3d, rotation_vector, translation_vector, camera_matrix, np.zeros((4,1)))
        origin = tuple(image_points_2d[3].ravel().astype(int))
        x_axis_end = tuple(image_points_2d[0].ravel().astype(int))
        y_axis_end = tuple(image_points_2d[1].ravel().astype(int))
        z_axis_end = tuple(image_points_2d[2].ravel().astype(int))
        cv2.line(image, origin, x_axis_end, (255, 0, 0), 3); cv2.line(image, origin, y_axis_end, (0, 255, 0), 3); cv2.line(image, origin, z_axis_end, (0, 0, 255), 3)
    except Exception: # Catch any drawing error silently
        pass

# --- Main Recording Loop ---

# Create output directory if it doesn't exist
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)
    print(f"Created directory: {OUTPUT_DIR}")

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("Error: Cannot open webcam.")
    exit()

print("\n--- Data Recorder ---")
print("Press 'R' to start/stop recording.")
print("Press 'Q' to quit.")

is_recording = False
video_writer = None
csv_writer = None
csv_file = None
frame_counter = 0
session_timestamp = None

# Define CSV header
csv_header = ['frame', 'timestamp_ms', 'yaw', 'pitch', 'roll', 'ear', 'label']

while cap.isOpened():
    success, image = cap.read()
    if not success:
        print("Ignoring empty camera frame.")
        continue

    # Get frame dimensions (needed for VideoWriter)
    image_height, image_width, _ = image.shape

    # Process image
    image_rgb = cv2.cvtColor(cv2.flip(image, 1), cv2.COLOR_BGR2RGB) # Flip for selfie view
    image_rgb.flags.writeable = False
    results = face_mesh.process(image_rgb)
    image_rgb.flags.writeable = True
    display_image = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR) # Back to BGR for display

    # --- Feature Extraction ---
    yaw, pitch, roll, ear_avg = None, None, None, None # Reset features each frame

    if results.multi_face_landmarks:
        face_landmarks = results.multi_face_landmarks[0]

        # --- Optional: Draw landmarks/axis for visual feedback ---
        # mp_drawing.draw_landmarks(display_image, face_landmarks, mp_face_mesh.FACEMESH_CONTOURS, drawing_spec, connection_drawing_spec)
        # Estimate pose (needed for features AND drawing axis)
        est_yaw, est_pitch, est_roll, rvec, tvec = estimate_head_pose(face_landmarks.landmark, display_image.shape)
        # if rvec is not None: draw_pose_axis(display_image, rvec, tvec, cam_matrix) # cam_matrix defined below

        # --- Calculate features if pose was estimated ---
        if est_yaw is not None:
            yaw, pitch, roll = est_yaw, est_pitch, est_roll # Assign calculated values

            # Standard MediaPipe 468 landmarks for eyes for EAR
            left_eye_indices = [33, 159, 158, 133, 153, 145]
            right_eye_indices = [263, 386, 385, 362, 380, 374]
            left_ear = calculate_ear(left_eye_indices, face_landmarks, image_width, image_height)
            right_ear = calculate_ear(right_eye_indices, face_landmarks, image_width, image_height)

            if left_ear is not None and right_ear is not None:
                ear_avg = (left_ear + right_ear) / 2.0

    # --- Recording Logic ---
    key = cv2.waitKey(5) & 0xFF

    if key == ord('r'): # Toggle Recording
        if not is_recording:
            # Start recording
            is_recording = True
            frame_counter = 0
            session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            video_filename = os.path.join(OUTPUT_DIR, f"session_{session_timestamp}.mp4")
            csv_filename = os.path.join(OUTPUT_DIR, f"session_{session_timestamp}_features.csv")

            # Initialize Video Writer
            fourcc = cv2.VideoWriter_fourcc(*'mp4v') # Codec (use 'XVID' for AVI)
            video_writer = cv2.VideoWriter(video_filename, fourcc, FRAME_RATE_APPROX, (image_width, image_height))

            # Initialize CSV Writer
            csv_file = open(csv_filename, 'w', newline='')
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(csv_header) # Write header

            print(f"--- Recording STARTED ---")
            print(f"   Video: {video_filename}")
            print(f"   Features: {csv_filename}")
        else:
            # Stop recording
            is_recording = False
            if video_writer:
                video_writer.release()
                video_writer = None
            if csv_file:
                csv_file.close()
                csv_file = None
            csv_writer = None
            print(f"--- Recording STOPPED (Frames: {frame_counter}) ---")

    elif key == ord('q'): # Quit
        if is_recording: # Ensure ongoing recording is stopped before quitting
             is_recording = False
             if video_writer: video_writer.release()
             if csv_file: csv_file.close()
             print(f"--- Recording STOPPED before quitting (Frames: {frame_counter}) ---")
        print("Quitting...")
        break

    # --- Write Data if Recording ---
    if is_recording and video_writer and csv_writer:
        # Write video frame (use the original flipped image for correct orientation in video)
        video_writer.write(cv2.flip(image, 1))

        # Write features to CSV
        # Only write if features were successfully calculated
        if yaw is not None and pitch is not None and roll is not None and ear_avg is not None:
            current_time_ms = int(time.time() * 1000) # Millisecond timestamp
            row_data = [
                frame_counter,
                current_time_ms,
                f"{yaw:.4f}",
                f"{pitch:.4f}",
                f"{roll:.4f}",
                f"{ear_avg:.4f}",
                "UNKNOWN" # Placeholder label - we will fill this in Step 2
            ]
            csv_writer.writerow(row_data)
        else:
            # Optionally log or handle frames where features couldn't be extracted
            # print(f"Skipping frame {frame_counter} due to missing features.")
            pass

        frame_counter += 1


    # --- Display Information ---
    status_text = "RECORDING" if is_recording else "Press 'R' to Record"
    color = (0, 0, 255) if is_recording else (0, 255, 0)
    cv2.putText(display_image, status_text, (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
    # Optional: display live features
    # if yaw is not None: cv2.putText(display_image, f"Y:{yaw:.1f} P:{pitch:.1f} R:{roll:.1f}", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0), 1)
    # if ear_avg is not None: cv2.putText(display_image, f"EAR:{ear_avg:.2f}", (30, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0), 1)

    cv2.imshow('Data Recorder', display_image)


# --- Cleanup ---
print("Releasing resources...")
cap.release()
cv2.destroyAllWindows()
if face_mesh: face_mesh.close()
# Ensure any open files are closed (safety check)
if video_writer: video_writer.release()
if csv_file and not csv_file.closed: csv_file.close()

print("Data recorder stopped.")