import React, { useState, useEffect } from 'react';
import CameraManagement from './components/CameraManagement';
import CameraStream from './components/CameraStream';
import './index.css';

const API = 'http://localhost:8000';

function App() {
  const [tab, setTab]         = useState('manage'); // 'manage' | 'monitor'
  const [cameras, setCameras] = useState([]);
  const [loadError, setLoadError] = useState('');

  // Load all cameras from MongoDB on mount
  useEffect(() => {
    fetch(`${API}/cameras`)
      .then(r => r.json())
      .then(data => setCameras(data))
      .catch(() => setLoadError('⚠ Could not reach backend. Is uvicorn running?'));
  }, []);

  return (
    <div className="app-shell">
      {/* ── Header ── */}
      <header className="app-header">
        <div className="header-logo">
          <div className="header-logo-icon">🛡</div>
          <span>SmartSafety<span style={{ color: 'var(--accent)', fontWeight: 800 }}>AI</span></span>
        </div>
        <div className="header-divider" />
        <span className="header-badge">● System Online</span>
      </header>

      {/* ── Tab Bar ── */}
      <nav className="tab-nav">
        <button
          id="tab-manage"
          className={`tab-btn ${tab === 'manage' ? 'active' : ''}`}
          onClick={() => setTab('manage')}
        >
          <span className="tab-icon">⚙️</span>
          Camera Management
          <span className="tab-count">{cameras.length}</span>
        </button>
        <button
          id="tab-monitor"
          className={`tab-btn ${tab === 'monitor' ? 'active' : ''}`}
          onClick={() => setTab('monitor')}
        >
          <span className="tab-icon">📹</span>
          Live Monitoring
          <span className="tab-count">{cameras.length}</span>
        </button>
      </nav>

      {/* ── Page Content ── */}
      <main className="page-content">
        {loadError && (
          <div style={{ color: 'var(--danger)', marginBottom: '20px', fontSize: '14px' }}>{loadError}</div>
        )}

        {tab === 'manage' && (
          <CameraManagement cameras={cameras} onCamerasChange={setCameras} />
        )}

        {tab === 'monitor' && (
          <div>
            <div className="section-header">
              <h1 className="section-title">Live Monitoring</h1>
              <p className="section-subtitle">
                {cameras.length === 0
                  ? 'No cameras found. Add cameras in the Camera Management tab.'
                  : `${cameras.length} camera${cameras.length > 1 ? 's' : ''} available. Press Start on any feed to begin AI analysis.`}
              </p>
            </div>

            {cameras.length === 0 ? (
              <div className="glass-card">
                <div className="empty-state">
                  <div className="empty-icon">📡</div>
                  <div className="empty-title">No cameras configured</div>
                  <div className="empty-desc">Go to Camera Management to add your first camera.</div>
                </div>
              </div>
            ) : (
              <div className="monitor-grid">
                {cameras.map((cam) => (
                  <CameraStream key={cam._id} camera={cam} />
                ))}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
