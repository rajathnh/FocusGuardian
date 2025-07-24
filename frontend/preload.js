// In: frontend/preload.js
const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods that allow the renderer process (React app)
// to communicate with the main process.
contextBridge.exposeInMainWorld('electronAPI', {
  // Function to start the python script
    // Listener for when the Python engine is successfully initialized
  onEngineReady: (callback) => ipcRenderer.on('engine-ready', callback),
  // Listener for when the Python engine fails to initialize
  onEngineFailed: (callback) => ipcRenderer.on('engine-failed', callback),
  // Listener for when the Python process stops unexpectedly
  onEngineStopped: (callback) => ipcRenderer.on('engine-stopped', callback),

  startLocalEngine: (sessionId, token) => {
    console.log('Preload: Sending start-local-engine signal');
    ipcRenderer.send('start-local-engine', { sessionId, token });
  },
  
  // Function to stop the python script
  stopLocalEngine: () => {
    console.log('Preload: Sending stop-local-engine signal');
    ipcRenderer.send('stop-local-engine');
  },
  
  // (Optional but good) A way for the main process to send messages TO the React app
  onEngineStopped: (callback) => ipcRenderer.on('engine-stopped', callback)
});