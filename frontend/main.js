// In: frontend/main.js
const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const isDev = require('electron-is-dev'); // To check if we are in development
const { spawn } = require('child_process'); // To run the Python script

let mainWindow;
let pythonProcess = null; // Variable to hold the python child process

function createWindow() {
  // Create the browser window.
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      // Preload script is the secure bridge to your React app
      preload: path.join(__dirname, 'preload.js'),
    },
    title: "Focus Guardian"
  });

  // Load the React app.
  // In dev, we load from the local dev server for hot-reloading.
  // In production, we load the built `index.html` file.
  const startUrl = isDev
    ? 'http://localhost:3000'
    : `file://${path.join(__dirname, 'build/index.html')}`;

  mainWindow.loadURL(startUrl);

  // Open the DevTools automatically in development
  if (isDev) {
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  }

  mainWindow.on('closed', () => (mainWindow = null));
}

// --- IPC Listeners for Communication with React App ---

// Listen for the 'start-local-engine' signal from the UI
ipcMain.on('start-local-engine', (event, { sessionId, token }) => {
  console.log('[Main Process] Received signal to start local engine.');

  if (pythonProcess) {
    console.log('[Main Process] Terminating existing Python process...');
    pythonProcess.kill();
  }
  
  // Define the path to the Python script and virtual environment
  // Using path.join is crucial for cross-platform compatibility
  const pythonScriptPath = path.join(__dirname, '..', 'Backend', 'run_local_analysis.py');
  
  // --- IMPORTANT: CHOOSE THE CORRECT PYTHON EXECUTABLE PATH ---
  // Option 1: For Windows venv
  const pythonExecutable = path.join(__dirname, '..', 'Backend', 'venv', 'Scripts', 'python.exe');
  
  // Option 2: For Mac/Linux venv (uncomment if you're on Mac/Linux)
  // const pythonExecutable = path.join(__dirname, '..', 'Backend', 'venv', 'bin', 'python');

  console.log(`[Main Process] Spawning: ${pythonExecutable} ${pythonScriptPath}`);

  pythonProcess = spawn(pythonExecutable, [
    pythonScriptPath,
    '--session', sessionId,
    '--token', token
  ]);
  let isReady = false;

  // Listen for output from the Python script
  pythonProcess.stdout.on('data', (data) => {
    const output = data.toString();
    console.log(`[Python Engine]: ${output}`); // Keep logging all output for debugging

    // Check for our special "ready" message
    if (!isReady && output.includes('PYTHON_ENGINE_READY')) {
      isReady = true;
      console.log('[Main Process] Detected PYTHON_ENGINE_READY signal.');
      // Send a signal to the React UI that the engine is now ready
      mainWindow.webContents.send('engine-ready');
    }
  });

  pythonProcess.stderr.on('data', (data) => {
    const output = data.toString();
    console.error(`[Python Engine ERROR]: ${output}`);
    
    // Check for our special "failed" message
    if (!isReady && output.includes('PYTHON_ENGINE_FAILED')) {
        isReady = true; // Prevents sending multiple failure signals
        console.log('[Main Process] Detected PYTHON_ENGINE_FAILED signal.');
        mainWindow.webContents.send('engine-failed');
    }
  });

  pythonProcess.on('close', (code) => {
    console.log(`[Main Process] Python process exited with code ${code}`);
    pythonProcess = null;
    // Optional: Send a message back to the React UI that the process stopped
    mainWindow.webContents.send('engine-stopped');
  });
});

// Listen for the 'stop-local-engine' signal
ipcMain.on('stop-local-engine', () => {
  if (pythonProcess) {
    console.log('[Main Process] Received signal to stop local engine. Terminating...');
    pythonProcess.kill();
    pythonProcess = null;
  }
});


// --- Electron App Lifecycle ---
app.on('ready', createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
  }
});

// Make sure to kill the python process when the app quits
app.on('will-quit', () => {
  if (pythonProcess) {
    pythonProcess.kill();
  }
});