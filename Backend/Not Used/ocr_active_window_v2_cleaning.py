# ocr_active_window_v2_cleaning.py
import pyautogui
import pytesseract
import time
import sys
import re # Import regular expressions for more advanced cleaning

def clean_ocr_text(raw_text):
    if not raw_text:
        return ""

    cleaned_lines = []
    lines = raw_text.splitlines()

    for i, line in enumerate(lines): # Use enumerate to get index if needed for context later
        original_line = line # Keep original for debugging if needed
        line = line.strip()

        if not line:
            continue

        # Filter 1: Very short lines (stricter word count, more lenient char count for single long words)
        words = line.split()
        if len(words) < 2 and len(line) < 15: # e.g., single words unless they are long
            # print(f"DEBUG: Skip short: '{original_line}'")
            continue
        
        # Filter 2: Low alphanumeric ratio, but be careful not to remove lines with some symbols that are part of text
        # (e.g. code, URLs with symbols). This one is tricky.
        alnum_chars = sum(1 for char in line if char.isalnum())
        total_chars = len(line)
        if total_chars > 5 and (alnum_chars / total_chars) < 0.4: # Increased threshold, require more alnum
            # print(f"DEBUG: Skip low alnum: '{original_line}'")
            continue
            
        # Filter 3: Lines that are ONLY symbols, numbers, and whitespace (more robust)
        # Allows lines with numbers, but if it has no letters, it's likely noise
        if not re.search(r"[a-zA-Z]", line) and len(line) < 30 : # If no letters at all and relatively short
            # print(f"DEBUG: Skip no-letters: '{original_line}'")
            continue

        # Filter 4: Heuristics for browser tab/URL bar like lines (very experimental)
        # These are common patterns for browser chrome noise.
        # This is highly dependent on how Tesseract OCRs your specific browser UI.
        # Look for multiple 'x', '|', '%', '@' symbols, or common URL patterns if not a full sentence.
        symbol_count = sum(1 for char in line if char in "©%|x@>+=")
        if (symbol_count > 3 and len(words) < 10) or "http" in line.lower() and len(words) < 5 :
            # If many symbols and few words, OR looks like a short URL fragment.
            # This is a heuristic and might need a lot of tuning.
            # print(f"DEBUG: Skip browser-like UI: '{original_line}'")
            continue
        
        # Filter 5: Lines with many disconnected single characters or very short "words"
        # Example: "x + = o a x" or "Q ¢ + create L* @"
        if len(words) > 3: # Only apply if there are a few "words" to check
            short_word_count = sum(1 for word in words if len(word) <= 2)
            if short_word_count / len(words) > 0.6 and len(line) < 40: # If >60% of words are tiny and line is short
                # print(f"DEBUG: Skip fragmented: '{original_line}'")
                continue
        
        # Filter 6: Remove lines that are just numbers and a few symbols (like view counts)
        # e.g., "91K views 5.1M views 12K views 497K views 832K views"
        # This regex looks for patterns like number, optional (K/M), optional word "views", repeated.
        if re.fullmatch(r"(\s*[\d,.]+[KM]?(\s*(views|ago))?\s*)+", line.strip().lower()):
            # print(f"DEBUG: Skip view counts line: '{original_line}'")
            continue
            
        # Filter 7: Specific known junk patterns (add more as you find them)
        # For example, the "Home Shorts You Downloads" could be filtered if it appears often.
        # This requires manual observation.
        known_junk_phrases = [
            "home shorts subscriptions you", # Example, assuming this is how OCR reads it
            "home shorts you downloads",
            "cc" # If 'cc' alone is often noise
        ]
        if line.lower().strip() in known_junk_phrases:
            # print(f"DEBUG: Skip known junk phrase: '{original_line}'")
            continue


        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def ocr_active_window_content():
    try:
        active_window = pyautogui.getActiveWindow()
        if active_window is None:
            print("No active window detected.")
            print("\n----- OCR Result (Cleaned) -----"); print("(No active window)"); print("------------------------------\n")
            return None, None
        
        window_title = getattr(active_window, 'title', 'N/A')
        print(f"Attempting to OCR content from window: '{window_title}'")
        
        x = active_window.left; y = active_window.top
        width = active_window.width; height = active_window.height

        if width <= 0 or height <= 0:
            print(f"Invalid window dimensions for '{window_title}'")
            print("\n----- OCR Result (Cleaned) -----"); print("(Invalid window dimensions)"); print("------------------------------\n")
            return None, None

        screenshot_image = pyautogui.screenshot(region=(x, y, width, height))
        # screenshot_image.save("debug_ocr_capture_cleaning.png") 

        print("Performing OCR on captured image...")
        raw_text_from_ocr = pytesseract.image_to_string(screenshot_image)
        
        print("\n----- RAW OCR Result -----")
        if raw_text_from_ocr.strip():
            print(raw_text_from_ocr.strip())
        else:
            print("(No raw text detected or OCR result was empty)")
        print("--------------------------\n")

        print("Cleaning OCR text...")
        cleaned_text = clean_ocr_text(raw_text_from_ocr)

        print("\n----- OCR Result (Cleaned) -----")
        if cleaned_text.strip():
            print(cleaned_text.strip())
        else:
            print("(No meaningful text detected after cleaning)")
        print("------------------------------\n")
        return raw_text_from_ocr, cleaned_text # Return both for comparison if needed

    except AttributeError as e:
        print(f"AttributeError: {e}"); print("\n----- OCR Result (Cleaned) -----"); print("(Error geometry)"); print("------------------------------\n")
        return None, None
    except Exception as e:
        print(f"An error occurred: {e}"); print("\n----- OCR Result (Cleaned) -----"); print("(General error)"); print("------------------------------\n")
        return None, None

if __name__ == "__main__":
    print("Starting continuous OCR (with cleaning) of active window every 5 seconds (Ctrl+C to stop)...")
    print("Switch to the window you want to OCR.\n")
    try:
        while True:
            ocr_active_window_content()
            print(f"Waiting 5 seconds for next capture...")
            for i in range(5, 0, -1): print(f"{i}...", end=' ', flush=True); time.sleep(1)
            print("\n" + "="*40 + "\n")
            
    except KeyboardInterrupt:
        print("\nStopping continuous OCR test.")
    except Exception as e:
        print(f"\nAn unexpected error stopped the continuous test: {e}")
    finally:
        print("Exiting OCR exploration script.")