# emotion_test_webcam.py
from deepface import DeepFace
import cv2
import time

# Choose a backend for face detection. Default is 'opencv'.
# Others include 'ssd', 'dlib', 'mtcnn', 'retinaface'. Some might be more accurate but slower.
# For real-time, 'opencv' or 'ssd' are often good starting points.
DETECTOR_BACKEND = 'ssd' 

def analyze_webcam_emotions():
    cap = cv2.VideoCapture(0) # 0 for default webcam
    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return

    last_analysis_time = time.time()
    analysis_interval = 5 # seconds - how often to run DeepFace analysis (it's heavy)
    dominant_emotion_text = "Initializing..."

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Failed to capture frame.")
            break

        current_time = time.time()
        display_frame = frame.copy() # Work on a copy for drawing

        if current_time - last_analysis_time >= analysis_interval:
            last_analysis_time = current_time
            try:
                # Analyze the current frame for emotion
                # 'enforce_detection=False' is crucial for real-time to avoid crashes if face is briefly lost
                # 'silent=True' suppresses DeepFace's own print statements during the loop
                results = DeepFace.analyze(
                    img_path=frame, 
                    actions=['emotion'], 
                    enforce_detection=False, # Don't crash if no face, just return empty/None
                    detector_backend=DETECTOR_BACKEND,
                    silent=True 
                )
                
                # DeepFace returns a list of dicts, one for each face
                if results and isinstance(results, list) and len(results) > 0:
                    # Consider the first detected face
                    first_face_analysis = results[0]
                    dominant_emotion_text = first_face_analysis.get('dominant_emotion', "N/A")
                    
                    # Get face region for drawing bounding box
                    face_region = first_face_analysis.get('region') # {'x': X, 'y': Y, 'w': W, 'h': H}
                    if face_region:
                        x, y, w, h = face_region['x'], face_region['y'], face_region['w'], face_region['h']
                        cv2.rectangle(display_frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                        cv2.putText(display_frame, dominant_emotion_text, (x, y-10), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
                    print(f"Timestamp: {time.strftime('%H:%M:%S')}, Dominant Emotion: {dominant_emotion_text}, Confidence: {first_face_analysis['face_confidence']:.2f}")

                else:
                    dominant_emotion_text = "No face detected"
                    print(f"Timestamp: {time.strftime('%H:%M:%S')}, {dominant_emotion_text}")
            
            except Exception as e:
                # This might catch errors if a face is detected but emotion analysis fails for some reason
                # or if the frame is invalid for DeepFace.
                dominant_emotion_text = "Analysis Error"
                # print(f"Error during DeepFace analysis in loop: {e}") # Uncomment for debugging errors
                pass # Continue to next frame processing

        # Display the current dominant emotion text on frame continuously even if analysis is not run this cycle
        cv2.putText(display_frame, f"Emotion: {dominant_emotion_text}", (20, 40), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2, cv2.LINE_AA)
        
        cv2.imshow("Live Emotion Detection (DeepFace) - Press 'q' to quit", display_frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()
    print("Webcam stream stopped.")

if __name__ == "__main__":
    analyze_webcam_emotions()