# focus_detector_module.py
# Implements Tiered EAR Thresholds + Extreme Pose Override

import cv2
import mediapipe as mp
import numpy as np
import math
from collections import deque
import time
from scipy.spatial.transform import Rotation as R
import threading
import queue

# --- Configuration Constants ---
HEAD_YAW_THRESHOLD = 30      # "Normal" problematic yaw
HEAD_PITCH_THRESHOLD = 30    # "Normal" problematic pitch
EXTREME_YAW_THRESHOLD = 160  # Beyond this, likely distracted due to extreme pose
EXTREME_PITCH_THRESHOLD = 70 # Beyond this, likely distracted due to extreme pose
EYE_AR_THRESH_NORMAL = 0.18  # For when head pose is NOT problematic. Calibrate!
EYE_AR_THRESH_TILTED = 0.26  # For when head pose IS "normally" problematic. Calibrate!
EYE_AR_CONSEC_FRAMES = 3
HISTORY_BUFFER_SIZE = 30

# --- MediaPipe Initialization ---
mp_face_mesh = mp.solutions.face_mesh
mp_drawing = mp.solutions.drawing_utils
drawing_spec = mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=1, circle_radius=1)
connection_drawing_spec = mp_drawing.DrawingSpec(color=(0, 128, 0), thickness=1)

LEFT_EYE_INDICES = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_INDICES = [263, 387, 385, 362, 380, 373]
PNP_LANDMARK_INDICES = [1, 152, 33, 263, 61, 291]
PNP_MODEL_POINTS = np.array([
    (0.0,0.0,0.0), (0.0,-330.0,-65.0), (-225.0,170.0,-135.0),
    (225.0,170.0,-135.0), (-150.0,-150.0,-125.0), (150.0,-150.0,-125.0)
], dtype=np.float64)

# --- Helper Functions (Condensed for brevity but functional) ---
def calculate_ear(coords):
    if coords is None: return None
    try: A=np.linalg.norm(coords[1]-coords[5]); B=np.linalg.norm(coords[2]-coords[4]); C=np.linalg.norm(coords[0]-coords[3]); return (A+B)/(2.0*C) if C!=0 else 0.3
    except: return None
def extract_landmark_coords(landmarks, indices, w, h):
    if not landmarks: return None
    try: return np.array([(landmarks.landmark[i].x*w, landmarks.landmark[i].y*h) for i in indices], dtype=np.float64)
    except: return None
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
    except: return (None,)*5
def draw_pose_axis(img,rvec,tvec,cam_mat):
    if rvec is None or cam_mat is None: return
    pts3d=np.float32([[75,0,0],[0,75,0],[0,0,-75],[0,0,0]]).reshape(-1,3)
    try:
        pts2d,_=cv2.projectPoints(pts3d,rvec,tvec,cam_mat,np.zeros((4,1)))
        o=tuple(np.round(pts2d[3].ravel()).astype(int)); x=tuple(np.round(pts2d[0].ravel()).astype(int))
        y=tuple(np.round(pts2d[1].ravel()).astype(int)); z=tuple(np.round(pts2d[2].ravel()).astype(int))
        cv2.line(img,o,x,(255,0,0),3);cv2.line(img,o,y,(0,255,0),3);cv2.line(img,o,z,(0,0,255),3)
    except: pass

class FocusDetector:
    def __init__(self, show_window=False, history_size=HISTORY_BUFFER_SIZE):
        self.show_window = show_window; self.history_size = history_size
        self._is_running=False; self._stop_event=threading.Event(); self._cap=None
        self._face_mesh=None; self._distraction_history=deque(maxlen=self.history_size)
        self.latest_status="Initializing"; self.latest_percentage=0.0; self.latest_reason=""
        self._frame_counter=0; self._eye_closure_counter=0

    def initialize_resources(self):
        print("FD: Initializing resources...")
        try:
            self._face_mesh=mp_face_mesh.FaceMesh(max_num_faces=1,refine_landmarks=False,min_detection_confidence=0.5,min_tracking_confidence=0.5)
            print("FD: Face Mesh model loaded.")
            for idx in [0,1,-1]:
                self._cap=cv2.VideoCapture(idx)
                if self._cap and self._cap.isOpened(): print(f"FD: Webcam opened successfully (Index: {idx})."); return True
                if self._cap: self._cap.release()
            print("FD Error: Cannot open any webcam."); self._cap=None; return False
        except Exception as e: print(f"FD Error: Failed during initialization: {e}"); self._cap=None; return False

    def _process_frame(self, image):
        rgb=cv2.cvtColor(image,cv2.COLOR_BGR2RGB); h,w=rgb.shape[:2]
        rgb.flags.writeable=False; results=self._face_mesh.process(rgb); rgb.flags.writeable=True
        return results.multi_face_landmarks[0] if results.multi_face_landmarks else None,(h,w)

    def _analyze_landmarks(self, face_landmarks, image_shape):
        h, w = image_shape
        pnp_pts=extract_landmark_coords(face_landmarks,PNP_LANDMARK_INDICES,w,h)
        left_coords=extract_landmark_coords(face_landmarks,LEFT_EYE_INDICES,w,h)
        right_coords=extract_landmark_coords(face_landmarks,RIGHT_EYE_INDICES,w,h)
        yaw,pitch,roll,rvec,tvec=estimate_head_pose(pnp_pts,image_shape)
        left_ear=calculate_ear(left_coords); right_ear=calculate_ear(right_coords)
        ear_avg=(left_ear+right_ear)/2.0 if left_ear is not None and right_ear is not None else None

        print(f"\n--- FRAME ANALYSIS START ---")
        print(f"DEBUG_PRE_EVAL: EAR_AVG: {'{:.4f}'.format(ear_avg) if ear_avg is not None else 'None'}, EyeCounter: {self._eye_closure_counter}")

        status="Focused"; reasons_list=[]
        eyes_definitively_closed=False; eyes_are_open_and_confidently_detected=False
        
        head_pose_is_problematic=False; pose_reasons=[] # "Normal" problematic pose
        if yaw is not None and pitch is not None:
            if abs(yaw)>HEAD_YAW_THRESHOLD: head_pose_is_problematic=True; pose_reasons.append("Yaw")
            if abs(pitch)>HEAD_PITCH_THRESHOLD: head_pose_is_problematic=True; pose_reasons.append("Pitch")
        else: head_pose_is_problematic=True; pose_reasons.append("Pose Undetermined") # Counts as "normal" problematic if undetermined

        current_ear_threshold = EYE_AR_THRESH_TILTED if head_pose_is_problematic else EYE_AR_THRESH_NORMAL
        # If pose is EXTREME, current_ear_threshold is based on TILTED, which is fine, as extreme pose logic below might override.
        print(f"DEBUG_EAR_THRESH: Using {'TILTED (HPP=True)' if head_pose_is_problematic else 'NORMAL (HPP=False)'} threshold: {current_ear_threshold:.4f}")

        if ear_avg is not None:
            if ear_avg < current_ear_threshold:
                self._eye_closure_counter+=1
                if self._eye_closure_counter>=EYE_AR_CONSEC_FRAMES: eyes_definitively_closed=True
            else: self._eye_closure_counter=0; eyes_are_open_and_confidently_detected=True
        else: self._eye_closure_counter=0
        
        print(f"DEBUG_FLAGS: EDC={eyes_definitively_closed}, EAOCD={eyes_are_open_and_confidently_detected}, HPP={head_pose_is_problematic}, PR={pose_reasons}, Yaw={'N/A' if yaw is None else f'{yaw:.1f}'}, Pitch={'N/A' if pitch is None else f'{pitch:.1f}'}, EAR_None={ear_avg is None}")

        # --- Decision Logic with Extreme Pose Override ---
        is_extreme_pose = (yaw is not None and abs(yaw) > EXTREME_YAW_THRESHOLD) or \
                          (pitch is not None and abs(pitch) > EXTREME_PITCH_THRESHOLD)

        if is_extreme_pose:
            print("DEBUG_DECISION: Cond 0 (Extreme Pose) MET")
            status = "Distracted"
            reasons_list.append("Extreme Pose")
            if eyes_definitively_closed: # If eyes also happened to be flagged as closed
                 if "Eyes Closed" not in reasons_list: reasons_list.append("Eyes Closed")
        
        elif eyes_definitively_closed: # Not extreme pose, but eyes are closed
            print("DEBUG_DECISION: Cond 1 (EDC - eyes definitively closed) MET")
            status = "Distracted"; reasons_list.append("Eyes Closed")
        
        elif head_pose_is_problematic: # Not extreme, not EDC, but "normal" problematic head pose
            print("DEBUG_DECISION: Cond 2 (HPP - 'normal' problematic head pose) CHECKED")
            if eyes_are_open_and_confidently_detected: # Based on current_ear_threshold
                print("DEBUG_DECISION:   Sub (EAOCD) MET - Staying Focused")
            else: 
                print("DEBUG_DECISION:   Sub (EAOCD) NOT MET - Distracted by Pose + Eye_Issue_If_Any")
                status = "Distracted"; reasons_list.extend(pose_reasons)
                if ear_avg is None and "Eye Landmarks Unclear" not in reasons_list:
                    reasons_list.append("Eye Landmarks Unclear")
                elif ear_avg is not None and ear_avg < current_ear_threshold and "Eyes Slightly Closed" not in reasons_list and "Eyes Closed" not in reasons_list:
                    reasons_list.append("Eyes Slightly Closed")
        
        elif ear_avg is None: # Not extreme, not EDC, HPP okay, but EAR unknown
            print("DEBUG_DECISION: Cond 3 (EAR_None) MET")
            status = "Distracted"; reasons_list.append("Eye Landmarks Unclear")
        
        else: # All good: Not extreme, eyes open, head pose okay
            print("DEBUG_DECISION: No primary distraction conditions met - Status remains Focused")

        dist_score=1 if status=="Distracted" else 0; self._distraction_history.append(dist_score)
        final_reason=""; 
        if status=="Distracted":
            unique_reasons=set(reasons_list) # Use set for uniqueness, then sort for consistent order
            if "Extreme Pose" in unique_reasons and any(r in unique_reasons for r in ["Yaw", "Pitch"]): # Extreme Pose implies Yaw/Pitch
                if "Yaw" in unique_reasons: unique_reasons.remove("Yaw")
                if "Pitch" in unique_reasons: unique_reasons.remove("Pitch")
            if "Eyes Closed" in unique_reasons and "Eyes Slightly Closed" in unique_reasons:
                unique_reasons.remove("Eyes Slightly Closed")
            if ("Eyes Closed" in unique_reasons or "Eyes Slightly Closed" in unique_reasons) and \
               "Eye Landmarks Unclear" in unique_reasons:
                if not any(r in unique_reasons for r in ["Yaw","Pitch","Pose Undetermined","Extreme Pose"]): # If only eye issues
                    unique_reasons.remove("Eye Landmarks Unclear")
            final_reason=" & ".join(sorted(list(unique_reasons)))
        dist_perc=(sum(self._distraction_history)/len(self._distraction_history))*100 if len(self._distraction_history)>0 else 0
        
        print(f"DEBUG_FINAL: Status='{status}', Reason='{final_reason}', Perc={dist_perc:.1f}%")
        print(f"--- FRAME ANALYSIS END ---\n")
        return status,final_reason,dist_perc,yaw,pitch,roll,ear_avg,rvec,tvec,face_landmarks

    def _update_display(self, image, analysis_result, face_landmarks_mp, cam_matrix):
        (st, rs, dp, y, p, _, ear, rv, tv, _) = analysis_result
        h, w = image.shape[:2]
        if face_landmarks_mp: 
            for landmark_set in [LEFT_EYE_INDICES, RIGHT_EYE_INDICES]:
                for idx in landmark_set:
                    if idx < len(face_landmarks_mp.landmark): 
                        lm = face_landmarks_mp.landmark[idx]
                        cv2.circle(image, (int(lm.x * w), int(lm.y * h)), 1, (0, 255, 255), -1)
        draw_pose_axis(image, rv, tv, cam_matrix)
        status_color = (0, 0, 255) if st != "Focused" else (0, 255, 0)
        cv2.putText(image, f"Status: {st}", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, status_color, 2)
        if rs: cv2.putText(image, f"Reason: {rs}", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.putText(image, f"Distraction: {dp:.1f}%", (30, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        
        text_y_offset = h - 20
        if ear is not None: cv2.putText(image, f"EAR: {ear:.2f}", (w-180, text_y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0),1); text_y_offset -= 20
        if p is not None: cv2.putText(image, f"Pitch: {p:.1f}", (w-180, text_y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0),1); text_y_offset -= 20
        if y is not None: cv2.putText(image, f"Yaw: {y:.1f}", (w-180, text_y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0),1)
        cv2.imshow('Focus Detector', image)

    def run(self, output_queue: queue.Queue):
        if not self.initialize_resources():
            try: output_queue.put({'type':'error','source':'focus','message':'Init fail'})
            except: pass; return
        print("FD: Run loop starting."); self._is_running=True; self._stop_event.clear()
        self._distraction_history.clear(); self._eye_closure_counter=0
        win='Focus Detector';
        if self.show_window: cv2.namedWindow(win,cv2.WINDOW_NORMAL)
        while self._is_running and not self._stop_event.is_set() and self._cap and self._cap.isOpened():
            if self.show_window:
                try:
                    if cv2.getWindowProperty(win,cv2.WND_PROP_VISIBLE)<1: self.stop();break
                except: self.stop();break
            succ,img=self._cap.read()
            if not succ: time.sleep(0.1); continue
            img=cv2.flip(img,1); landmarks,shape=self._process_frame(img); h,w=shape
            res=None; cmat=None
            if landmarks:
                f=float(w);c=(w/2.0,h/2.0);cmat=np.array([[f,0,c[0]],[0,f,c[1]],[0,0,1]],np.float64)
                res=self._analyze_landmarks(landmarks,shape)
                self.latest_status,self.latest_reason,self.latest_percentage,_,_,_,_,_,_,_=res
            else:
                self.latest_status="No Face";self.latest_reason="Face not detected";self.latest_percentage=100.0
                self._distraction_history.append(1)
                if len(self._distraction_history)>0: self.latest_percentage=(sum(self._distraction_history)/len(self._distraction_history))*100
            
            out={'type':'focus','timestamp':time.time(),'status':self.latest_status,'percentage':self.latest_percentage,'reason':self.latest_reason}
            try: output_queue.put_nowait(out)
            except: print("FD: Q full/err")
            
            if self.show_window and img is not None:
                d_img=img.copy()
                if res and cmat is not None: self._update_display(d_img,res,landmarks,cmat)
                else:
                    cv2.putText(d_img,f"Status: {self.latest_status}",(30,50),cv2.FONT_HERSHEY_SIMPLEX,1,(0,0,255),2)
                    if self.latest_reason:cv2.putText(d_img,f"Reason: {self.latest_reason}",(30,80),cv2.FONT_HERSHEY_SIMPLEX,0.7,(0,0,255),2)
                    cv2.putText(d_img,f"Distraction: {self.latest_percentage:.1f}%",(30,110),cv2.FONT_HERSHEY_SIMPLEX,0.7,(255,255,0),2)
                    cv2.imshow(win,d_img)
            key=-1
            if self.show_window: key=cv2.waitKey(1)&0xFF
            else: time.sleep(0.001) 
            if key==27: self.stop()
        self._cleanup(); print("FD: Run loop finished.")

    def stop(self): print("FD: Stop req."); self._is_running=False; self._stop_event.set()
    def _cleanup(self):
        print("FD: Cleaning up...")
        if self._cap:self._cap.release();self._cap=None;print("FD: Cam released.")
        if self._face_mesh:self._face_mesh=None;print("FD: Mesh deref.")
        if self.show_window:
            try:cv2.destroyWindow('Focus Detector');print("FD: Win destroyed.");cv2.waitKey(1)
            except:pass
        print("FD: Cleanup done.")

# --- Standalone Test (Optional) ---
if __name__ == "__main__":
    print("Running Focus Detector in standalone test mode...")
    test_q = queue.Queue()
    detector = FocusDetector(show_window=True) # Set to False for no UI and only terminal output
    test_thread = threading.Thread(target=detector.run, args=(test_q,), daemon=True)
    test_thread.start()

    latest_data_from_detector = None
    last_print_time = time.time()

    try:
        while test_thread.is_alive() or not test_q.empty():
            try:
                while True: # Drain the queue to get the latest item
                    latest_data_from_detector = test_q.get_nowait()
            except queue.Empty:
                pass # Queue is empty, proceed with last known data

            current_time = time.time()
            if current_time - last_print_time >= 1.0: # Print once per second
                ts_str = time.strftime('%H:%M:%S', time.localtime(current_time))
                if latest_data_from_detector:
                    msg_type = latest_data_from_detector.get('type')
                    if msg_type == 'error':
                        print(f"ERROR @ {ts_str}: Src: {latest_data_from_detector.get('source','N/A')}, Msg: {latest_data_from_detector.get('message','No details')}")
                    else: # 'focus' type
                        print(f"STATUS @ {ts_str}: Focus: {latest_data_from_detector.get('status','N/A')}, "
                              f"Distr: {latest_data_from_detector.get('percentage',0.0):.1f}%, "
                              f"Reason: {latest_data_from_detector.get('reason','N/A')}")
                elif test_thread.is_alive():
                    print(f"STATUS @ {ts_str}: Waiting for data from detector...")
                last_print_time = current_time
            
            if not test_thread.is_alive() and test_q.empty():
                print("Main: Detector thread stopped and queue is empty. Exiting test loop.")
                break
            time.sleep(0.05) # Prevent busy-waiting

    except KeyboardInterrupt:
        print("\nMain: Standalone test interrupted by user.")
    finally:
        print("Main: Initiating shutdown...")
        if detector: detector.stop() 
        if test_thread.is_alive():
            print("Main: Waiting for detector thread to join...")
            test_thread.join(timeout=5)
        
        print(f"Main: Detector thread {'alive' if test_thread.is_alive() else 'stopped'}.")
        
        final_items_count = 0
        last_item_from_q = None
        try:
            while not test_q.empty(): 
                last_item_from_q = test_q.get_nowait()
                final_items_count += 1
        except queue.Empty: pass
        if last_item_from_q: print(f"Main: Last item from queue before exit: {last_item_from_q}")
        if final_items_count > 1: print(f"Main: Processed {final_items_count} remaining item(s) from queue after thread stop signal.")
        
        print("Main: Standalone test finished.")