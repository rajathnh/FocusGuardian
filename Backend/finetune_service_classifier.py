# finetune_service_classifier.py (Modern Version - Fixed for Latest Transformers)

import torch
from datasets import load_dataset
from transformers import (
    AutoTokenizer,
    AutoModelForSeq2SeqLM,
    DataCollatorForSeq2Seq,
    Seq2SeqTrainingArguments,
    Seq2SeqTrainer
)
import os

# --- Helper Functions ---
def is_valid(example):
    return example["text"] is not None and example["label"] is not None and example["text"] != "" and example["label"] != ""

def preprocess_function(examples, tokenizer, prefix):
    inputs = [prefix + inp for inp in examples["text"]]
    model_inputs = tokenizer(inputs, max_length=128, truncation=True)
    labels = tokenizer(text_target=examples["label"], max_length=32, truncation=True)
    model_inputs["labels"] = labels["input_ids"]
    return model_inputs

def compute_metrics(eval_pred):
    return {} # Placeholder for load_best_model_at_end

# --- Main Execution Block ---
if __name__ == '__main__':
    if torch.cuda.is_available():
        torch.backends.cudnn.benchmark = True

    # --- 1. Load and Prepare Dataset ---
    print("Loading and preparing dataset...")
    dataset = load_dataset("csv", data_files="service_dataset_final.csv")
    data = dataset["train"]

    checkpoint = "t5-small"
    tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    prefix = "Classify the primary application or service from the following data: "

    data = data.filter(is_valid).shuffle(seed=42)
    split_data = data.train_test_split(test_size=40)
    train_data = split_data['train']
    eval_data = split_data['test']

    print("Tokenizing dataset...")
    tokenized_train = train_data.map(
        lambda x: preprocess_function(x, tokenizer, prefix),
        batched=True, remove_columns=train_data.column_names
    )
    tokenized_eval = eval_data.map(
        lambda x: preprocess_function(x, tokenizer, prefix),
        batched=True, remove_columns=eval_data.column_names
    )
    train_dataset = tokenized_train
    eval_dataset = tokenized_eval

    # --- 2. Load Model ---
    print("Loading pre-trained t5-small model...")
    model = AutoModelForSeq2SeqLM.from_pretrained(checkpoint)
    output_dir = "t5-service-extractor-modern-final"

    # --- 3. Configure Training Arguments with MODERN Features ---
    training_args = Seq2SeqTrainingArguments(
        output_dir=output_dir,
        num_train_epochs=30,
        per_device_train_batch_size=32,
        per_device_eval_batch_size=64,
        fp16=True,
        gradient_accumulation_steps=2,
        dataloader_num_workers=0,
        predict_with_generate=False,
        logging_strategy="epoch",
        eval_strategy="epoch",  # Changed from evaluation_strategy to eval_strategy
        save_strategy="epoch",
        save_total_limit=1,
        load_best_model_at_end=True,
        metric_for_best_model="loss",
        greater_is_better=False,
    )

    # --- 4. Create Data Collator and Trainer ---
    
    # --- THIS IS THE FIX: Define the data_collator before using it ---
    data_collator = DataCollatorForSeq2Seq(tokenizer=tokenizer, model=model)
    
    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        tokenizer=tokenizer,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
    )

    print("\nStarting fine-tuning with MODERN, updated libraries...")
    trainer.train()
    print("Fine-tuning complete.")

    # --- 5. Save the Final, Best Model ---
    print(f"\nSaving the BEST performing model to ./{output_dir}")
    trainer.save_model(output_dir)
    print("Best model saved successfully!")
    
    # --- 6. Test the Final Model ---
    print("\n--- Running a quick test on the new T5 Extractor ---")
    from transformers import pipeline

    extractor_pipe = pipeline("text2text-generation", model=output_dir, device=0)

    test_text_1 = "extract service: [APP]: Code.exe [TITLE]: main.py - MyProject [URL]: "
    test_text_2 = "extract service: [APP]: chrome.exe [TITLE]: How to fix bugs - Stack Overflow [URL]: stackoverflow.com"
    test_text_3 = "extract service: [APP]: vlc.exe [TITLE]: my_anime_episode.mkv - VLC [URL]: "

    print(f"Input: '{test_text_1}'")
    print(f"Prediction: {extractor_pipe(test_text_1)}")

    print(f"\nInput: '{test_text_2}'")
    print(f"Prediction: {extractor_pipe(test_text_2)}")

    print(f"\nInput: '{test_text_3}'")
    print(f"Prediction: {extractor_pipe(test_text_3)}")