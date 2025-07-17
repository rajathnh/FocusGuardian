# create_feature_dataset.py
import cv2
import mediapipe as mp
import numpy as np
import os
import pandas as pd
from tqdm import tqdm

# --- MediaPipe Initialization ---
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1, min_detection_confidence=0.5)

# --- Feature Calculation Functions ---
# (These are simplified versions from your fd6.py for this specific task)
def get_geometric_features(landmarks, img_shape):
    h, w = img_shape

    # Normalize landmarks to be scale-invariant
    # We use the distance between the eyes as the normalization factor
    p1 = np.array([landmarks.landmark[33].x * w, landmarks.landmark[33].y * h])
    p2 = np.array([landmarks.landmark[263].x * w, landmarks.landmark[263].y * h])
    eye_dist = np.linalg.norm(p1 - p2)
    if eye_dist == 0: return None

    features = []
    # Create features by calculating distances between key points, normalized by eye distance
    # This is a simple example; you can add many more features like angles, etc.
    key_landmark_indices = [
        33, 263, # Left/Right eye outer corners
        61, 291, # Left/Right mouth corners
        13, 14,  # Upper/Lower lip center
        70, 300, # Left/Right eyebrow inner ends
        10, 336, # Left/Right eyebrow outer ends
    ]

    # Get the coordinates of all key landmarks
    points = [np.array([landmarks.landmark[i].x * w, landmarks.landmark[i].y * h]) for i in key_landmark_indices]
    
    # Calculate pairwise distances and normalize
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            distance = np.linalg.norm(points[i] - points[j])
            features.append(distance / eye_dist)

    return features

# --- Main Data Processing Loop ---
def create_dataset(dataset_path):
    all_features = []
    all_labels = []
    
    # The emotions folders in FER2013
    emotions = ["angry", "happy", "neutral", "sad", "surprise"]

    for emotion_idx, emotion in enumerate(emotions):
        emotion_folder = os.path.join(dataset_path, emotion)
        if not os.path.isdir(emotion_folder):
            print(f"Warning: Folder not found {emotion_folder}")
            continue

        print(f"Processing emotion: {emotion}")
        image_files = os.listdir(emotion_folder)
        
        for img_name in tqdm(image_files, desc=emotion):
            img_path = os.path.join(emotion_folder, img_name)
            image = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE) # FER2013 is grayscale
            if image is None: continue

            # Convert grayscale to RGB for MediaPipe
            image_rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
            h, w, _ = image_rgb.shape
            
            results = face_mesh.process(image_rgb)
            if results.multi_face_landmarks:
                landmarks = results.multi_face_landmarks[0]
                features = get_geometric_features(landmarks, (h, w))
                
                if features:
                    all_features.append(features)
                    all_labels.append(emotion) # Use the string label

    return pd.DataFrame(all_features), pd.Series(all_labels, name="emotion")


if __name__ == '__main__':
    # IMPORTANT: Change this path to where you unzipped the FER2013 dataset
    train_folder_path = r'D:\Focus Guardian 2.0\Stuff\archive\train'
    
    print("Starting dataset creation...")
    features_df, labels_series = create_dataset(train_folder_path)
    
    # Combine features and labels into one DataFrame
    full_df = pd.concat([features_df, labels_series], axis=1)

    # Save to a single, clean file
    output_filename = "facial_features_dataset.csv"
    full_df.to_csv(output_filename, index=False)
    
    print(f"\nDataset creation complete!")
    print(f"Saved {len(full_df)} samples to {output_filename}")
    print("\nFirst 5 rows of your new dataset:")
    print(full_df.head())