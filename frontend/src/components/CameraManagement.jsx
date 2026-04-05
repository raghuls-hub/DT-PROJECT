import React, { useState, useEffect } from 'react';

const API = 'http://localhost:8000';

const CameraManagement = ({ cameras, onCamerasChange }) => {
  const [name, setName] = useState('');
  const [url, setUrl]   = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleAdd = async () => {
    if (!name.trim() || !url.trim()) {
      setError('Both name and URL are required.');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const res = await fetch(`${API}/cameras`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), url: url.trim() }),
      });
      if (!res.ok) throw new Error('Failed to add camera.');
      const added = await res.json();
      onCamerasChange([...cameras, added]);
      setName('');
      setUrl('');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (cam) => {
    try {
      await fetch(`${API}/cameras/${cam._id}`, { method: 'DELETE' });
      onCamerasChange(cameras.filter(c => c._id !== cam._id));
    } catch (err) {
      console.error('Delete failed:', err);
    }
  };

  return (
    <div>
      <div className="section-header">
        <h1 className="section-title">Camera Management</h1>
        <p className="section-subtitle">Add and manage your CCTV camera sources. Cameras are persisted to the database.</p>
      </div>

      {/* Add Form */}
      <div className="glass-card add-camera-form">
        <div className="form-group">
          <label className="form-label">Camera Name</label>
          <input
            id="camera-name-input"
            className="form-input"
            placeholder="e.g. Entrance Gate"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
          />
        </div>
        <div className="form-group" style={{ flex: 2 }}>
          <label className="form-label">Stream URL</label>
          <input
            id="camera-url-input"
            className="form-input"
            placeholder="http://127.0.0.1:5000/stream/video.mp4  or  rtsp://..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
          />
        </div>
        <button
          id="add-camera-btn"
          className="btn btn-primary"
          onClick={handleAdd}
          disabled={loading}
          style={{ alignSelf: 'flex-end' }}
        >
          {loading ? '⏳ Adding...' : '+ Add Camera'}
        </button>
      </div>
      {error && <p style={{ color: 'var(--danger)', fontSize: '13px', marginBottom: '16px', paddingLeft: '4px' }}>⚠ {error}</p>}

      {/* Camera List */}
      <div className="glass-card camera-list">
        <div className="camera-list-header">
          <span className="camera-list-col">Name</span>
          <span className="camera-list-col">Stream URL</span>
          <span className="camera-list-col">Actions</span>
        </div>

        {cameras.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📷</div>
            <div className="empty-title">No cameras yet</div>
            <div className="empty-desc">Add a camera above to get started.</div>
          </div>
        ) : (
          cameras.map((cam) => (
            <div className="camera-row" key={cam._id}>
              <div className="camera-name">
                <span className="cam-dot" style={{ background: 'var(--accent)' }}></span>
                {cam.name}
              </div>
              <div className="camera-url-cell" title={cam.url}>{cam.url}</div>
              <div className="camera-actions">
                <button
                  id={`delete-cam-${cam._id}`}
                  className="btn btn-danger btn-sm"
                  onClick={() => handleDelete(cam)}
                >
                  🗑 Delete
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default CameraManagement;
