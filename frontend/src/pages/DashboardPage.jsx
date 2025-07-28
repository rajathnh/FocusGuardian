// src/pages/DashboardPage.jsx

import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { useNavigate, Link } from 'react-router-dom';
import Navbar from '../components/Navbar';
import Footer from '../components/Footer';
import Chatbot from '../components/Chatbot';
import './dashboard.css';

const API_URL = process.env.REACT_APP_API_BASE_URL;

const createAuthAxiosInstance = () => {
  const instance = axios.create();
  const token = localStorage.getItem('focusGuardianToken');
  if (token) instance.defaults.headers.common['Authorization'] = `Bearer ${token}`;
  return instance;
};
const authAxios = createAuthAxiosInstance();

export default function DashboardPage() {
  const navigate = useNavigate();

  const [user, setUser] = useState(null);
  const [activeSession, setActiveSession] = useState(null);
  const [loadingInitial, setLoadingInitial] = useState(true);
  const [loadingAction, setLoadingAction] = useState(false);
  const [error, setError] = useState(null);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [isEngineInitializing, setIsEngineInitializing] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [isTrackingActive, setIsTrackingActive] = useState(false);

  const elapsedTimerIntervalRef = useRef(null);
  const sessionPlaceholderRef = useRef(null);

  const handleLogout = useCallback(() => {
    if (window.electronAPI) window.electronAPI.stopLocalEngine();
    clearInterval(elapsedTimerIntervalRef.current);
    localStorage.removeItem('focusGuardianToken');
    localStorage.removeItem('focusGuardianUser');
    setActiveSession(null);
    setElapsedTime(0);
    setUser(null);
    setError(null);
    setIsTrackingActive(false);
    navigate('/login');
  }, [navigate]);

  const handleStartSession = useCallback(async () => {
    if (isStarting || activeSession) return;
    setError(null);
    setIsStarting(true);
    setIsEngineInitializing(true);
    setLoadingAction(true);
    setIsTrackingActive(false);

    try {
      const res = await authAxios.post(`${API_URL}/api/sessions/start`);
      const placeholderSession = res.data.session;
      if (!placeholderSession?._id) throw new Error("No session placeholder returned");
      
      sessionPlaceholderRef.current = placeholderSession;
      
      const token = localStorage.getItem('focusGuardianToken');
      if (window.electronAPI) {
        window.electronAPI.startLocalEngine(placeholderSession._id, token);
      } else {
        throw new Error("Desktop application environment not found.");
      }
    } catch (err) {
      setError(`Start Failed: ${err.response?.data?.message || err.message}`);
      setIsEngineInitializing(false);
      setLoadingAction(false);
    } finally {
      setIsStarting(false);
    }
  }, [activeSession, isStarting]);

  const handleStopSession = useCallback(async () => {
    const sessionId = activeSession?._id;
    if (!sessionId) return;
    setError(null);
    setLoadingAction(true);
    if (window.electronAPI) window.electronAPI.stopLocalEngine();
    setIsTrackingActive(false);
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

  useEffect(() => {
    let mounted = true;
    const loadDashboard = async () => {
        setLoadingInitial(true);
        const token = localStorage.getItem('focusGuardianToken');
        if (!token) { if (mounted) handleLogout(); return; }
        try {
            const userRes = await authAxios.get(`${API_URL}/api/users/profile`);
            if (!mounted) return;
            setUser(userRes.data);
            const sessionRes = await authAxios.get(`${API_URL}/api/sessions/current`).catch(() => null);
            if (mounted && sessionRes?.data) {
                setError("An unterminated session was found. Please stop it before starting a new one.");
                setActiveSession(sessionRes.data);
                setIsTrackingActive(true);
            }
        } catch (err) {
            if (mounted && err.response?.status === 401) handleLogout();
        } finally {
            if (mounted) setLoadingInitial(false);
        }
    };
    loadDashboard();
    return () => { mounted = false; };
  }, [handleLogout]);

  // Corrected Electron IPC listeners useEffect
  useEffect(() => {
    if (!window.electronAPI) return;

    const handleEngineReady = async () => {
      console.log("React: Engine is ready. Activating session on backend...");
      const placeholder = sessionPlaceholderRef.current;
      if (!placeholder) {
        setError("Error: Session placeholder missing. Please restart.");
        setIsEngineInitializing(false);
        setLoadingAction(false);
        return;
      }
      try {
        const res = await authAxios.patch(`${API_URL}/api/sessions/${placeholder._id}/activate`);
        const finalSession = res.data.session;
        setActiveSession(finalSession);
        setIsTrackingActive(true);
        setIsEngineInitializing(false);
        setLoadingAction(false);
        sessionPlaceholderRef.current = null;
      } catch (err) {
        setError("Failed to activate session on the server. Please stop and restart.");
        setIsEngineInitializing(false);
        setLoadingAction(false);
      }
    };

    const handleEngineFailed = () => {
      console.error("React: Received engine-failed signal!");
      setError("The local analysis engine failed to start. Please check the terminal for errors.");
      setIsEngineInitializing(false);
      setLoadingAction(false);
      setIsTrackingActive(false);
    };

    // Set up listeners using the robust preload functions.
    // The preload.js now handles listener cleanup, so we don't need a return function here.
    window.electronAPI.onEngineReady(handleEngineReady);
    window.electronAPI.onEngineFailed(handleEngineFailed);

  }, []); // Empty dependency array is correct.

  // Timer effect
  useEffect(() => {
    clearInterval(elapsedTimerIntervalRef.current);
    if (activeSession && isTrackingActive) {
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
  }, [activeSession, isTrackingActive]);

  const formatElapsed = secs => {
    if (isNaN(secs) || secs < 0) return '00:00:00';
    const h = String(Math.floor(secs / 3600)).padStart(2, '0');
    const m = String(Math.floor((secs % 3600) / 60)).padStart(2, '0');
    const s = String(secs % 60).padStart(2, '0');
    return `${h}:${m}:${s}`;
  };

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
            <span className="user-greeting">Welcome back, {user?.name || user?.email || 'User'}!</span>
            <button onClick={handleLogout} disabled={loadingAction} className="btn btn-primary">Logout</button>
          </div>
        </header>
        {error && (<div className="error-alert"><span>{error}</span><button onClick={() => setError(null)}>×</button></div>)}
        
        <section className="session-card">
          <div className="session-status">
            {activeSession && !isEngineInitializing && (
              <span className="session-active">Session Active</span>
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
              {isTrackingActive ? (
                  <div className="timer-display">{formatElapsed(elapsedTime)}</div>
              ) : (
                  <div className="timer-display">00:00:00</div>
              )}
              <div className="btn-group">
                <button onClick={handleStopSession} disabled={loadingAction} className="btn btn-danger">
                  {loadingAction ? 'Stopping...' : 'Stop Session'}
                </button>
              </div>
            </>
          ) : (
            <button
              onClick={handleStartSession}
              disabled={loadingAction || isEngineInitializing || isStarting}
              className="btn btn-success"
            >
              {isStarting ? 'Starting...' : 'Start New Session'}
            </button>
          )}
        </section>

        <div className="session-history-link" style={{ marginBottom: '20px', textAlign: 'center' }}>
          <Link to="/session" className="btn btn-secondary">View Session History & Analytics →</Link>
        </div>
        <section className="chatbot-section">
          <h2>Productivity Assistant</h2>
          <div className="chatbot-content"><Chatbot /></div>
        </section>
      </div>
      <Footer />
    </div>
  );
}