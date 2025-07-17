## 🚀 Quick Start & Demo

This section explains how to get the application's core backend service up and running.

### Prerequisites

1.  A modern version of **Python (3.10 or 3.11 recommended)**.
2.  The **Tesseract OCR Engine**.
    *   **Windows:** Download and run the installer from the [Tesseract at UB Mannheim page](https://github.com/UB-Mannheim/tesseract/wiki).
    *   **Mac:** `brew install tesseract`
    *   **Linux:** `sudo apt install tesseract-ocr`
3.  An **NVIDIA GPU** is recommended for real-time performance, but the application will fall back to CPU.

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/focus-guardian.git
    cd focus-guardian
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    .\venv\Scripts\activate  # On Windows
    # source venv/bin/activate  # On Mac/Linux
    ```

3.  **Install all required Python libraries:** This command uses the provided `requirements.txt` file.
    ```bash
    python -m pip install -r requirements.txt
    ```

### Running the Application

The trained AI models are required to run the application but are too large for this Git repository.

1.  **Download the Pre-trained Models:**
    *   Click this link to download the models from Google Drive:
        **[Download Models Here](https://drive.google.com/drive/folders/1chs8Ys5QeTUV73vAEYpqlQO4mLsn2B1d?usp=sharing)**
    *   Download both the `emotion_classifier_model.joblib` file and the entire `distilbert-productivity-classifier` folder.

2.  **Place the Models in Your Project:**
    *   Move the `emotion_classifier_model.joblib` file into the main `focus-guardian` directory.
    *   Move the `distilbert-productivity-classifier` folder into the main `focus-guardian` directory.
    *   Your folder should now look like this:
        ```
        focus-guardian/
        |-- distilbert-productivity-classifier/
        |   |-- config.json
        |   |-- ... (other model files)
        |-- venv/
        |-- emotion_classifier_model.joblib
        |-- ProductivityManager.py
        |-- fd6.py
        |-- ... (all your other .py and .txt files)
        ```

3.  **Run the Main Application:**
    ```bash
    python ProductivityManager.py
    ```

You will now see the live analysis printed to your terminal. The application is running! You can stop it with `Ctrl+C`.