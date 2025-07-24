# Focus Guardian

**An Intelligent, Privacy-First Productivity Monitoring & Analytics Platform**

Focus Guardian is a sophisticated desktop application designed to provide users with deep, actionable insights into their productivity habits. Leveraging a hybrid architecture that combines local AI processing with a robust cloud backend, it offers real-time focus analysis without compromising user privacy. The platform tracks application usage, determines user engagement through webcam analysis, and provides a comprehensive suite of analytics to help users understand and improve their workflow.

### Application Gallery

| Dashboard | Session History | Classification Report |
| :---: | :---: | :---: |
| ![Dashboard](images/Dashboard.png) | ![Session History](images/Session%20History.png) | ![Classification Report](images/Classification.png) |
| **System Architecture** | **Session Detail 1** | **Session Detail 2** |
| ![Architecture](images/Architecture.png) | ![Session History 1](images/Session%20History1.png) | ![Session History 2](images/Session%20History2.png) |

*Note: Replace this with a compelling screenshot of your application's UI*

## 🏛️ Core Architectural Philosophy

This project was engineered around a central challenge: **How do you provide powerful, AI-driven analysis of sensitive user data (screen and webcam) without sending that raw data to the cloud?**

The solution is a hybrid, decoupled architecture that leverages the strengths of multiple technology stacks:

- **Local, On-Device AI Engine (Python)**: All real-time analysis of the user's screen and webcam happens directly on the user's machine. This privacy-first approach ensures that sensitive raw data never leaves their computer.

- **Centralized Cloud Backend (Node.js & MongoDB)**: A scalable backend service handles user authentication, data aggregation, and serves the analytics dashboard. It only ever receives the results of the local analysis, not the raw data itself.

- **Rich Desktop Client (React & Electron)**: A modern, responsive user interface built with React is packaged into a professional cross-platform desktop application using Electron, which acts as the command center for the entire system.

This design provides the best of both worlds: the privacy and performance of a native desktop application combined with the power, data persistence, and scalability of a modern web service.

## ✨ Key Features

- **Intelligent Focus Tracking**: Utilizes a custom-trained machine learning model to classify productivity based on application context and user engagement.

- **Privacy-Centric Design**: Real-time webcam and screen analysis is performed 100% on the user's local machine. Only anonymized, structured analysis results are sent for aggregation.

- **Comprehensive Analytics Dashboard**: Visualize productivity trends over time with interactive charts for daily focus, session-by-session performance, and application usage breakdowns.

- **AI-Powered Productivity Assistant**: An integrated chatbot (powered by the Groq Llama 3.1) allows users to ask natural language questions about their productivity data and receive insightful summaries.

- **Secure User Authentication**: Full user registration and login system with JWT-based authentication to ensure data is secure and private to each user.

- **Seamless Desktop Experience**: Packaged as a native desktop application for Windows, macOS, and Linux using Electron.

## ⚙️ Technology & Architecture Deep Dive

The application is composed of three primary, independent components that communicate via APIs.

### 1. The Local Analysis Engine (Python)

This is the "smart sensor" of the system, running silently in the background during a monitoring session.

**Technology Stack**: Python, OpenCV, MediaPipe, PyTesseract, PyWinAuto, Scikit-learn, PyTorch/Transformers.

#### Face Analysis (`fd6.py`)
- Uses MediaPipe Face Mesh to detect facial landmarks in real-time
- Calculates head pose and Eye Aspect Ratio (EAR) to determine gaze direction and attention
- Feeds landmark data into a custom-trained Scikit-learn model (.joblib) to classify user emotion (e.g., neutral, focused, tired)

#### Screen Analysis (`screen_recorder_with_ocr.py`)
- Identifies the active window, application name (pywinauto), and title
- Performs targeted OCR (pytesseract) on the active window to extract textual context

#### AI Classification Pipeline (`run_local_analysis.py`)
- A fine-tuned T5 model classifies the primary service/application (e.g., "VS Code", "YouTube", "Slack") from the window title and OCR content
- A fine-tuned DistilBERT model acts as the final classifier, taking in all available context (gaze, emotion, application, content) to produce a final "Productive" or "Unproductive" label
- The final JSON result is sent to the Node.js backend via a secure API call

### 2. The Cloud Backend (Node.js)

This is the central "brain" and data warehouse of the application.

**Technology Stack**: Node.js, Express.js, MongoDB Atlas, Mongoose, JWT.

#### Responsibilities

- **User Management**: Handles user registration, password hashing (bcrypt), and login, issuing JWT tokens for stateless authentication

- **Data Ingestion**: Provides a secure API endpoint (`/api/sessions/data/:id`) that receives the JSON analysis results from the local Python engine

- **Database Logic**: Updates user and session documents in MongoDB, incrementing focus/distraction timers and aggregating application usage statistics

- **Analytics API**: Exposes a suite of powerful data aggregation endpoints that feed the frontend charts. Leverages the MongoDB Aggregation Framework to efficiently query and transform data for daily trends, historical summaries, and more

- **AI Chatbot Service**: Provides an endpoint that securely fetches a user's summarized data, injects it as context into a prompt, and queries the Groq (Llama 3.1) API for insightful, natural language responses

### 3. The Frontend Client (React & Electron)

This is the command center that the user interacts with.

**Technology Stack**: React, React Router, Axios, Chart.js, Electron.

#### Responsibilities

- **User Interface**: A complete single-page application (SPA) with routing for the dashboard, login/register pages, and the detailed analytics view

- **State Management**: Uses React hooks (useState, useEffect, useCallback) to manage application state, including the active session, timer, and fetched data

- **Data Visualization**: Renders interactive charts and graphs using Chart.js to display the analytics data fetched from the Node.js backend

#### Desktop Integration (Electron)
- The React app is wrapped in an Electron shell, providing a native desktop experience
- Electron's Main Process acts as an orchestrator, using `child_process` to seamlessly start and stop the local Python engine in the background in response to user actions
- A secure IPC Bridge (`preload.js`) allows the sandboxed React UI to safely communicate with the powerful Main Process, enabling a one-click start/stop experience without compromising security

---

This project demonstrates a comprehensive understanding of full-stack development, machine learning integration, and sophisticated software architecture, tackling real-world challenges of privacy, performance, and user experience.