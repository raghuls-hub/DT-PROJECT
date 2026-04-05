import React, { useEffect, useRef, useState } from 'react';

const API = 'http://localhost:8000';

const CameraStream = ({ camera, onDelete }) => {
  const videoRef = useRef(null);
  const pcRef    = useRef(null);
  const [status, setStatus]   = useState('idle'); // idle | connecting | connected | error
  const [active, setActive]   = useState(false);

  const startStream = async () => {
    setStatus('connecting');
    setActive(true);
    const pc = new RTCPeerConnection();
    pcRef.current = pc;

    pc.addTransceiver('video', { direction: 'recvonly' });

    pc.ontrack = (event) => {
      if (videoRef.current && event.streams?.[0]) {
        videoRef.current.srcObject = event.streams[0];
        setStatus('connected');
      }
    };

    pc.onconnectionstatechange = () => {
      if (pc.connectionState === 'failed' || pc.connectionState === 'disconnected') {
        setStatus('error');
      }
    };

    try {
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      const res = await fetch(`${API}/offer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sdp: pc.localDescription.sdp,
          type: pc.localDescription.type,
          camera_url: camera.url,
        }),
      });

      if (!res.ok) throw new Error('Backend signaling failed.');
      const answer = await res.json();
      await pc.setRemoteDescription(new RTCSessionDescription(answer));
    } catch (err) {
      console.error('[WebRTC Error]:', err);
      setStatus('error');
    }
  };

  const stopStream = () => {
    if (pcRef.current) {
      pcRef.current.close();
      pcRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    // Tell backend to release the thread
    fetch(`${API}/close_camera`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ camera_url: camera.url }),
    }).catch(() => {});
    setStatus('idle');
    setActive(false);
  };

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (pcRef.current) pcRef.current.close();
    };
  }, []);

  return (
    <div className="camera-card">
      {/* Header */}
      <div className="camera-card-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1, overflow: 'hidden' }}>
          <span className={`status-dot ${status}`}></span>
          <span className="camera-card-title">{camera.name}</span>
          <span className="camera-card-url">{camera.url}</span>
        </div>
        <div className="camera-card-controls">
          <span className={`status-text ${status}`}>
            {status === 'idle' ? 'Idle' : status === 'connecting' ? 'Connecting…' : status === 'connected' ? 'Live' : 'Error'}
          </span>
          {!active ? (
            <button id={`start-${camera._id}`} className="btn btn-success btn-sm" onClick={startStream}>
              ▶ Start
            </button>
          ) : (
            <button id={`stop-${camera._id}`} className="btn btn-ghost btn-sm" onClick={stopStream}>
              ⏹ Stop
            </button>
          )}
        </div>
      </div>

      {/* Video */}
      <div className="video-wrapper">
        <video ref={videoRef} autoPlay playsInline muted controls={false} />
        {!active && (
          <div className="video-placeholder">
            <div className="video-placeholder-icon">📷</div>
            <div className="video-placeholder-text">Press Start to connect</div>
          </div>
        )}
      </div>
    </div>
  );
};

export default CameraStream;
