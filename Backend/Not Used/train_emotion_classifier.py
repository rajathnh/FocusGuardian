# train_emotion_classifier.py
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
import joblib

# --- 1. Load the Dataset ---
print("Loading dataset...")
df = pd.read_csv("facial_features_dataset.csv")

# Drop rows with any missing values, just in case
df.dropna(inplace=True)

print("Dataset loaded. Shape:", df.shape)

# --- 2. Prepare Data for Training ---
# X contains the features (all columns except the last one)
X = df.iloc[:, :-1].values 
# y contains the labels (the 'emotion' column)
y = df['emotion']

# Split the data into a training set and a testing set
# 80% for training, 20% for testing. 'random_state' ensures we get the same split every time.
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

print(f"Training data shape: {X_train.shape}")
print(f"Testing data shape: {X_test.shape}")


# --- 3. Train the Model ---
# We'll use a RandomForestClassifier. It's powerful, fast, and hard to mess up.
# 'n_estimators' is the number of "trees" in the forest. 100 is a good default.
# 'n_jobs=-1' tells it to use all available CPU cores to speed up training.
print("\nTraining RandomForestClassifier...")
model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)

# The .fit() method is where the learning happens!
model.fit(X_train, y_train)
print("Training complete.")


# --- 4. Evaluate the Model ---
print("\nEvaluating model performance...")
# Use the trained model to make predictions on the test data (data it has never seen)
y_pred = model.predict(X_test)

# Check how accurate the predictions were
accuracy = accuracy_score(y_test, y_pred)
print(f"\nModel Accuracy on Test Data: {accuracy * 100:.2f}%")

# Print a detailed report
print("\nClassification Report:")
print(classification_report(y_test, y_pred))


# --- 5. Save the Trained Model ---
# We save the trained model so we can use it in our main application without retraining.
model_filename = "emotion_classifier_model.joblib"
joblib.dump(model, model_filename)

print(f"\nModel saved to {model_filename}")