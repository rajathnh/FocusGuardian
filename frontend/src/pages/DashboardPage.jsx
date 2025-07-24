// src/pages/DashboardPage.jsx

import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { useNavigate, Link } from 'react-router-dom';
import Navbar from '../components/Navbar';
import Footer from '../components/Footer';
import Chatbot from '../components/Chatbot';
import './dashboard.css';

const API_URL = process.env.REACT_APP_API_BASE_URL;

// Axios instance with token (NO CHANGE)
const createAuthAxiosInstance = () => {
  const instance = axios.create();
  const token = localStorage.getItem('focusGuardianToken');
  if (token) {
    instance.defaults.headers.common['Authorization'] = `Bearer ${token}`;
  }
  return instance;
};
const authAxios = createAuthAxiosInstance();


export default function DashboardPage() {
  const navigate = useNavigate();

  // --- STATE ---
  const [user, setUser] = useState(null);
  const [activeSession, setActiveSession] = useState(null);
  const [loadingInitial, setLoadingInitial] = useState(true);
  const [loadingAction, setLoadingAction] = useState(false);
  const [error, setError] = useState(null);
  const [elapsedTime, setElapsedTime] = useState(0);
  
  // --- NEW STATE for handshake ---
  const [isEngineInitializing, setIsEngineInitializing] = useState(false);

  // --- REFS ---
  const elapsedTimerIntervalRef = useRef(null);
  const isSessionRunningRef = useRef(false);

  // --- REMOVED STATE & REFS for Groq ---
  // const [latestAnalysis, setLatestAnalysis] = useState(null); // No longer needed, server handles this
  // const [streamsActive, setStreamsActive] = useState(false); // No longer needed
  // const webcamVideoRef = useRef(null); // No longer needed
  // const screenVideoRef = useRef(null); // No longer needed
  // const canvasRef = useRef(null); // No longer needed
  // const captureIntervalRef = useRef(null); // No longer needed
  // const webcamStreamRef = useRef(null); // No longer needed
  // const screenStreamRef = useRef(null); // No longer needed

  // --- FUNCTIONS ---

  const handleLogout = useCallback(() => {
    // Stop the python engine if it's running
    if (window.electronAPI) {
      window.electronAPI.stopLocalEngine();
    }
    isSessionRunningRef.current = false;
    clearInterval(elapsedTimerIntervalRef.current);
    setActiveSession(null);
    setElapsedTime(0);
    localStorage.removeItem('focusGuardianToken');
    localStorage.removeItem('focusGuardianUser');
    setUser(null);
    navigate('/login');
  }, [navigate]);

  // --- REVISED handleStartSession ---
  const handleStartSession = useCallback(async () => {
    if (activeSession || isSessionRunningRef.current) return;
    setError(null);
    setLoadingAction(true);
    setIsEngineInitializing(true); // Set initializing state to true

    try {
      const res = await authAxios.post(`${API_URL}/api/sessions/start`);
      if (!res.data.sessionId) throw new Error("No session ID returned from server");
      
      const sessionId = res.data.sessionId;
      const token = localStorage.getItem('focusGuardianToken');

      if (window.electronAPI) {
        console.log("Electron API found. Sending 'start' signal to main process...");
        window.electronAPI.startLocalEngine(sessionId, token);
        // We now wait for the 'engine-ready' signal instead of immediately setting the session active
      } else {
        setError("This feature is only available in the desktop application.");
        setIsEngineInitializing(false); // Reset state on error
        setLoadingAction(false);
        throw new Error("Electron API not available.");
      }
    } catch (err) {
      setError(`Start Failed: ${err.message}`);
      setIsEngineInitializing(false); // Reset state on error
      setLoadingAction(false);
    }
    // Note: finally block is removed so loadingAction stays true during initialization
  }, [activeSession]);


  // --- REVISED handleStopSession ---
  const handleStopSession = useCallback(async () => {
    const sessionId = activeSession?._id;
    if (!sessionId) return;

    setError(null);
    setLoadingAction(true);

    if (window.electronAPI) {
      console.log("Sending 'stop' signal to main process...");
      window.electronAPI.stopLocalEngine();
    }

    isSessionRunningRef.current = false;
    clearInterval(elapsedTimerIntervalRef.current);
    setActiveSession(null);
    setElapsedTime(0);

    try {
      await authAxios.post(`${API_URL}/api/sessions/${sessionId}/stop`);
    } catch (err) {
      setError(`Failed to notify backend: ${err.response?.data?.message || err.message}`);
    } finally {
      setLoadingAction(false);
    }
  }, [activeSession]);

  // --- REMOVED `captureAndSend` function entirely, it is no longer needed ---

  // --- useEffects ---

  // Initial load effect (NO CHANGE)
  useEffect(() => {
    let mounted = true;
    setLoadingInitial(true);
    setError(null);
    const load = async () => {
      const token = localStorage.getItem('focusGuardianToken');
      if (!token) {
        if (mounted) handleLogout();
        return;
      }
      if (!authAxios.defaults.headers.common['Authorization']) {
        authAxios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
      }
      try {
        const userPromise = authAxios.get(`${API_URL}/api/users/profile`);
        const sessionPromise = authAxios.get(`${API_URL}/api/sessions/current`)
          .catch(e => e.response?.status === 404 ? { data: null } : Promise.reject(e));
        const [uRes, sRes] = await Promise.all([userPromise, sessionPromise]);
        if (!mounted) return;
        setUser(uRes.data);
        if (sRes.data) {
          // If a session is found on load, we assume the engine is NOT running and needs a restart.
          setError("An unterminated session was found. Please stop and restart it.");
          setActiveSession(sRes.data); // Show it so the user can stop it
          isSessionRunningRef.current = true; // Set this so timer appears
        } else {
          setActiveSession(null);
          isSessionRunningRef.current = false;
        }
      } catch (err) {
        if (!mounted) return;
        if (err.response?.status === 401) handleLogout();
        else setError(`Could not load dashboard data: ${err.message}`);
      } finally {
        if (mounted) setLoadingInitial(false);
      }
    };
    load();
    return () => { mounted = false; };
  }, [handleLogout]);

  // --- NEW useEffect for Electron IPC listeners ---
  useEffect(() => {
    // Guard clause if not in Electron
    if (!window.electronAPI) return;

    const handleEngineReady = () => {
      console.log("React: Received engine-ready signal!");
      // Fetch the session details to ensure we have the correct startTime from the DB
      const fetchCurrentSession = async () => {
        try {
          const res = await authAxios.get(`${API_URL}/api/sessions/current`);
          if (res.data) {
            setActiveSession(res.data);
            isSessionRunningRef.current = true;
            setIsEngineInitializing(false);
            setLoadingAction(false);
          } else {
             // This can happen in a race condition if the session was stopped very quickly
             handleStopSession();
          }
        } catch (err) {
          setError("Engine ready, but failed to sync session. Please stop and restart.");
          setIsEngineInitializing(false);
          setLoadingAction(false);
        }
      };
      fetchCurrentSession();
    };

    const handleEngineFailed = () => {
      console.error("React: Received engine-failed signal!");
      setError("The local analysis engine failed to start. Check terminal for errors.");
      setIsEngineInitializing(false);
      setLoadingAction(false);
      // Attempt to stop the session on the backend since it won't be monitored
      authAxios.get(`${API_URL}/api/sessions/current`).then(res => {
          if (res.data?._id) {
              authAxios.post(`${API_URL}/api/sessions/${res.data._id}/stop`);
          }
      });
      setActiveSession(null);
    };

    // Setup listeners
    const removeReadyListener = window.electronAPI.onEngineReady(handleEngineReady);
    const removeFailedListener = window.electronAPI.onEngineFailed(handleEngineFailed);

    // Cleanup: It's good practice to have a way to remove listeners.
    // Assuming preload.js might not return a remover, but this is the ideal pattern.
    return () => {
      // if (removeReadyListener) removeReadyListener();
      // if (removeFailedListener) removeFailedListener();
    };
  }, [handleStopSession]); // handleStopSession is a dependency

  // Elapsed timer effect (NO CHANGE)
  useEffect(() => {
    clearInterval(elapsedTimerIntervalRef.current);
    if (activeSession && isSessionRunningRef.current) {
      const start = new Date(activeSession.startTime);
      const tick = () => {
        setElapsedTime(Math.floor((new Date() - start) / 1000));
      };
      tick();
      elapsedTimerIntervalRef.current = setInterval(tick, 1000);
    } else {
      setElapsedTime(0);
    }
    return () => clearInterval(elapsedTimerIntervalRef.current);
  }, [activeSession]);


  // --- Helper Functions ---
  const formatElapsed = secs => {
    if (isNaN(secs) || secs < 0) return '00:00:00';
    const h = String(Math.floor(secs / 3600)).padStart(2, '0');
    const m = String(Math.floor((secs % 3600) / 60)).padStart(2, '0');
    const s = String(secs % 60).padStart(2, '0');
    return `${h}:${m}:${s}`;
  };

  // --- Render Logic ---
  if (loadingInitial) {
    return <div style={{ padding: '20px', textAlign: 'center', fontSize: '1.2em' }}>Loading Dashboard...</div>;
  }

  return (
    <div className="dashboard-page">
      <Navbar />
      <div className="dashboard-container">
        <header className="dashboard-header">
          <h1>Focus Guardian Dashboard</h1>
          <div className="user-info">
            <span className="user-greeting">
              Welcome back, {user?.name || user?.email || 'User'}!
            </span>
            <button onClick={handleLogout} disabled={loadingAction} className="btn btn-primary">
              Logout
            </button>
          </div>
        </header>

        {error && (
          <div className="error-alert">
            <span>{error}</span>
            <button onClick={() => setError(null)}>×</button>
          </div>
        )}
        
        <section className="session-card">
          <div className="session-status">
            {activeSession && !isEngineInitializing && (
              <>
                <span className="session-active">Session Active</span>
                <span className="session-id">ID: ...{activeSession._id.slice(-6)}</span>
              </>
            )}
             {isEngineInitializing && (
                <p>Initializing Analysis Engine...</p>
            )}
            {!activeSession && !isEngineInitializing && (
              <p>No active session.</p>
            )}
          </div>

          {activeSession ? (
            <>
              <div className="timer-display">{formatElapsed(elapsedTime)}</div>
              <div className="btn-group">
                <button
                  onClick={handleStopSession}
                  disabled={loadingAction}
                  className="btn btn-danger"
                >
                  {loadingAction ? 'Stopping...' : 'Stop Session'}
                </button>
              </div>
            </>
          ) : (
            <button
              onClick={handleStartSession}
              disabled={loadingAction || isEngineInitializing}
              className="btn btn-success"
            >
              {loadingAction && !isEngineInitializing && 'Starting...'}
              {isEngineInitializing && 'Initializing Engine...'}
              {!loadingAction && !isEngineInitializing && 'Start New Session'}
            </button>
          )}
        </section>

        {/* This section for analysis results is no longer needed as we don't get live results back */}
        {/* We can repurpose it later to poll the backend for the latest data point if desired */}
        {/*
        {activeSession && (
          <section className="analysis-card">
            <h2>Latest Analysis</h2>
            ...
          </section>
        )}
        */}

        <div className="session-history-link" style={{ marginBottom: '20px', textAlign: 'center' }}>
          <Link to="/session" className="btn btn-secondary">
            View Session History & Analytics →
          </Link>
        </div>
        
        <section className="chatbot-section">
          <h2>Productivity Assistant</h2>
          <div className="chatbot-content">
            <Chatbot />
          </div>
        </section>
      </div>

      {/* The hidden video/canvas elements are no longer needed for this component */}
      {/* 
      <div style={{ display: 'none' }}>
        <video ref={webcamVideoRef} ... />
        <video ref={screenVideoRef} ... />
        <canvas ref={canvasRef} ... />
      </div>
      */}

      <Footer />
    </div>
  );
}