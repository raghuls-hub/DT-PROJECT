import React, { useState, useEffect } from 'react';
import CameraManagement from './components/CameraManagement';
import CameraStream from './components/CameraStream';
import WorkerManagement from './components/WorkerManagement';
import AttendanceScanner from './components/AttendanceScanner';
import './index.css';
import './modals.css';

const API = 'http://localhost:8000';

function App() {
  const [tab, setTab]         = useState('manage');
  const [cameras, setCameras] = useState([]);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    fetch(`${API}/cameras`)
      .then(r => r.json())
      .then(data => setCameras(data))
      .catch(() => setLoadError('⚠ Could not reach backend. Is uvicorn running?'));
  }, []);

  const tabs = [
    { id: 'manage',    icon: '⚙️',  label: 'Camera Management', count: cameras.length },
    { id: 'monitor',   icon: '📹',  label: 'Live Monitoring',   count: cameras.length },
    { id: 'workers',   icon: '👷',  label: 'Workers',           count: null },
    { id: 'scanner',   icon: '📱',  label: 'QR Scanner',        count: null },
  ];

  return (
    <div className="app-shell">
      {/* Header */}
      <header className="app-header">
        <div className="header-logo">
          <div className="header-logo-icon">🛡</div>
          <span>SmartSafety<span style={{ color: 'var(--accent)', fontWeight: 800 }}>AI</span></span>
        </div>
        <div className="header-divider" />
        <span className="header-badge">● System Online</span>
      </header>

      {/* Tabs */}
      <nav className="tab-nav">
        {tabs.map(t => (
          <button
            key={t.id}
            id={`tab-${t.id}`}
            className={`tab-btn ${tab === t.id ? 'active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            <span className="tab-icon">{t.icon}</span>
            {t.label}
            {t.count !== null && <span className="tab-count">{t.count}</span>}
          </button>
        ))}
      </nav>

      {/* Content */}
      <main className="page-content">
        {loadError && (
          <div style={{ color: 'var(--danger)', marginBottom: 20, fontSize: 14 }}>{loadError}</div>
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
                  : `${cameras.length} camera${cameras.length > 1 ? 's' : ''} available. Press Start to begin AI analysis.`}
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
                {cameras.map(cam => (
                  <CameraStream key={cam._id} camera={cam} />
                ))}
              </div>
            )}
          </div>
        )}

        {tab === 'workers' && <WorkerManagement />}

        {tab === 'scanner' && <AttendanceScanner />}
      </main>
    </div>
  );
}

export default App;
