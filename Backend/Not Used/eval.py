# evaluate_models.py

import torch
from datasets import load_dataset
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer
)
import numpy as np
import evaluate

# --- Step 1: Load and Prepare the Test Data ---
# We only need the evaluation data for this task.
print("Loading IMDb test dataset...")
raw_datasets = load_dataset("imdb")
eval_dataset = raw_datasets["test"].shuffle(seed=42).select(range(1000)) # Use the same 1000 samples for a fair comparison

# Load a tokenizer (we can use the base one for both models)
tokenizer = AutoTokenizer.from_pretrained("distilbert-base-uncased")

def tokenize_function(examples):
    return tokenizer(examples["text"], padding="max_length", truncation=True)

print("Tokenizing test data...")
tokenized_eval_dataset = eval_dataset.map(tokenize_function, batched=True)


# --- Step 2: Define the Evaluation Function ---
# A function to compute accuracy during evaluation
accuracy_metric = evaluate.load("accuracy")
def compute_metrics(eval_pred):
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)
    return accuracy_metric.compute(predictions=predictions, references=labels)

# We'll use a temporary Trainer just to run the evaluation loop easily
# The arguments are minimal because we are not training.
eval_args = TrainingArguments(
    output_dir="./evaluation_results",
    per_device_eval_batch_size=16,
    do_eval=True,
)


# --- Step 3: Evaluate the BASE Model ---
print("\n--- Evaluating BASE DistilBERT (Before Fine-Tuning) ---")
# Load the original, pre-trained model from Hugging Face Hub
base_model = AutoModelForSequenceClassification.from_pretrained("distilbert-base-uncased", num_labels=2)

# Create a Trainer for the base model
base_trainer = Trainer(
    model=base_model,
    args=eval_args,
    eval_dataset=tokenized_eval_dataset,
    compute_metrics=compute_metrics,
)

# Run the evaluation
base_metrics = base_trainer.evaluate()
base_accuracy = base_metrics['eval_accuracy'] * 100
print("Evaluation complete.")


# --- Step 4: Evaluate YOUR FINE-TUNED Model ---
print("\n--- Evaluating YOUR Fine-Tuned Model ---")
# Define the path to your saved model
fine_tuned_model_path = "./distilbert-imdb-sentiment-classifier"

# Load your specialized model from the local directory
fine_tuned_model = AutoModelForSequenceClassification.from_pretrained(fine_tuned_model_path)

# Create a Trainer for your fine-tuned model
fine_tuned_trainer = Trainer(
    model=fine_tuned_model,
    args=eval_args,
    eval_dataset=tokenized_eval_dataset,
    compute_metrics=compute_metrics,
)

# Run the evaluation
fine_tuned_metrics = fine_tuned_trainer.evaluate()
fine_tuned_accuracy = fine_tuned_metrics['eval_accuracy'] * 100
print("Evaluation complete.")


# --- Step 5: Print the Final Comparison ---
print("\n\n===== EVALUATION SUMMARY =====")
print(f"Base Model Accuracy:      {base_accuracy:.2f}%")
print(f"Fine-Tuned Model Accuracy: {fine_tuned_accuracy:.2f}%")
print("================================")