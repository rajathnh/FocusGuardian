# finetune_imdb_sentiment.py

# --- Import necessary libraries ---
# 'torch' is the backend, 'datasets' for data loading, 'transformers' for the model/training
# 'numpy' and 'evaluate' are for calculating accuracy.
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

# --- Step 1: Load and Prepare the IMDb Dataset ---
print("Loading IMDb dataset from Hugging Face Hub...")
# The 'datasets' library makes it easy to download standard datasets.
# It automatically handles downloading, caching, and loading the data.
raw_datasets = load_dataset("imdb")

# Define the pre-trained model we want to use. 'distilbert-base-uncased' is a fast and effective choice.
checkpoint = "distilbert-base-uncased"
# Every model on Hugging Face has a corresponding "tokenizer". 
# The tokenizer's job is to convert raw text into numbers (tokens) that the model can understand.
tokenizer = AutoTokenizer.from_pretrained(checkpoint)

# This function will be applied to every example in our dataset.
def tokenize_function(examples):
    # The tokenizer takes the text and handles padding (making all sequences the same length)
    # and truncation (cutting off sequences that are too long).
    return tokenizer(examples["text"], padding="max_length", truncation=True)

# Use the .map() method to apply our tokenization function to the entire dataset.
# `batched=True` processes multiple examples at once for speed.
print("\nTokenizing the dataset (this may take a moment)...")
tokenized_datasets = raw_datasets.map(tokenize_function, batched=True)

# The full IMDb dataset is large (25,000 training samples).
# For a quick proof-of-concept, we'll select a smaller, random subset.
# This will make training much faster while still giving a good result.
train_dataset = tokenized_datasets["train"].shuffle(seed=42).select(range(5000))
eval_dataset = tokenized_datasets["test"].shuffle(seed=42).select(range(1000))

print(f"\nUsing a subset for this demo: Training on {len(train_dataset)} samples, evaluating on {len(eval_dataset)}.")


# --- Step 2: Load the Pre-trained Model ---
print("\nLoading pre-trained DistilBERT model...")
# `AutoModelForSequenceClassification` automatically adds a classification "head"
# on top of the base DistilBERT model.
# We tell it `num_labels=2` because we have two classes: Negative (0) and Positive (1).
model = AutoModelForSequenceClassification.from_pretrained(checkpoint, num_labels=2)


# --- Step 3: Configure the Training Process ---
# Define the directory where the final trained model will be saved.
output_dir = "distilbert-imdb-sentiment-classifier"

# `TrainingArguments` is a class that holds all the hyperparameters for the training run.
# THE GUARANTEED CORRECT CODE FOR YOUR OLD VERSION
training_args = TrainingArguments(
    output_dir=output_dir,
    num_train_epochs=3,
    per_device_train_batch_size=16,
    per_device_eval_batch_size=16,
    warmup_steps=500,
    weight_decay=0.01,
    logging_dir='./logs',
    
    # --- KEY CHANGES FOR VERY OLD VERSIONS ---
    logging_steps=500,       # Log metrics every 500 steps
    save_steps=500,          # Save a checkpoint every 500 steps
    do_eval=True,            # The old boolean flag to enable evaluation
)

# We need a function to calculate metrics during evaluation. Here, we'll use accuracy.
accuracy_metric = evaluate.load("accuracy")
def compute_metrics(eval_pred):
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)
    return accuracy_metric.compute(predictions=predictions, references=labels)

# The `Trainer` class from Hugging Face orchestrates the entire fine-tuning process.
# It brings together the model, training arguments, datasets, and metric computation.
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    eval_dataset=eval_dataset,
    compute_metrics=compute_metrics,
)


# --- Step 4: Start Fine-Tuning ---
print("\nStarting the fine-tuning process...")
# This one line of code starts the entire training loop.
trainer.train()
print("Fine-tuning complete.")


# --- Step 5: Save the Final Model ---
# After training, we save the fine-tuned model and its tokenizer to the output directory.
# This allows us to load it later for inference without needing to retrain.
print(f"\nSaving the fine-tuned model to ./{output_dir}")
trainer.save_model(output_dir)
tokenizer.save_pretrained(output_dir)
print("Model saved successfully.")


# --- Step 6: Test the Fine-Tuned Model on New Examples ---
print("\n--- Running inference with the new model ---")

# Load the model we just saved to ensure it works correctly.
fine_tuned_model = AutoModelForSequenceClassification.from_pretrained(output_dir)
fine_tuned_tokenizer = AutoTokenizer.from_pretrained(output_dir)

# For GPU usage, move the model to the GPU device
if torch.cuda.is_available():
    fine_tuned_model.to("cuda")

# Create two new sentences to test on.
positive_review = "I absolutely loved this movie! The acting was brilliant and the story was gripping."
negative_review = "What a waste of time. The plot was predictable and the characters were boring."

# The model expects a dictionary mapping of label IDs to label names.
labels_map = fine_tuned_model.config.id2label

# Test the positive review
inputs = fine_tuned_tokenizer(positive_review, return_tensors="pt")
# Move input tensors to the same device as the model (GPU)
if torch.cuda.is_available():
    inputs = {k: v.to("cuda") for k, v in inputs.items()}
    
with torch.no_grad(): # Disable gradient calculation for faster inference
    logits = fine_tuned_model(**inputs).logits

prediction = torch.argmax(logits, dim=-1).item()
print(f"\nReview: '{positive_review}'")
print(f"Prediction: {labels_map[prediction]}")

# Test the negative review
inputs = fine_tuned_tokenizer(negative_review, return_tensors="pt")
if torch.cuda.is_available():
    inputs = {k: v.to("cuda") for k, v in inputs.items()}

with torch.no_grad():
    logits = fine_tuned_model(**inputs).logits

prediction = torch.argmax(logits, dim=-1).item()
print(f"\nReview: '{negative_review}'")
print(f"Prediction: {labels_map[prediction]}")