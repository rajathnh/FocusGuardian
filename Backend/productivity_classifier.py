# productivity_classifier.py
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import os

class ProductivityClassifier:
    def __init__(self, model_name="distilbert-productivity-classifier"):
        print("CLASSIFIER: Loading productivity model...")
        script_dir = os.path.dirname(os.path.abspath(__file__))
        model_path = os.path.join(script_dir, model_name)
        if not os.path.isdir(model_path):
            raise FileNotFoundError(f"Model directory not found at {model_path}. Please ensure the fine-tuned model exists.")
        
        # Load the fine-tuned model and tokenizer from the saved directory
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_path)
        
        # Move model to GPU if available, for faster inference
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model.to(self.device)
        self.model.eval() # Set the model to evaluation mode (disables dropout, etc.)
        
        print(f"CLASSIFIER: Model loaded successfully on device: '{self.device}'")

    def _format_input_text(self, focus_data, screen_data):
        """Creates the text blob in the exact format the model was trained on."""
        return (
            f"[FOCUS]: {focus_data.get('status', 'N/A')} "
            f"[REASON]: {focus_data.get('reason', '')} "
            f"[EMOTION]: {focus_data.get('emotion', 'N/A')} "
            f"[APP]: {screen_data.get('app_name', 'N/A')} "
            f"[TITLE]: {screen_data.get('window_title', '')} "
            f"[CONTENT]: {screen_data.get('screen_content_ocr', '')}"
        )

    def predict(self, focus_data, screen_data):
        """
        Takes raw data dictionaries, formats them, and returns a productivity label.
        Returns 'Productive', 'Unproductive', or 'Error'.
        """
        if not focus_data or not screen_data:
            return "Error: Incomplete data"
            
        # 1. Format the input text
        text_blob = self._format_input_text(focus_data, screen_data)
        
        # 2. Tokenize the text
        inputs = self.tokenizer(text_blob, return_tensors="pt", padding=True, truncation=True, max_length=512)
        
        # 3. Move tensors to the correct device (GPU/CPU)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        # 4. Make prediction
        with torch.no_grad(): # Disable gradient calculation for inference
            logits = self.model(**inputs).logits
        
        # 5. Convert output to a label
        prediction_id = torch.argmax(logits, dim=-1).item()
        
        # Assuming 1 was 'Productive' and 0 was 'Unproductive' during training
        return "Productive" if prediction_id == 1 else "Unproductive"