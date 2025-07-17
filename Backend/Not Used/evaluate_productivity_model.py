# evaluate_productivity_model.py
import torch
from datasets import load_dataset
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer
)
import numpy as np
from sklearn.metrics import classification_report, accuracy_score

# --- Step 1: Load and Prepare the Same Dataset Split ---
print("Loading and splitting the master dataset...")
# It's crucial to use the same dataset and the same 'seed' to get the exact same test set.
raw_datasets = load_dataset("csv", data_files="master_productivity_dataset.csv")

# We must use the same tokenizer that the model was trained with.
model_path = "./distilbert-productivity-classifier"
tokenizer = AutoTokenizer.from_pretrained(model_path)

def tokenize_function(examples):
    return tokenizer(examples["text"], padding="max_length", truncation=True)

print("Tokenizing data...")
tokenized_datasets = raw_datasets.map(tokenize_function, batched=True, remove_columns=["text"])

# Re-create the exact same 80/20 split to isolate our 220 test samples.
split_dataset = tokenized_datasets["train"].train_test_split(test_size=0.2, seed=42)
test_dataset = split_dataset["test"]

print(f"Loaded {len(test_dataset)} samples for evaluation.")


# --- Step 2: Load Your Fine-Tuned Model ---
print(f"Loading fine-tuned model from '{model_path}'...")
model = AutoModelForSequenceClassification.from_pretrained(model_path)


# --- Step 3: Run Predictions on the Test Set ---
print("\nRunning predictions on the unseen test set...")

# We use a simple Trainer here just as an easy way to run the prediction loop.
trainer = Trainer(
    model=model,
    # No training arguments are needed, only the output directory for logs.
    args=TrainingArguments(output_dir="./evaluation_logs"),
)

# .predict() runs the model on the entire test_dataset and gives us the outputs.
predictions_output = trainer.predict(test_dataset)

# The raw outputs from the model are 'logits'. We need to convert them to class predictions (0 or 1).
logits = predictions_output.predictions
y_pred = np.argmax(logits, axis=1)

# The true labels are also in the output object.
y_true = predictions_output.label_ids


# --- Step 4: Display the "Report Card" ---
print("\n--- Model Evaluation Report ---")

# Calculate overall accuracy
accuracy = accuracy_score(y_true, y_pred)
print(f"Overall Accuracy: {accuracy * 100:.2f}%\n")

# Define the label names for the report
target_names = ['Unproductive (0)', 'Productive (1)']

# Generate and print the detailed classification report
# This shows precision, recall, and f1-score for each class.
print(classification_report(y_true, y_pred, target_names=target_names))

print("--- End of Report ---")