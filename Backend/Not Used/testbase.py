# test_base_model_associations.py

import torch
from transformers import pipeline

# --- Step 1: Load the Base Model ---
# We use the `pipeline` tool from transformers, which makes this task very easy.
# We specify "fill-mask" as the task.
# This will load the base DistilBERT model, NOT the one fine-tuned for sequence classification.
print("Loading base DistilBERT model for Masked Language Modeling...")
fill_mask = pipeline(
    "fill-mask",
    model="distilbert-base-uncased"
)
print("Model loaded.")


# --- Step 2: Define our Test Data ---
test_sentences = [
    # 1. Productive (Coding)
    "[FOCUS]: Focused [EMOTION]: neutral [APP]: code.exe [TITLE]: main.py [CONTENT]: import pandas as pd. This activity is [MASK].",

    # 2. Productive (Research)
    "[FOCUS]: Focused [EMOTION]: neutral [APP]: chrome.exe [TITLE]: Stack Overflow [CONTENT]: How to solve ValueError in Python. This activity is [MASK].",

    # 3. Unproductive (Social Media)
    "[FOCUS]: Distracted [EMOTION]: neutral [APP]: chrome.exe [TITLE]: Facebook [CONTENT]: scrolling through the news feed. This activity is [MASK].",

    # 4. Unproductive (YouTube Entertainment)
    "[FOCUS]: Distracted [EMOTION]: happy [APP]: chrome.exe [TITLE]: YouTube [CONTENT]: Top 10 Funniest Cat Videos. This activity is [MASK].",

    # 5. Ambiguous (Music)
    "[FOCUS]: Focused [EMOTION]: happy [APP]: spotify.exe [TITLE]: Lofi Hip Hop Radio [CONTENT]: music playing. This activity is [MASK]."
]


# --- Step 3: Run the Predictions ---
print("\n--- Running Predictions ---")

# Loop through each sentence and get the top 5 predictions for the [MASK] token
for i, sentence in enumerate(test_sentences):
    print(f"\n--- Test Case #{i+1} ---")
    print(f"Input: {sentence.replace(' [MASK].', '')}")
    
    # The pipeline returns a list of dictionaries, each with a predicted token and a score.
    predictions = fill_mask(sentence, top_k=5)
    
    print("Top 5 Predictions for [MASK]:")
    for pred in predictions:
        # The 'token_str' contains the predicted word.
        # The 'score' is the model's confidence.
        predicted_word = pred['token_str']
        confidence = pred['score']
        print(f"  - '{predicted_word}' (Confidence: {confidence:.2f})")