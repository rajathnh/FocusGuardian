# evaluate.py
# This script LOADS a pre-trained model and evaluates it on the test set.
# It does NOT perform any training.

import torch
from datasets import load_dataset
from transformers import pipeline
import pandas as pd

# --- Configuration ---
# IMPORTANT: This must match the output directory from your training script
MODEL_DIR = "t5-service-extractor-modern-final" 
DATASET_FILE = "service_dataset_final.csv"
TEXT_PREFIX = "Classify the primary application or service from the following data: "

print(f"--- Loading model from '{MODEL_DIR}' ---")

# --- 1. Load the fine-tuned model via a pipeline ---
# This is the fastest way to load a model for inference.
# It will automatically use the GPU if available.
try:
    extractor_pipe = pipeline("text2text-generation", model=MODEL_DIR, device=0 if torch.cuda.is_available() else -1)
    print("Model loaded successfully onto GPU." if torch.cuda.is_available() else "Model loaded successfully onto CPU.")
except Exception as e:
    print(f"Error loading model: {e}")
    exit()

# --- 2. Load and prepare the EXACT same evaluation dataset ---
print(f"--- Loading dataset '{DATASET_FILE}' to get the test split ---")

def is_valid(example):
    return example["text"] is not None and example["label"] is not None

# Load the full dataset
full_dataset = load_dataset("csv", data_files=DATASET_FILE)["train"]
# Filter and shuffle with the SAME seed to get the identical split
eval_data = full_dataset.filter(is_valid).shuffle(seed=42).train_test_split(test_size=40)['test']

print(f"Found {len(eval_data)} samples in the test set for evaluation.")

# --- 3. Run evaluation and generate the report ---
print("\n--- Generating Full Evaluation Report ---")

results = []
correct_predictions = 0
total_predictions = len(eval_data)

for item in eval_data:
    input_text = TEXT_PREFIX + item['text']
    true_label = item['label']
    
    # Get the model's prediction
    prediction_output = extractor_pipe(input_text)
    predicted_label = prediction_output[0]['generated_text']
    
    is_correct = (predicted_label == true_label)
    if is_correct:
        correct_predictions += 1
    
    results.append({
        "Input Text": item['text'][:100] + '...', # Show a snippet
        "True Label": true_label,
        "Predicted Label": predicted_label,
        "Correct?": "✅" if is_correct else "❌"
    })

# --- 4. Display the results ---
# Use pandas to create a clean, readable table
df = pd.DataFrame(results)
print(df.to_string()) # .to_string() ensures the entire table is printed

# Print the final accuracy score
accuracy = (correct_predictions / total_predictions) * 100
print("\n--- Evaluation Summary ---")
print(f"Correct Predictions: {correct_predictions}/{total_predictions}")
print(f"Accuracy on Test Set: {accuracy:.2f}%")