import React, { useState, useEffect, useRef, useCallback } from "react";
import jsQR from "jsqr";

const API = "http://localhost:8000";

/* ─── Toast Notification ────────────────────────────────────────────────────── */
const Toast = ({ toasts }) => (
  <div
    style={{
      position: "fixed",
      top: 24,
      right: 24,
      zIndex: 9999,
      display: "flex",
      flexDirection: "column",
      gap: 10,
    }}
  >
    {toasts.map((t) => (
      <div
        key={t.id}
        style={{
          padding: "14px 20px",
          borderRadius: 10,
          minWidth: 280,
          maxWidth: 380,
          fontWeight: 500,
          fontSize: 14,
          boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
          background:
            t.type === "success"
              ? "rgba(34,197,94,0.15)"
              : t.type === "warn"
                ? "rgba(245,158,11,0.15)"
                : "rgba(239,68,68,0.15)",
          border: `1px solid ${t.type === "success" ? "rgba(34,197,94,0.4)" : t.type === "warn" ? "rgba(245,158,11,0.4)" : "rgba(239,68,68,0.4)"}`,
          color:
            t.type === "success"
              ? "#4ade80"
              : t.type === "warn"
                ? "#fbbf24"
                : "#f87171",
          backdropFilter: "blur(12px)",
          animation: "slide-in 0.3s ease",
        }}
      >
        {t.type === "success" ? "✅" : t.type === "warn" ? "⚠️" : "❌"}{" "}
        {t.message}
      </div>
    ))}
  </div>
);

/* ─── PPE Verification Modal ────────────────────────────────────────────────── */
const DETECTION_WINDOW_MS = 10000;   // 10-second hard limit
const CONFIRM_STREAK       = 3;       // consecutive hits needed
const RETRY_INTERVAL_MS    = 1200;    // ms between frames

const PPEVerificationModal = ({
  visible,
  worker,
  recordId,
  requiredPPE,
  onVerify,
  onCancel,
  loading,
  cameras,
  videoRef,
}) => {
  const [detectedPPE, setDetectedPPE] = useState([]);
  const [detecting, setDetecting] = useState(false);
  const [cameraReady, setCameraReady] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [timeLeft, setTimeLeft] = useState(DETECTION_WINDOW_MS / 1000);
  const [timedOut, setTimedOut] = useState(false);
  const detectTimeoutRef = useRef(null);
  const deadlineRef      = useRef(null);
  const tickRef          = useRef(null);
  const streakRef        = useRef(0);
  const canvasRef        = useRef(null);   // overlay canvas (drawn on)
  const captureCanvasRef = useRef(null);   // hidden capture canvas
  const ppeVideoRef      = useRef(null);

  const resetState = useCallback(() => {
    setDetectedPPE([]);
    setDetecting(false);
    setCameraReady(false);
    setCameraError("");
    setTimeLeft(DETECTION_WINDOW_MS / 1000);
    setTimedOut(false);
    streakRef.current = 0;
    clearTimeout(detectTimeoutRef.current);
    clearTimeout(deadlineRef.current);
    clearInterval(tickRef.current);
  }, []);

  // Draw bounding boxes on the overlay canvas
  const drawBoxes = useCallback((boxes) => {
    const canvas = canvasRef.current;
    const video  = ppeVideoRef.current;
    if (!canvas || !video) return;
    canvas.width  = video.videoWidth  || video.clientWidth;
    canvas.height = video.videoHeight || video.clientHeight;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    boxes.forEach(({ bbox, class_name, conf, color }) => {
      const [x1, y1, x2, y2] = bbox;
      const [r, g, b] = color;
      ctx.strokeStyle = `rgb(${r},${g},${b})`;
      ctx.lineWidth   = 2;
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
      const label = `${class_name} ${Math.round(conf * 100)}%`;
      ctx.font      = "bold 12px sans-serif";
      const tw      = ctx.measureText(label).width;
      ctx.fillStyle = `rgba(${r},${g},${b},0.75)`;
      ctx.fillRect(x1, y1 - 18, tw + 6, 18);
      ctx.fillStyle = "#fff";
      ctx.fillText(label, x1 + 3, y1 - 4);
    });
  }, []);

  // START CAMERA FOR PPE DETECTION WHEN MODAL OPENS
  useEffect(() => {
    if (!visible) {
      resetState();
      if (ppeVideoRef?.current?.srcObject) {
        ppeVideoRef.current.srcObject.getTracks().forEach((t) => t.stop());
        ppeVideoRef.current.srcObject = null;
      }
      return;
    }

    console.log("📹 PPE Modal opened - Starting camera...");

    // When modal opens, start camera for PPE detection
    const startCameraForPPE = async () => {
      try {
        setCameraError("");
        console.log("🎥 Requesting camera access...");
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: "user",
            width: { ideal: 1280 },
            height: { ideal: 720 },
          },
        });
        console.log("✓ Camera access granted, stream:", stream);
        if (ppeVideoRef?.current) {
          ppeVideoRef.current.srcObject = stream;
          console.log("✓ Stream attached to videoRef");
          // Wait for video to be ready
          ppeVideoRef.current.onloadedmetadata = () => {
            console.log("✓ Video metadata loaded");
            ppeVideoRef.current
              .play()
              .then(() => {
                console.log("✓ Video playing, setting cameraReady=true");
                setCameraReady(true);
              })
              .catch((err) => {
                console.error("✗ Failed to play video:", err);
              });
          };
        }
      } catch (err) {
        console.error("✗ Failed to start camera:", err);
        setCameraError(err.message);
        setCameraReady(false);
      }
    };

    startCameraForPPE();

    return () => {
      if (ppeVideoRef?.current?.srcObject) {
        ppeVideoRef.current.srcObject.getTracks().forEach((t) => t.stop());
      }
    };
  }, [visible, resetState]);

  // Capture frame from video as base64 (uses separate hidden canvas)
  const captureFrame = useCallback(() => {
    const video = ppeVideoRef.current;
    if (!video) return null;
    if (!captureCanvasRef.current) captureCanvasRef.current = document.createElement("canvas");
    const c = captureCanvasRef.current;
    c.width  = video.videoWidth;
    c.height = video.videoHeight;
    c.getContext("2d").drawImage(video, 0, 0);
    return c.toDataURL("image/jpeg", 0.9);
  }, []);

  // Auto-trigger 10-second PPE detection loop when camera is ready
  useEffect(() => {
    if (!visible || !cameraReady || timedOut) return;

    // Start countdown tick
    const start = Date.now();
    tickRef.current = setInterval(() => {
      const remaining = Math.max(0, DETECTION_WINDOW_MS - (Date.now() - start));
      setTimeLeft(Math.ceil(remaining / 1000));
    }, 200);

    // Hard deadline — cancel if not confirmed in time
    deadlineRef.current = setTimeout(() => {
      clearInterval(tickRef.current);
      clearTimeout(detectTimeoutRef.current);
      setTimedOut(true);
      setDetecting(false);
      // Clear boxes on timeout
      if (canvasRef.current) {
        const ctx = canvasRef.current.getContext("2d");
        ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
      }
    }, DETECTION_WINDOW_MS);

    const runDetection = async () => {
      setDetecting(true);
      try {
        const frameBase64 = captureFrame();
        if (!frameBase64) { setDetecting(false); return; }

        const res  = await fetch(`${API}/attendance/verify-ppe-frame`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ required_ppe: requiredPPE, frame_base64: frameBase64 }),
        });
        const data = await res.json();

        if (res.ok) {
          setDetectedPPE(data.detected_ppe || []);
          drawBoxes(data.boxes || []);

          if (data.ppe_verified) {
            streakRef.current += 1;
            if (streakRef.current >= CONFIRM_STREAK) {
              // Confirmed — stop timers and auto-verify
              clearTimeout(deadlineRef.current);
              clearInterval(tickRef.current);
              clearTimeout(detectTimeoutRef.current);
              setDetecting(false);
              return; // let user click Verify button (allMet will be true)
            }
          } else {
            streakRef.current = 0;
          }

          // Schedule next frame if still within window
          detectTimeoutRef.current = setTimeout(runDetection, RETRY_INTERVAL_MS);
        }
      } catch (err) {
        console.error("PPE detection error:", err);
        detectTimeoutRef.current = setTimeout(runDetection, RETRY_INTERVAL_MS);
      }
      setDetecting(false);
    };

    const delay = setTimeout(runDetection, 400);

    return () => {
      clearTimeout(delay);
      clearTimeout(detectTimeoutRef.current);
      clearTimeout(deadlineRef.current);
      clearInterval(tickRef.current);
    };
  }, [visible, cameraReady, timedOut, requiredPPE, captureFrame, drawBoxes]);

  if (!visible) return null;

  const allMet = !timedOut && streakRef.current >= CONFIRM_STREAK && requiredPPE.every((ppe) => detectedPPE.includes(ppe));

  return (
    <div style={{
      position: "fixed",
      inset: 0,
      background: "rgba(0,0,0,0.85)",
      display: "flex",
      zIndex: 10000,
      backdropFilter: "blur(6px)",
    }}>

      {/* ── LEFT: Full-screen camera feed ── */}
      <div style={{
        flex: 1,
        position: "relative",
        background: "#000",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        overflow: "hidden",
      }}>
        <video
          ref={ppeVideoRef}
          autoPlay
          playsInline
          muted
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            display: cameraReady ? "block" : "none",
          }}
        />

        {/* Bounding-box overlay */}
        <canvas
          ref={canvasRef}
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            pointerEvents: "none",
            display: cameraReady ? "block" : "none",
          }}
        />

        {/* Countdown badge — top-right of video */}
        {cameraReady && !timedOut && (
          <div style={{
            position: "absolute",
            top: 16, right: 16,
            background: timeLeft <= 3 ? "rgba(239,68,68,0.9)" : "rgba(0,0,0,0.65)",
            color: "#fff",
            borderRadius: 8,
            padding: "6px 14px",
            fontSize: 18,
            fontWeight: 700,
            fontVariantNumeric: "tabular-nums",
            letterSpacing: 1,
            boxShadow: "0 2px 12px rgba(0,0,0,0.4)",
          }}>
            ⏱ {timeLeft}s
          </div>
        )}

        {/* Status badge — bottom of video */}
        {cameraReady && (
          <div style={{
            position: "absolute",
            bottom: 16, left: "50%",
            transform: "translateX(-50%)",
            background: timedOut
              ? "rgba(239,68,68,0.85)"
              : allMet
              ? "rgba(34,197,94,0.85)"
              : "rgba(0,0,0,0.65)",
            color: "#fff",
            borderRadius: 8,
            padding: "8px 20px",
            fontSize: 14,
            fontWeight: 600,
            backdropFilter: "blur(4px)",
            whiteSpace: "nowrap",
          }}>
            {timedOut
              ? "❌ Timed out — attendance not marked"
              : allMet
              ? `✓ PPE Confirmed (${CONFIRM_STREAK}/${CONFIRM_STREAK})`
              : `🔍 Scanning... ${streakRef.current}/${CONFIRM_STREAK} confirmed`}
          </div>
        )}

        {/* Camera loading / error state */}
        {!cameraReady && (
          <div style={{ textAlign: "center", color: "#aaa" }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>📷</div>
            <div style={{ fontSize: 14 }}>
              {cameraError ? `Camera Error: ${cameraError}` : "Starting camera..."}
            </div>
          </div>
        )}
      </div>

      {/* ── RIGHT: Controls panel ── */}
      <div style={{
        width: 320,
        background: "var(--bg-1)",
        borderLeft: "1px solid var(--glass-border)",
        display: "flex",
        flexDirection: "column",
        padding: 24,
        gap: 20,
        overflowY: "auto",
      }}>
        {/* Header */}
        <div>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>🔍 PPE Verification</h2>
          <p style={{ margin: "8px 0 0", fontSize: 13, color: "var(--text-2)" }}>
            Worker: <strong>{worker}</strong>
          </p>
        </div>

        {/* Required PPE */}
        <div>
          <p style={{ margin: "0 0 8px", fontSize: 11, fontWeight: 700, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: 1 }}>
            Required PPE
          </p>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {requiredPPE.map((ppe) => (
              <div key={ppe} style={{
                padding: "5px 10px", borderRadius: 6, fontSize: 12, fontWeight: 600,
                background: "rgba(59,130,246,0.15)", color: "var(--accent)",
                border: "1px solid rgba(59,130,246,0.3)",
              }}>{ppe}</div>
            ))}
          </div>
        </div>

        {/* Detected PPE */}
        <div>
          <p style={{ margin: "0 0 8px", fontSize: 11, fontWeight: 700, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: 1 }}>
            Detected PPE
          </p>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {detectedPPE.length === 0 ? (
              <div style={{ fontSize: 12, color: "var(--text-3)", fontStyle: "italic", display: "flex", alignItems: "center", gap: 6 }}>
                {detecting || !cameraReady
                  ? <><span style={{ display: "inline-block", animation: "spin 1s linear infinite" }}>⏳</span> {!cameraReady ? "Waiting for camera..." : "Scanning..."}</>
                  : "Point webcam at yourself"}
              </div>
            ) : (
              detectedPPE.map((ppe) => (
                <div key={ppe} style={{
                  padding: "5px 10px", borderRadius: 6, fontSize: 12, fontWeight: 600,
                  background: "rgba(34,197,94,0.15)", color: "var(--success)",
                  border: "1px solid rgba(34,197,94,0.3)",
                }}>✓ {ppe}</div>
              ))
            )}
          </div>
        </div>

        {/* Alerts */}
        {timedOut && (
          <div style={{
            padding: 12, background: "rgba(239,68,68,0.15)",
            border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8,
            fontSize: 12, color: "var(--danger)", lineHeight: 1.5,
          }}>
            ⏰ 10-second window expired. Required PPE was not consistently detected. Attendance will NOT be marked.
          </div>
        )}
        {!timedOut && !allMet && detectedPPE.length > 0 && (
          <div style={{
            padding: 12, background: "rgba(239,68,68,0.15)",
            border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8,
            fontSize: 12, color: "var(--danger)",
          }}>
            ❌ Missing: {requiredPPE.filter((p) => !detectedPPE.includes(p)).join(", ")}
          </div>
        )}

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* Action buttons */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <button
            onClick={() => onVerify(detectedPPE)}
            disabled={!allMet || loading || detecting}
            style={{
              padding: "12px 16px", borderRadius: 8,
              background: allMet ? "var(--success)" : "var(--text-3)",
              color: "#fff", border: "none",
              cursor: allMet && !loading && !detecting ? "pointer" : "not-allowed",
              fontSize: 14, fontWeight: 700,
              opacity: allMet && !loading && !detecting ? 1 : 0.45,
              transition: "all 0.2s ease",
            }}
          >
            {loading ? "Processing..." : "✓ Verify & Mark Present"}
          </button>
          <button
            onClick={onCancel}
            disabled={loading}
            style={{
              padding: "10px 16px", borderRadius: 8,
              border: "1px solid var(--glass-border)",
              background: "transparent", color: "var(--text-2)",
              cursor: loading ? "not-allowed" : "pointer",
              fontSize: 13, fontWeight: 600,
              opacity: loading ? 0.5 : 1,
            }}
          >
            {timedOut ? "✕ Close" : "✕ Cancel"}
          </button>
        </div>
      </div>

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

/* ─── QR Attendance Scanner ─────────────────────────────────────────────────── */
const AttendanceScanner = () => {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const rafRef = useRef(null);
  const cooldownRef = useRef(false); // Prevents repeated scans of same QR

  const [scanning, setScanning] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [todayRecords, setTodayRecords] = useState([]);
  const [toasts, setToasts] = useState([]);
  const [lastScanned, setLastScanned] = useState("");

  // PPE-related state
  const [ppeOptions, setPPEOptions] = useState([]);
  const [selectedPPE, setSelectedPPE] = useState([]);
  const [ppeModalMode, setPPEModalMode] = useState("select"); // 'select' or 'verify'
  const [pendingWorker, setPendingWorker] = useState(null);
  const [pendingRecordId, setPendingRecordId] = useState(null);
  const [ppeVerifying, setPPEVerifying] = useState(false);
  const [cameras, setCameras] = useState([]);

  const addToast = (message, type = "success") => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(
      () => setToasts((prev) => prev.filter((t) => t.id !== id)),
      4500,
    );
  };

  const fetchTodayAttendance = async () => {
    try {
      const r = await fetch(`${API}/attendance/today`);
      if (r.ok) setTodayRecords(await r.json());
    } catch {
      /* silently fail */
    }
  };

  const fetchPPEOptions = async () => {
    try {
      const r = await fetch(`${API}/ppe/options`);
      if (r.ok) {
        const data = await r.json();
        setPPEOptions(data.available_ppe || []);
      }
    } catch {
      /* silently fail */
    }
  };

  const fetchCameras = async () => {
    try {
      const r = await fetch(`${API}/cameras`);
      if (r.ok) {
        setCameras(await r.json());
      }
    } catch {
      /* silently fail */
    }
  };

  useEffect(() => {
    fetchPPEOptions();
    fetchCameras();
    fetchTodayAttendance();
    const interval = setInterval(fetchTodayAttendance, 10000); // refresh every 10s
    return () => clearInterval(interval);
  }, []);

  const startCamera = async () => {
    setCameraError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: "environment",
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
        setScanning(true);
        scanLoop();
      }
    } catch (err) {
      if (err.name === "NotAllowedError") {
        setCameraError(
          "Camera access denied. Please allow camera permission in your browser settings.",
        );
      } else if (err.name === "NotFoundError") {
        setCameraError("No camera found on this device.");
      } else {
        setCameraError(`Camera error: ${err.message}`);
      }
    }
  };

  const stopCamera = () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    if (videoRef.current?.srcObject) {
      videoRef.current.srcObject.getTracks().forEach((t) => t.stop());
      videoRef.current.srcObject = null;
    }
    setScanning(false);
    setLastScanned("");
    cooldownRef.current = false;
  };

  const handleScan = useCallback(
    async (qrData) => {
      if (cooldownRef.current || qrData === lastScanned) return;
      cooldownRef.current = true;
      setLastScanned(qrData);

      // ✅ STOP QR SCANNING CAMERA WHEN QR IS SCANNED
      stopCamera();

      try {
        const res = await fetch(`${API}/attendance/scan`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            qr_data: qrData,
            required_ppe: selectedPPE.length > 0 ? selectedPPE : null,
          }),
        });
        const data = await res.json();

        if (res.status === 200) {
          if (data.requires_ppe_verification) {
            // Move to PPE verification mode
            setPendingWorker(data.record.name);
            setPendingRecordId(data.record_id);
            setPPEModalMode("verify");
            addToast("QR scanned! Verifying PPE requirements...", "warn");
          } else {
            addToast(data.message, "success");
            fetchTodayAttendance();
            // Restart QR scanning after successful attendance (no PPE required)
            setTimeout(() => {
              startCamera();
            }, 500);
          }
        } else if (res.status === 404) {
          addToast(data.detail || "QR code not registered in system.", "error");
          // Restart camera on error
          setTimeout(() => {
            startCamera();
          }, 500);
        } else if (res.status === 409) {
          addToast(data.detail, "warn");
          // Restart camera on error
          setTimeout(() => {
            startCamera();
          }, 500);
        } else {
          addToast(data.detail || "Unexpected error.", "error");
          // Restart camera on error
          setTimeout(() => {
            startCamera();
          }, 500);
        }
      } catch {
        addToast("Network error. Cannot reach backend.", "error");
        // Restart camera on error
        setTimeout(() => {
          startCamera();
        }, 500);
      }

      // Cooldown for 3 seconds to avoid re-scanning
      setTimeout(() => {
        cooldownRef.current = false;
        setLastScanned("");
      }, 3000);
    },
    [lastScanned, selectedPPE],
  );

  const scanLoop = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2) {
      rafRef.current = requestAnimationFrame(scanLoop);
      return;
    }
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const code = jsQR(imageData.data, imageData.width, imageData.height, {
      inversionAttempts: "dontInvert",
    });
    if (code && code.data) {
      handleScan(code.data);
    }
    rafRef.current = requestAnimationFrame(scanLoop);
  }, [handleScan]);

  const handlePPEVerify = async (detectedPPE) => {
    setPPEVerifying(true);
    try {
      const res = await fetch(
        `${API}/attendance/verify-ppe?record_id=${pendingRecordId}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ detected_ppe: detectedPPE }),
        },
      );
      const data = await res.json();

      if (res.ok) {
        addToast(data.message, "success");
        fetchTodayAttendance();
        setPPEModalMode("select");
        setPendingWorker(null);
        setPendingRecordId(null);
        // ✅ RESTART QR SCANNING CAMERA AFTER PPE VERIFICATION SUCCESS
        setTimeout(() => {
          startCamera();
        }, 500);
      } else {
        addToast(data.detail || "PPE verification failed.", "error");
      }
    } catch {
      addToast("Network error during PPE verification.", "error");
    } finally {
      setPPEVerifying(false);
    }
  };

  const handlePPECancel = async () => {
    // If there's a pending record (timed out or user cancelled), delete it
    if (pendingRecordId) {
      try {
        await fetch(`${API}/attendance/${pendingRecordId}`, { method: "DELETE" });
      } catch { /* ignore */ }
    }
    setPPEModalMode("select");
    setPendingWorker(null);
    setPendingRecordId(null);
    setTimeout(() => startCamera(), 300);
  };

  const togglePPE = (ppe) => {
    setSelectedPPE((prev) =>
      prev.includes(ppe) ? prev.filter((p) => p !== ppe) : [...prev, ppe],
    );
  };

  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, []);

  return (
    <div>
      <Toast toasts={toasts} />

      <PPEVerificationModal
        visible={pendingRecordId !== null}
        worker={pendingWorker}
        recordId={pendingRecordId}
        requiredPPE={selectedPPE}
        onVerify={handlePPEVerify}
        onCancel={handlePPECancel}
        loading={ppeVerifying}
        cameras={cameras}
      />

      <div className="section-header">
        <h1 className="section-title">
          QR Attendance Scanner with PPE Verification
        </h1>
        <p className="section-subtitle">
          Point a worker's QR code at the camera to mark their attendance and
          verify PPE compliance.
        </p>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 380px",
          gap: 24,
          alignItems: "start",
        }}
      >
        {/* Scanner Panel */}
        <div className="glass-card" style={{ overflow: "hidden" }}>
          <div
            style={{
              padding: "16px 20px",
              borderBottom: "1px solid var(--glass-border)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <span style={{ fontWeight: 600 }}>📷 Live Scanner</span>
            <div style={{ display: "flex", gap: 8 }}>
              {!scanning ? (
                <button
                  id="start-scanner-btn"
                  className="btn btn-success btn-sm"
                  onClick={startCamera}
                >
                  ▶ Start Camera
                </button>
              ) : (
                <button
                  id="stop-scanner-btn"
                  className="btn btn-danger btn-sm"
                  onClick={stopCamera}
                >
                  ⏹ Stop Camera
                </button>
              )}
            </div>
          </div>

          <div
            style={{
              position: "relative",
              background: "#000",
              minHeight: 360,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              style={{
                width: "100%",
                display: scanning ? "block" : "none",
                maxHeight: 480,
                objectFit: "cover",
              }}
            />
            <canvas ref={canvasRef} style={{ display: "none" }} />

            {/* Scanner crosshair overlay */}
            {scanning && (
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  pointerEvents: "none",
                }}
              >
                <div
                  style={{
                    width: 180,
                    height: 180,
                    border: "2px solid rgba(59,130,246,0.8)",
                    borderRadius: 12,
                    boxShadow: "0 0 0 9999px rgba(0,0,0,0.35)",
                    position: "relative",
                  }}
                >
                  {/* Corner accents */}
                  {[
                    ["0", "0"],
                    ["0", "auto"],
                    ["auto", "0"],
                    ["auto", "auto"],
                  ].map(([t, b], i) => (
                    <div
                      key={i}
                      style={{
                        position: "absolute",
                        top: t !== "auto" ? -2 : "auto",
                        bottom: b !== "auto" ? -2 : "auto",
                        left: i < 2 ? -2 : "auto",
                        right: i >= 2 ? -2 : "auto",
                        width: 20,
                        height: 20,
                        borderColor: "var(--accent)",
                        borderStyle: "solid",
                        borderWidth:
                          i === 0
                            ? "3px 0 0 3px"
                            : i === 1
                              ? "0 0 3px 3px"
                              : i === 2
                                ? "3px 3px 0 0"
                                : "0 3px 3px 0",
                        borderRadius:
                          i === 0
                            ? "4px 0 0 0"
                            : i === 1
                              ? "0 0 0 4px"
                              : i === 2
                                ? "0 4px 0 0"
                                : "0 0 4px 0",
                      }}
                    />
                  ))}
                  {/* Scan line */}
                  <div
                    style={{
                      position: "absolute",
                      left: 0,
                      right: 0,
                      height: 2,
                      background: "var(--accent)",
                      animation: "scan-line 1.8s ease-in-out infinite",
                      boxShadow: "0 0 8px var(--accent)",
                    }}
                  />
                </div>
              </div>
            )}

            {!scanning && (
              <div style={{ textAlign: "center", color: "var(--text-3)" }}>
                {cameraError ? (
                  <div style={{ padding: 24 }}>
                    <div style={{ fontSize: 36, marginBottom: 12 }}>🚫</div>
                    <div
                      style={{
                        color: "var(--danger)",
                        fontSize: 14,
                        maxWidth: 300,
                      }}
                    >
                      {cameraError}
                    </div>
                  </div>
                ) : (
                  <div style={{ padding: 48 }}>
                    <div style={{ fontSize: 48, marginBottom: 12 }}>📷</div>
                    <div style={{ fontSize: 14 }}>
                      Press "Start Camera" to begin scanning
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {lastScanned && (
            <div
              style={{
                padding: "10px 20px",
                borderTop: "1px solid var(--glass-border)",
                fontSize: 12,
                color: "var(--text-3)",
                fontFamily: "monospace",
              }}
            >
              Last scanned: {lastScanned}
            </div>
          )}
        </div>

        {/* Sidebar: PPE Selection + Today's Log */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* PPE Selection Panel */}
          <div className="glass-card">
            <div
              style={{
                padding: "14px 18px",
                borderBottom: "1px solid var(--glass-border)",
              }}
            >
              <span style={{ fontWeight: 600, fontSize: 14 }}>
                ⚙️ PPE Requirements
              </span>
            </div>
            <div style={{ padding: 16 }}>
              <p
                style={{
                  marginTop: 0,
                  marginBottom: 12,
                  fontSize: 12,
                  color: "var(--text-3)",
                }}
              >
                Select required PPE for this scanning session:
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {ppeOptions.map((ppe) => (
                  <label
                    key={ppe}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      cursor: "pointer",
                      fontSize: 13,
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={selectedPPE.includes(ppe)}
                      onChange={() => togglePPE(ppe)}
                      style={{ cursor: "pointer", width: 18, height: 18 }}
                    />
                    <span
                      style={{
                        fontWeight: selectedPPE.includes(ppe) ? 600 : 400,
                      }}
                    >
                      {ppe}
                    </span>
                  </label>
                ))}
              </div>
              {selectedPPE.length === 0 && (
                <p
                  style={{
                    marginTop: 12,
                    fontSize: 11,
                    color: "var(--text-3)",
                    fontStyle: "italic",
                  }}
                >
                  No PPE requirements selected (attendance only)
                </p>
              )}
              {selectedPPE.length > 0 && (
                <div
                  style={{
                    marginTop: 12,
                    padding: 8,
                    background: "rgba(59,130,246,0.1)",
                    borderRadius: 6,
                    fontSize: 11,
                    color: "var(--accent)",
                    textAlign: "center",
                    fontWeight: 600,
                  }}
                >
                  🔒 PPE verification will be required
                </div>
              )}
            </div>
          </div>

          {/* Today's Attendance Log */}
          <div
            className="glass-card"
            style={{ maxHeight: 360, display: "flex", flexDirection: "column" }}
          >
            <div
              style={{
                padding: "14px 18px",
                borderBottom: "1px solid var(--glass-border)",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <span style={{ fontWeight: 600, fontSize: 14 }}>
                📋 Today's Log
              </span>
              <span style={{ fontSize: 12, color: "var(--text-3)" }}>
                {new Date().toLocaleDateString()}
              </span>
            </div>
            <div style={{ flex: 1, overflowY: "auto" }}>
              {todayRecords.length === 0 ? (
                <div style={{ padding: "40px 20px", textAlign: "center" }}>
                  <div style={{ fontSize: 32, marginBottom: 8, opacity: 0.4 }}>
                    🕐
                  </div>
                  <div style={{ color: "var(--text-3)", fontSize: 13 }}>
                    No attendance marked today
                  </div>
                </div>
              ) : (
                todayRecords.map((r) => (
                  <div
                    key={r._id}
                    style={{
                      padding: "12px 18px",
                      borderBottom: "1px solid var(--glass-border)",
                      display: "flex",
                      flexDirection: "column",
                      gap: 2,
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                      }}
                    >
                      <span style={{ fontWeight: 600, fontSize: 13 }}>
                        {r.name}
                      </span>
                      <span
                        style={{
                          fontSize: 11,
                          fontWeight: 600,
                          color:
                            r.status === "Present"
                              ? "var(--success)"
                              : r.status === "pending_verification"
                                ? "#fbbf24"
                                : "var(--danger)",
                        }}
                      >
                        {r.status === "Present"
                          ? "✓ Present"
                          : r.status === "pending_verification"
                            ? "⏳ Pending"
                            : "✗ Rejected"}
                      </span>
                    </div>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        fontSize: 11,
                        color: "var(--text-3)",
                      }}
                    >
                      <span>{r.department}</span>
                      <span>{r.time}</span>
                    </div>
                    {r.detected_ppe && r.detected_ppe.length > 0 && (
                      <div
                        style={{
                          fontSize: 10,
                          color: "var(--success)",
                          marginTop: 2,
                        }}
                      >
                        ✓ PPE: {r.detected_ppe.join(", ")}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
            <div
              style={{
                padding: "10px 18px",
                borderTop: "1px solid var(--glass-border)",
                fontSize: 12,
                color: "var(--text-2)",
              }}
            >
              {todayRecords.length} record(s) today
            </div>
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
