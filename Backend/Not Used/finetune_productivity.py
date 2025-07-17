# finetune_productivity.py

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

# --- Step 1: Load Your Custom Dataset ---
print("Loading master productivity dataset...")
# This line now points to your combined, labeled CSV file.
raw_datasets = load_dataset("csv", data_files="master_productivity_dataset.csv")

# The model name we are fine-tuning
checkpoint = "distilbert-base-uncased"
# Load the tokenizer for DistilBERT
tokenizer = AutoTokenizer.from_pretrained(checkpoint)

# A function to tokenize the 'text' column of your CSV
def tokenize_function(examples):
    return tokenizer(examples["text"], padding="max_length", truncation=True)

# Apply tokenization to the entire dataset
print("\nTokenizing the dataset...")
tokenized_datasets = raw_datasets.map(tokenize_function, batched=True, remove_columns=["text"]) # remove_columns cleans up the dataset

# The dataset is already shuffled from your combine script, but we still need to split it.
# We'll split the 'train' split (which is the whole dataset) into a new training and test set.
# 80% for training, 20% for evaluation is a standard split.
split_dataset = tokenized_datasets["train"].train_test_split(test_size=0.2, seed=42)
train_dataset = split_dataset["train"]
eval_dataset = split_dataset["test"]

print(f"\nDataset prepared: Training on {len(train_dataset)} samples, evaluating on {len(eval_dataset)}.")


# --- Step 2: Load the Pre-trained Model ---
print("\nLoading pre-trained DistilBERT model...")
# Our labels are 0 (Unproductive) and 1 (Productive), so num_labels=2
model = AutoModelForSequenceClassification.from_pretrained(checkpoint, num_labels=2)


# --- Step 3: Configure and Run the Training ---
# Define where the final model will be saved
output_dir = "distilbert-productivity-classifier"

# Define the training hyperparameters
# These are tuned for a dataset of ~1000-2000 samples.
# NEW, CORRECTED CODE
# In finetune_productivity.py

# Using the most basic arguments to ensure compatibility with new/unknown versions.
training_args = TrainingArguments(
    output_dir=output_dir,
    num_train_epochs=5,
    per_device_train_batch_size=16,
    per_device_eval_batch_size=16,
    warmup_steps=100,
    weight_decay=0.01,
    logging_dir='./logs',
    
    # --- Using the most stable, long-standing arguments ---
    
    # Enable evaluation. This is the oldest method.
    do_eval=True,
    
    # Set logging and saving intervals in terms of steps.
    logging_steps=50,
    save_steps=50, 
    
    # IMPORTANT: We must remove `load_best_model_at_end=True` for now,
    # as it often requires the newer, more explicit strategy arguments.
    # The model saved at the end of the 5th epoch will be our final model.
)

# Define the metric for evaluation
accuracy_metric = evaluate.load("accuracy")
def compute_metrics(eval_pred):
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)
    return accuracy_metric.compute(predictions=predictions, references=labels)

# The Trainer orchestrates the fine-tuning process
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    eval_dataset=eval_dataset,
    compute_metrics=compute_metrics,
)

# Start the training!
print("\nStarting fine-tuning on your custom productivity data...")
trainer.train()
print("Fine-tuning complete.")


# --- Step 4: Save the Final Model ---
print(f"\nSaving the best model to ./{output_dir}")
trainer.save_model(output_dir)
tokenizer.save_pretrained(output_dir)
print("Productivity classifier saved successfully!")


# --- Step 5: Test Your New Model (Optional but Recommended) ---
print("\n--- Running a quick test on the new model ---")

# Load the fine-tuned model you just saved
fine_tuned_model = AutoModelForSequenceClassification.from_pretrained(output_dir)
fine_tuned_tokenizer = AutoTokenizer.from_pretrained(output_dir)

# A classic productive example
productive_text = "[FOCUS]: Focused [EMOTION]: neutral [APP]: Code.exe [TITLE]: main.py [CONTENT]: def my_function():"
# A classic unproductive example
unproductive_text = "[FOCUS]: Distracted [EMOTION]: happy [APP]: chrome.exe [TITLE]: YouTube [CONTENT]: funny cat compilation"

# Move model to GPU if available
if torch.cuda.is_available():
    fine_tuned_model.to("cuda")

def predict(text):
    inputs = fine_tuned_tokenizer(text, return_tensors="pt")
    if torch.cuda.is_available():
        inputs = {k: v.to("cuda") for k, v in inputs.items()}
    
    with torch.no_grad():
        logits = fine_tuned_model(**inputs).logits
    
    prediction = torch.argmax(logits, dim=-1).item()
    return "Productive" if prediction == 1 else "Unproductive"

print(f"Input: '{productive_text}'")
print(f"Prediction: {predict(productive_text)}\n")

print(f"Input: '{unproductive_text}'")
print(f"Prediction: {predict(unproductive_text)}")