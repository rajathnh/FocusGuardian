# emotion_test_image.py
from deepface import DeepFace
import cv2 # DeepFace uses OpenCV, so it's good to have it explicitly if you want to display
import sys

def analyze_emotion_from_image(image_path):
    try:
        print(f"Analyzing emotions in image: {image_path}")
        # By default, DeepFace.analyze will try to detect a face first.
        # 'actions' specifies what analyses to perform.
        # 'enforce_detection=True' (default) means it will raise an error if no face is found.
        # 'enforce_detection=False' will return None or an empty list if no face.
        # 'silent=True' can suppress some of DeepFace's internal console output.
        
        analysis_result = DeepFace.analyze(
            img_path=image_path,
            actions=['emotion'],
            enforce_detection=True, # Let's be strict for this first image test
            silent=False # Let's see DeepFace's output for now
        )
        
        # DeepFace.analyze returns a list of dictionaries, one for each face found.
        # For a single face image, we expect one item in the list.
        if analysis_result and isinstance(analysis_result, list) and len(analysis_result) > 0:
            first_face_analysis = analysis_result[0]
            dominant_emotion = first_face_analysis.get('dominant_emotion')
            emotions = first_face_analysis.get('emotion') # This is a dict of all emotion scores

            print("\n----- Emotion Analysis Result -----")
            print(f"Dominant Emotion: {dominant_emotion}")
            print("Emotion Scores:")
            if emotions:
                for emotion, score in emotions.items():
                    print(f"  - {emotion}: {score:.2f}%")
            print("-----------------------------------")
            
            # Optional: Display the image with the dominant emotion
            # img = cv2.imread(image_path)
            # if img is not None:
            #     face_region = first_face_analysis.get('region') # {'x': X, 'y': Y, 'w': W, 'h': H}
            #     if face_region:
            #         x, y, w, h = face_region['x'], face_region['y'], face_region['w'], face_region['h']
            #         cv2.rectangle(img, (x, y), (x+w, y+h), (0, 255, 0), 2)
            #         cv2.putText(img, dominant_emotion, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,255,0), 2)
            #     cv2.imshow("Emotion Test", img)
            #     cv2.waitKey(0)
            #     cv2.destroyAllWindows()

        else:
            print("No face detected or analysis failed to return expected results.")

    except ValueError as ve: # Often raised if no face is detected with enforce_detection=True
        print(f"ValueError during emotion analysis: {ve}")
        print("This might mean no face was detected in the image.")
    except Exception as e:
        print(f"An error occurred during emotion analysis: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        image_file = sys.argv[1]
        analyze_emotion_from_image(image_file)
    else:
        print("Please provide an image file path as a command-line argument.")
        print("Usage: python emotion_test_image.py path/to/your/face_image.jpg")
        # Example: analyze_emotion_from_image("test_face.jpg")