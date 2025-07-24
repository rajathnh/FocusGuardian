# service_extractor.py
# A dedicated module to load and run the fine-tuned T5 service extractor model.

import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline
import os

class ServiceExtractor:
    def __init__(self, model_name="t5-service-extractor-modern-final"):
        """
        Initializes the ServiceExtractor by loading the fine-tuned T5 model and tokenizer.
        """
        print("SERVICE EXTRACTOR: Loading fine-tuned T5 model...")
        script_dir = os.path.dirname(os.path.abspath(__file__))
        model_path = os.path.join(script_dir, model_name)
        if not os.path.isdir(model_path):
            raise FileNotFoundError(
                f"Model directory not found at '{model_path}'. "
                "Please ensure the T5 model has been fine-tuned and saved correctly."
            )
        
        self.model_path = model_path
        self.device = 0 if torch.cuda.is_available() else -1
        
        try:
            # Use the Hugging Face pipeline for easy and efficient inference
            self.extractor_pipe = pipeline(
                "text2text-generation",
                model=self.model_path,
                tokenizer=self.model_path,
                device=self.device
            )
            print(f"SERVICE EXTRACTOR: Model loaded successfully on device: {'cuda' if self.device == 0 else 'cpu'}")
        except Exception as e:
            print(f"SERVICE EXTRACTOR: Failed to load model pipeline: {e}")
            self.extractor_pipe = None

    def _format_input_text(self, app_name, window_title, url):
        """
        Creates the input text blob in the exact format the T5 model was trained on.
        Includes the "extract service: " prefix.
        """
        # Ensure url is a string, even if it's None or empty
        url_str = url if url else ""
        return f"extract service: [APP]: {app_name} [TITLE]: {window_title} [URL]: {url_str}"

    # In service_extractor.py

    def predict(self, app_name, window_title, url):
        """
        Takes app name, title, and URL, formats them, and returns the extracted service name.
        """
        if not self.extractor_pipe:
            print("SERVICE EXTRACTOR Error: Model not loaded.")
            return "Unknown"

        # 1. Format the input text
        input_text = self._format_input_text(app_name, window_title, url)
        
        try:
            # 2. Run inference using the pipeline with the CORRECT argument name
            results = self.extractor_pipe(input_text, max_new_tokens=32, num_beams=2)
            
            # 3. Extract and clean the generated text
            if results and isinstance(results, list):
                extracted_text = results[0]['generated_text'].strip()
                return extracted_text
            else:
                return "Unknown"
        except Exception as e:
            print(f"SERVICE EXTRACTOR Error: Prediction failed: {e}")
            return "Unknown"

# --- Standalone Test Block ---
if __name__ == '__main__':
    print("--- Running a standalone test for ServiceExtractor ---")
    
    try:
        # Initialize the extractor
        service_extractor = ServiceExtractor()

        # Test cases
        test_cases = [
            {"app": "Code.exe", "title": "main.py - MyProject", "url": ""},
            {"app": "chrome.exe", "title": "How to fix bugs - Stack Overflow", "url": "stackoverflow.com/questions/123"},
            {"app": "vlc.exe", "title": "my_anime_episode.mkv - VLC media player", "url": ""},
            {"app": "chrome.exe", "title": "My Favorite Song - YouTube", "url": "youtube.com/watch?v=..."},
            {"app": "GTA5.exe", "title": "Grand Theft Auto V", "url": ""},
        ]
        
        if service_extractor.extractor_pipe:
            for case in test_cases:
                service_name = service_extractor.predict(case["app"], case["title"], case["url"])
                print(f"\nInput: APP='{case['app']}', TITLE='{case['title']}'")
                print(f"--> Extracted Service: '{service_name}'")
        else:
            print("\nSkipping tests because the model failed to load.")

    except FileNotFoundError as e:
        print(f"\nERROR: {e}")
        print("Please run the `finetune_t5_extractor.py` script first to create the model.")
    except Exception as e:
        print(f"\nAn unexpected error occurred during the test: {e}")