# fd6.py
# Implements Tiered EAR Thresholds + Extreme Pose Override + ML Emotion Detection
# ADAPTED for integration: uses multiprocessing.Queue and multiprocessing.Event
import os
os.environ['PYTHONWARNINGS'] = 'ignore:SymbolDatabase.GetPrototype() is deprecated'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
import cv2
import mediapipe as mp
import numpy as np
import math
from collections import deque
import time
from scipy.spatial.transform import Rotation as R
import multiprocessing
import queue
import sys
# ## NEW: Import for loading the trained model ##
import joblib
import warnings
from sklearn.exceptions import InconsistentVersionWarning, ConvergenceWarning # Might as well filter these too
warnings.filterwarnings("ignore", category=UserWarning, message="SymbolDatabase.GetPrototype() is deprecated.")
warnings.filterwarnings("ignore", category=UserWarning)
# ## NEW: Suppress specific, harmless scikit-learn warnings ##
warnings.filterwarnings("ignore", category=UserWarning, module='sklearn.ensemble._base')
warnings.filterwarnings("ignore", category=UserWarning, module='sklearn.utils.validation')
warnings.filterwarnings("ignore", category=InconsistentVersionWarning)
warnings.filterwarnings("ignore", category=ConvergenceWarning)
# --- Configuration Constants ---
HEAD_YAW_THRESHOLD = 30
HEAD_PITCH_THRESHOLD = 30
EXTREME_YAW_THRESHOLD = 160
EXTREME_PITCH_THRESHOLD = 70
EYE_AR_THRESH_NORMAL = 0.18
EYE_AR_THRESH_TILTED = 0.26
EYE_AR_CONSEC_FRAMES = 3
HISTORY_BUFFER_SIZE = 30

# --- MediaPipe Initialization ---
mp_face_mesh = mp.solutions.face_mesh
mp_drawing = mp.solutions.drawing_utils

# --- Landmark Indices ---
LEFT_EYE_INDICES = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_INDICES = [263, 387, 385, 362, 380, 373]
PNP_LANDMARK_INDICES = [1, 152, 33, 263, 61, 291]
PNP_MODEL_POINTS = np.array([
    (0.0,0.0,0.0), (0.0,-330.0,-65.0), (-225.0,170.0,-135.0),
    (225.0,170.0,-135.0), (-150.0,-150.0,-125.0), (150.0,-150.0,-125.0)
], dtype=np.float64)

# --- Helper Functions (Unchanged) ---
def calculate_ear(coords):
    if coords is None: return None
    try: A=np.linalg.norm(coords[1]-coords[5]); B=np.linalg.norm(coords[2]-coords[4]); C=np.linalg.norm(coords[0]-coords[3]); return (A+B)/(2.0*C) if C!=0 else 0.3
    except Exception as e: print(f"FD Helper Error (calculate_ear): {e}", file=sys.stderr); return None
def extract_landmark_coords(landmarks, indices, w, h):
    if not landmarks: return None
    try: return np.array([(landmarks.landmark[i].x*w, landmarks.landmark[i].y*h) for i in indices], dtype=np.float64)
    except Exception as e: print(f"FD Helper Error (extract_landmark_coords): {e}", file=sys.stderr); return None
def estimate_head_pose(points, shape):
    if points is None or len(points)!=len(PNP_MODEL_POINTS): return (None,)*5
    h,w=shape[:2]; f=float(w); c=(w/2.0,h/2.0); cam_mat=np.array([[f,0,c[0]],[0,f,c[1]],[0,0,1]],dtype=np.float64)
    dist_coeffs=np.zeros((4,1))
    try:
        succ,rvec,tvec=cv2.solvePnP(PNP_MODEL_POINTS,points,cam_mat,dist_coeffs,cv2.SOLVEPNP_ITERATIVE)
        if not succ: return (None,)*5
        rmat,_=cv2.Rodrigues(rvec); euler=R.from_matrix(rmat).as_euler('YXZ',degrees=True)
        yaw,pitch,roll=euler[0],euler[1],euler[2]
        if abs(yaw)>160: yaw-=np.sign(yaw)*180
        return yaw,pitch,roll,rvec,tvec
    except Exception as e: print(f"FD Helper Error (estimate_head_pose): {e}", file=sys.stderr); return (None,)*5
def draw_pose_axis(img,rvec,tvec,cam_mat):
    if rvec is None or cam_mat is None: return
    pts3d=np.float32([[75,0,0],[0,75,0],[0,0,-75],[0,0,0]]).reshape(-1,3)
    try:
        pts2d,_=cv2.projectPoints(pts3d,rvec,tvec,cam_mat,np.zeros((4,1)))
        o=tuple(np.round(pts2d[3].ravel()).astype(int)); x=tuple(np.round(pts2d[0].ravel()).astype(int))
        y=tuple(np.round(pts2d[1].ravel()).astype(int)); z=tuple(np.round(pts2d[2].ravel()).astype(int))
        cv2.line(img,o,x,(255,0,0),3);cv2.line(img,o,y,(0,255,0),3);cv2.line(img,o,z,(0,0,255),3)
    except Exception as e: print(f"FD Helper Error (draw_pose_axis): {e}", file=sys.stderr); pass


class FocusDetector:
    def __init__(self, show_window=False, history_size=HISTORY_BUFFER_SIZE):
        self.show_window = show_window
        self.history_size = history_size
        self._cap = None
        self._face_mesh = None
        self._distraction_history = deque(maxlen=self.history_size)
        self.latest_status = "Initializing"
        self.latest_percentage = 0.0
        self.latest_reason = ""
        self._eye_closure_counter = 0

        # ## NEW: Load the trained emotion classifier model ##
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            model_path = os.path.join(script_dir, "emotion_classifier_model.joblib")
            self.emotion_model = joblib.load(model_path)
            print("FD: Emotion classifier model loaded successfully.", file=sys.stderr)
        except FileNotFoundError:
            print(f"FD Error: '{model_path}' not found. Emotion detection will be disabled.", file=sys.stderr)
            self.emotion_model = None
        except Exception as e:
            print(f"FD Error: Failed to load emotion model: {e}", file=sys.stderr)
            self.emotion_model = None


    def initialize_resources(self):
        print("FD: Initializing resources...", file=sys.stderr)
        try:
            self._face_mesh = mp_face_mesh.FaceMesh(max_num_faces=1, refine_landmarks=True, min_detection_confidence=0.5, min_tracking_confidence=0.5)
            print("FD: Face Mesh model loaded.", file=sys.stderr)
            for idx in [0, 1, -1]:
                self._cap = cv2.VideoCapture(idx)
                if self._cap and self._cap.isOpened():
                    print(f"FD: Webcam opened successfully (Index: {idx}).", file=sys.stderr)
                    return True
                if self._cap: self._cap.release()
            print("FD Error: Cannot open any webcam.", file=sys.stderr); self._cap = None; return False
        except Exception as e:
            print(f"FD Error: Failed during initialization: {e}", file=sys.stderr); self._cap = None; return False

    def _process_frame(self, image):
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        rgb.flags.writeable = False
        results = self._face_mesh.process(rgb)
        rgb.flags.writeable = True
        return results.multi_face_landmarks[0] if results.multi_face_landmarks else None, (h, w)
    
    # ## NEW: Feature extraction for the ML model ##
    # This function MUST be identical to the one in create_feature_dataset.py
    def _get_emotion_features(self, landmarks, img_shape):
        h, w = img_shape
        try:
            # Normalize landmarks to be scale-invariant
            p1 = np.array([landmarks.landmark[33].x * w, landmarks.landmark[33].y * h])
            p2 = np.array([landmarks.landmark[263].x * w, landmarks.landmark[263].y * h])
            eye_dist = np.linalg.norm(p1 - p2)
            if eye_dist == 0: return None

            features = []
            # The same key landmarks used during training
            key_landmark_indices = [33, 263, 61, 291, 13, 14, 70, 300, 10, 336]
            points = [np.array([landmarks.landmark[i].x * w, landmarks.landmark[i].y * h]) for i in key_landmark_indices]
            
            # Calculate pairwise distances and normalize
            for i in range(len(points)):
                for j in range(i + 1, len(points)):
                    distance = np.linalg.norm(points[i] - points[j])
                    features.append(distance / eye_dist)
            return features
        except Exception as e:
            print(f"FD Error (_get_emotion_features): {e}", file=sys.stderr)
            return None

    def _analyze_landmarks(self, face_landmarks, image_shape):
        h, w = image_shape
        # --- Landmark Extraction & Feature Calculation ---
        pnp_pts = extract_landmark_coords(face_landmarks, PNP_LANDMARK_INDICES, w, h)
        left_coords = extract_landmark_coords(face_landmarks, LEFT_EYE_INDICES, w, h)
        right_coords = extract_landmark_coords(face_landmarks, RIGHT_EYE_INDICES, w, h)
        
        yaw, pitch, roll, rvec, tvec = estimate_head_pose(pnp_pts, image_shape)
        left_ear = calculate_ear(left_coords); right_ear = calculate_ear(right_coords)
        ear_avg = (left_ear + right_ear) / 2.0 if left_ear is not None and right_ear is not None else None
        
        # ## NEW: Emotion Prediction using the loaded model ##
        current_emotion = "N/A"
        if self.emotion_model is not None:
            emotion_features = self._get_emotion_features(face_landmarks, image_shape)
            if emotion_features:
                # The model expects a 2D array, so we reshape our single sample
                emotion_features_2d = np.array(emotion_features).reshape(1, -1)
                try:
                    prediction = self.emotion_model.predict(emotion_features_2d)
                    current_emotion = prediction[0]
                except Exception as e:
                    print(f"FD Error (model.predict): {e}", file=sys.stderr)
        
        # --- Main Status Logic (Unchanged) ---
        status = "Focused"; reasons_list = []
        eyes_definitively_closed = False; eyes_are_open_and_confidently_detected = False
        head_pose_is_problematic = False; pose_reasons = []

        if yaw is not None and pitch is not None:
            if abs(yaw) > HEAD_YAW_THRESHOLD: head_pose_is_problematic = True; pose_reasons.append("Yaw")
            if abs(pitch) > HEAD_PITCH_THRESHOLD: head_pose_is_problematic = True; pose_reasons.append("Pitch")
        else: head_pose_is_problematic = True; pose_reasons.append("Pose Undetermined")

        current_ear_threshold = EYE_AR_THRESH_TILTED if head_pose_is_problematic else EYE_AR_THRESH_NORMAL
        if ear_avg is not None:
            if ear_avg < current_ear_threshold:
                self._eye_closure_counter += 1
                if self._eye_closure_counter >= EYE_AR_CONSEC_FRAMES: eyes_definitively_closed = True
            else: self._eye_closure_counter = 0; eyes_are_open_and_confidently_detected = True
        else: self._eye_closure_counter = 0

        is_extreme_pose = (yaw is not None and abs(yaw) > EXTREME_YAW_THRESHOLD) or (pitch is not None and abs(pitch) > EXTREME_PITCH_THRESHOLD)
        if is_extreme_pose: status = "Distracted"; reasons_list.append("Extreme Pose")
        elif eyes_definitively_closed: status = "Distracted"; reasons_list.append("Eyes Closed")
        elif head_pose_is_problematic:
            if not eyes_are_open_and_confidently_detected:
                status = "Distracted"; reasons_list.extend(pose_reasons)
                if ear_avg is None: reasons_list.append("Eye Landmarks Unclear")
                elif ear_avg < current_ear_threshold: reasons_list.append("Eyes Slightly Closed")
        elif ear_avg is None: status = "Distracted"; reasons_list.append("Eye Landmarks Unclear")

        # --- Finalize and Return ---
        dist_score = 1 if status != "Focused" else 0
        self._distraction_history.append(dist_score)
        dist_perc = (sum(self._distraction_history) / len(self._distraction_history)) * 100 if len(self._distraction_history) > 0 else 0
        final_reason = " & ".join(sorted(list(set(reasons_list))))

        analysis_result = {
            "status": status, "reason": final_reason, "distraction_percent": dist_perc,
            "yaw": yaw, "pitch": pitch, "roll": roll, "ear": ear_avg,
            "rvec": rvec, "tvec": tvec, "face_landmarks": face_landmarks,
            "emotion": current_emotion  # ## NEW: Added emotion to result ##
        }
        return analysis_result

    def _update_display(self, image, analysis_result, cam_matrix):
        st = analysis_result["status"]
        rs = analysis_result["reason"]
        dp = analysis_result["distraction_percent"]
        y, p, ear = analysis_result["yaw"], analysis_result["pitch"], analysis_result["ear"]
        rv, tv = analysis_result["rvec"], analysis_result["tvec"]
        face_landmarks_mp = analysis_result["face_landmarks"]
        emotion = analysis_result["emotion"] # ## NEW ##
        
        h, w = image.shape[:2]
        if face_landmarks_mp: 
            mp_drawing.draw_landmarks(
                image=image,
                landmark_list=face_landmarks_mp,
                connections=mp_face_mesh.FACEMESH_TESSELATION,
                landmark_drawing_spec=None,
                connection_drawing_spec=mp_drawing.DrawingSpec(color=(0, 128, 0), thickness=1)
            )
        draw_pose_axis(image, rv, tv, cam_matrix)
        status_color = (0, 0, 255) if st != "Focused" else (0, 255, 0)
        
        # Display Text
        cv2.putText(image, f"Status: {st}", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, status_color, 2)
        if rs: cv2.putText(image, f"Reason: {rs}", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.putText(image, f"Distraction: {dp:.1f}%", (30, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        # ## NEW: Display Emotion ##
        cv2.putText(image, f"Emotion: {emotion.capitalize()}", (30, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        text_y_offset = h - 20
        if ear is not None: cv2.putText(image, f"EAR: {ear:.2f}", (w-180, text_y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0),1); text_y_offset -= 20
        if p is not None: cv2.putText(image, f"Pitch: {p:.1f}", (w-180, text_y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0),1); text_y_offset -= 20
        if y is not None: cv2.putText(image, f"Yaw: {y:.1f}", (w-180, text_y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0),1)
        cv2.imshow('Focus Detector', image)

    def run(self, output_queue: multiprocessing.Queue, stop_event: multiprocessing.Event, handshake_queue: multiprocessing.Queue = None):
        if not self.initialize_resources():
            error_msg = {'source': 'focus_detector', 'type': 'error', 'timestamp': time.time(), 'message': 'Initialization failed.'}
            try: output_queue.put_nowait(error_msg)
            except Exception as e: print(f"FD Error: Could not put init error to queue: {e}", file=sys.stderr)
            return
        if handshake_queue:
            handshake_queue.put("fd_ready")
        print("FD: Run loop starting.", file=sys.stderr)
        self._distraction_history.clear()
        
        win_name = 'Focus Detector'
        if self.show_window: cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)

        while not stop_event.is_set():
            if self.show_window:
                try:
                    if cv2.getWindowProperty(win_name, cv2.WND_PROP_VISIBLE) < 1:
                        print("FD: Window closed by user.", file=sys.stderr); break
                except cv2.error: print("FD: Window property check failed, assuming closed.", file=sys.stderr); break

            if not self._cap or not self._cap.isOpened():
                print("FD Error: Webcam disconnected.", file=sys.stderr); break

            succ, img = self._cap.read()
            if not succ: time.sleep(0.05); continue
            
            img = cv2.flip(img, 1)
            landmarks, shape = self._process_frame(img)
            h, w = shape
            analysis_result = None; cam_matrix = None

            if landmarks:
                f = float(w); c = (w / 2.0, h / 2.0)
                cam_matrix = np.array([[f, 0, c[0]], [0, f, c[1]], [0, 0, 1]], np.float64)
                analysis_result = self._analyze_landmarks(landmarks, shape)
                self.latest_status = analysis_result["status"]
                self.latest_reason = analysis_result["reason"]
                self.latest_percentage = analysis_result["distraction_percent"]
            else:
                self.latest_status = "No Face"; self.latest_reason = "Face not detected"; self.latest_percentage = 100.0
                self._distraction_history.append(1)
                if len(self._distraction_history) > 0: self.latest_percentage = (sum(self._distraction_history) / len(self._distraction_history)) * 100
            
            output_data = {
                'source': 'focus_detector', 'timestamp': time.time(),
                'status': self.latest_status, 'reason': self.latest_reason,
            }
            # ## NEW: Add emotion to the output queue data ##
            if analysis_result and "emotion" in analysis_result:
                output_data['emotion'] = analysis_result['emotion']

            try: output_queue.put_nowait(output_data)
            except queue.Full: print("FD Warning: Output queue is full.", file=sys.stderr)
            
            if self.show_window and img is not None:
                display_img = img.copy()
                if analysis_result and cam_matrix is not None:
                    self._update_display(display_img, analysis_result, cam_matrix)
                else:
                    cv2.putText(display_img, f"Status: {self.latest_status}", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)
                    cv2.imshow(win_name, display_img)
            
            if self.show_window:
                if cv2.waitKey(1) & 0xFF == 27: print("FD: ESC key pressed.", file=sys.stderr); break
            else: time.sleep(0.01)

        self._cleanup()
        print("FD: Run loop finished.", file=sys.stderr)

    def _cleanup(self):
        print("FD: Cleaning up resources...", file=sys.stderr)
        if self._cap: self._cap.release(); self._cap = None; print("FD: Camera released.", file=sys.stderr)
        if self._face_mesh: self._face_mesh = None; print("FD: Face Mesh model dereferenced.", file=sys.stderr)
        if self.show_window:
            try: cv2.destroyAllWindows(); cv2.waitKey(1)
            except Exception: pass
        print("FD: Cleanup done.", file=sys.stderr)

def run_focus_detector_process(output_queue: 'multiprocessing.Queue', stop_event: 'multiprocessing.Event', handshake_queue: 'multiprocessing.Queue'):
    """This function is the target for the multiprocessing.Process."""
    try:
        detector = FocusDetector(show_window=False)
        detector.run(output_queue, stop_event, handshake_queue)
    except Exception as e:
        print(f"FD PROCESS CRASHED: {e}", file=sys.stderr)
# --- Standalone Test ---
if __name__ == "__main__":
    print("Running Focus Detector (ML Emotion) in standalone test mode...")
    test_output_queue = multiprocessing.Queue()
    test_stop_event = multiprocessing.Event()
    detector_instance = FocusDetector(show_window=True)
    detector_process = multiprocessing.Process(
        target=detector_instance.run, 
        args=(test_output_queue, test_stop_event),
        daemon=True
    )
    print("Main: Starting detector process...")
    detector_process.start()
    last_print_time = time.time()
    try:
        while detector_process.is_alive() or not test_output_queue.empty():
            latest_data = None
            try:
                while not test_output_queue.empty():
                    latest_data = test_output_queue.get_nowait()
            except queue.Empty: pass
            current_time = time.time()
            if latest_data and (current_time - last_print_time >= 1.0):
                ts_str = time.strftime('%H:%M:%S', time.localtime(latest_data.get('timestamp', current_time)))
                source = latest_data.get('source', 'N/A')
                msg_type = latest_data.get('type')
                # NEW, CLEANER SECTION
                if msg_type == 'error':
                    print(f"TESTER @ {ts_str}: ERROR from {source}: {latest_data.get('message', 'No details')}", file=sys.stderr)
                else:
                    status = latest_data.get('status', 'N/A')
                    reason = latest_data.get('reason', '')
                    emotion = latest_data.get('emotion', 'N/A')

                    # Build a clean output string
                    output_parts = [
                        f"Status: {status}",
                        f"Emotion: {emotion.capitalize()}"
                    ]
                    if reason:
                        output_parts.append(f"Reason: {reason}")

                    # Join the parts with a separator for a clean, single-line output
                    final_output = " | ".join(output_parts)
                    print(f"TESTER @ {ts_str}: {final_output}")
                last_print_time = current_time
            if not detector_process.is_alive() and test_output_queue.empty():
                print("Main: Detector process stopped and queue is empty.", file=sys.stderr); break
            time.sleep(0.1)
    except KeyboardInterrupt: print("\nMain: Test interrupted by user.", file=sys.stderr)
    finally:
        print("Main: Initiating shutdown...", file=sys.stderr)
        if detector_process.is_alive():
            test_stop_event.set()
            detector_process.join(timeout=5)
            if detector_process.is_alive():
                detector_process.terminate(); detector_process.join()
        print("Main: Standalone test finished.", file=sys.stderr)