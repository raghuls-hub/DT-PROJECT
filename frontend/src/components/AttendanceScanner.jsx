import React, { useState, useEffect, useRef, useCallback } from 'react';
import jsQR from 'jsqr';

const API = 'http://localhost:8000';

/* ─── Toast Notification ────────────────────────────────────────────────────── */
const Toast = ({ toasts }) => (
  <div style={{ position: 'fixed', top: 24, right: 24, zIndex: 9999, display: 'flex', flexDirection: 'column', gap: 10 }}>
    {toasts.map(t => (
      <div key={t.id} style={{
        padding: '14px 20px', borderRadius: 10, minWidth: 280, maxWidth: 380,
        fontWeight: 500, fontSize: 14, boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
        background: t.type === 'success' ? 'rgba(34,197,94,0.15)'
                  : t.type === 'warn'    ? 'rgba(245,158,11,0.15)'
                  :                        'rgba(239,68,68,0.15)',
        border: `1px solid ${t.type === 'success' ? 'rgba(34,197,94,0.4)' : t.type === 'warn' ? 'rgba(245,158,11,0.4)' : 'rgba(239,68,68,0.4)'}`,
        color: t.type === 'success' ? '#4ade80' : t.type === 'warn' ? '#fbbf24' : '#f87171',
        backdropFilter: 'blur(12px)',
        animation: 'slide-in 0.3s ease',
      }}>
        {t.type === 'success' ? '✅' : t.type === 'warn' ? '⚠️' : '❌'} {t.message}
      </div>
    ))}
  </div>
);

/* ─── QR Attendance Scanner ─────────────────────────────────────────────────── */
const AttendanceScanner = () => {
  const videoRef   = useRef(null);
  const canvasRef  = useRef(null);
  const rafRef     = useRef(null);
  const cooldownRef = useRef(false);  // Prevents repeated scans of same QR

  const [scanning, setScanning] = useState(false);
  const [cameraError, setCameraError] = useState('');
  const [todayRecords, setTodayRecords] = useState([]);
  const [toasts, setToasts] = useState([]);
  const [lastScanned, setLastScanned] = useState('');

  const addToast = (message, type = 'success') => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 4500);
  };

  const fetchTodayAttendance = async () => {
    try {
      const r = await fetch(`${API}/attendance/today`);
      if (r.ok) setTodayRecords(await r.json());
    } catch { /* silently fail */ }
  };

  useEffect(() => {
    fetchTodayAttendance();
    const interval = setInterval(fetchTodayAttendance, 10000); // refresh every 10s
    return () => clearInterval(interval);
  }, []);

  const startCamera = async () => {
    setCameraError('');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
        setScanning(true);
        scanLoop();
      }
    } catch (err) {
      if (err.name === 'NotAllowedError') {
        setCameraError('Camera access denied. Please allow camera permission in your browser settings.');
      } else if (err.name === 'NotFoundError') {
        setCameraError('No camera found on this device.');
      } else {
        setCameraError(`Camera error: ${err.message}`);
      }
    }
  };

  const stopCamera = () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    if (videoRef.current?.srcObject) {
      videoRef.current.srcObject.getTracks().forEach(t => t.stop());
      videoRef.current.srcObject = null;
    }
    setScanning(false);
    setLastScanned('');
    cooldownRef.current = false;
  };

  const handleScan = useCallback(async (qrData) => {
    if (cooldownRef.current || qrData === lastScanned) return;
    cooldownRef.current = true;
    setLastScanned(qrData);

    try {
      const res = await fetch(`${API}/attendance/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ qr_data: qrData }),
      });
      const data = await res.json();

      if (res.status === 200) {
        addToast(data.message, 'success');
        fetchTodayAttendance();
      } else if (res.status === 404) {
        addToast(data.detail || 'QR code not registered in system.', 'error');
      } else if (res.status === 409) {
        addToast(data.detail, 'warn');
      } else {
        addToast(data.detail || 'Unexpected error.', 'error');
      }
    } catch {
      addToast('Network error. Cannot reach backend.', 'error');
    }

    // Cooldown for 3 seconds to avoid re-scanning
    setTimeout(() => {
      cooldownRef.current = false;
      setLastScanned('');
    }, 3000);
  }, [lastScanned]);

  const scanLoop = useCallback(() => {
    const video  = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2) {
      rafRef.current = requestAnimationFrame(scanLoop);
      return;
    }
    canvas.width  = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const code = jsQR(imageData.data, imageData.width, imageData.height, {
      inversionAttempts: 'dontInvert',
    });
    if (code && code.data) {
      handleScan(code.data);
    }
    rafRef.current = requestAnimationFrame(scanLoop);
  }, [handleScan]);

  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, []);

  return (
    <div>
      <Toast toasts={toasts} />

      <div className="section-header">
        <h1 className="section-title">QR Attendance Scanner</h1>
        <p className="section-subtitle">Point a worker's QR code at the camera to mark their attendance for today.</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: 24, alignItems: 'start' }}>
        {/* Scanner Panel */}
        <div className="glass-card" style={{ overflow: 'hidden' }}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--glass-border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontWeight: 600 }}>📷 Live Scanner</span>
            <div style={{ display: 'flex', gap: 8 }}>
              {!scanning ? (
                <button id="start-scanner-btn" className="btn btn-success btn-sm" onClick={startCamera}>
                  ▶ Start Camera
                </button>
              ) : (
                <button id="stop-scanner-btn" className="btn btn-danger btn-sm" onClick={stopCamera}>
                  ⏹ Stop Camera
                </button>
              )}
            </div>
          </div>

          <div style={{ position: 'relative', background: '#000', minHeight: 360, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <video ref={videoRef} autoPlay playsInline muted
              style={{ width: '100%', display: scanning ? 'block' : 'none', maxHeight: 480, objectFit: 'cover' }} />
            <canvas ref={canvasRef} style={{ display: 'none' }} />

            {/* Scanner crosshair overlay */}
            {scanning && (
              <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', pointerEvents: 'none' }}>
                <div style={{ width: 180, height: 180, border: '2px solid rgba(59,130,246,0.8)', borderRadius: 12, boxShadow: '0 0 0 9999px rgba(0,0,0,0.35)', position: 'relative' }}>
                  {/* Corner accents */}
                  {[['0','0'], ['0','auto'], ['auto','0'], ['auto','auto']].map(([t,b], i) => (
                    <div key={i} style={{ position: 'absolute', top: t !== 'auto' ? -2 : 'auto', bottom: b !== 'auto' ? -2 : 'auto', left: i < 2 ? -2 : 'auto', right: i >= 2 ? -2 : 'auto', width: 20, height: 20, borderColor: 'var(--accent)', borderStyle: 'solid', borderWidth: i === 0 ? '3px 0 0 3px' : i === 1 ? '0 0 3px 3px' : i === 2 ? '3px 3px 0 0' : '0 3px 3px 0', borderRadius: i === 0 ? '4px 0 0 0' : i === 1 ? '0 0 0 4px' : i === 2 ? '0 4px 0 0' : '0 0 4px 0' }} />
                  ))}
                  {/* Scan line */}
                  <div style={{ position: 'absolute', left: 0, right: 0, height: 2, background: 'var(--accent)', animation: 'scan-line 1.8s ease-in-out infinite', boxShadow: '0 0 8px var(--accent)' }} />
                </div>
              </div>
            )}

            {!scanning && (
              <div style={{ textAlign: 'center', color: 'var(--text-3)' }}>
                {cameraError ? (
                  <div style={{ padding: 24 }}>
                    <div style={{ fontSize: 36, marginBottom: 12 }}>🚫</div>
                    <div style={{ color: 'var(--danger)', fontSize: 14, maxWidth: 300 }}>{cameraError}</div>
                  </div>
                ) : (
                  <div style={{ padding: 48 }}>
                    <div style={{ fontSize: 48, marginBottom: 12 }}>📷</div>
                    <div style={{ fontSize: 14 }}>Press "Start Camera" to begin scanning</div>
                  </div>
                )}
              </div>
            )}
          </div>

          {lastScanned && (
            <div style={{ padding: '10px 20px', borderTop: '1px solid var(--glass-border)', fontSize: 12, color: 'var(--text-3)', fontFamily: 'monospace' }}>
              Last scanned: {lastScanned}
            </div>
          )}
        </div>

        {/* Today's Attendance Log */}
        <div className="glass-card" style={{ maxHeight: 520, display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--glass-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontWeight: 600, fontSize: 14 }}>📋 Today's Log</span>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>{new Date().toLocaleDateString()}</span>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {todayRecords.length === 0 ? (
              <div style={{ padding: '40px 20px', textAlign: 'center' }}>
                <div style={{ fontSize: 32, marginBottom: 8, opacity: 0.4 }}>🕐</div>
                <div style={{ color: 'var(--text-3)', fontSize: 13 }}>No attendance marked today</div>
              </div>
            ) : todayRecords.map(r => (
              <div key={r._id} style={{ padding: '12px 18px', borderBottom: '1px solid var(--glass-border)', display: 'flex', flexDirection: 'column', gap: 2 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{r.name}</span>
                  <span style={{ fontSize: 11, color: 'var(--success)', fontWeight: 600 }}>✓ {r.status}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{r.department}</span>
                  <span style={{ fontSize: 11, color: 'var(--text-2)' }}>{r.time}</span>
                </div>
              </div>
            ))}
          </div>
          <div style={{ padding: '10px 18px', borderTop: '1px solid var(--glass-border)', fontSize: 12, color: 'var(--text-2)' }}>
            {todayRecords.length} present today
          </div>
        </div>
      </div>

      <style>{`
        @keyframes scan-line {
          0%   { top: 0; }
          50%  { top: calc(100% - 2px); }
          100% { top: 0; }
        }
        @keyframes slide-in {
          from { opacity: 0; transform: translateX(20px); }
          to   { opacity: 1; transform: translateX(0); }
        }
      `}</style>
    </div>
  );
};

export default AttendanceScanner;
