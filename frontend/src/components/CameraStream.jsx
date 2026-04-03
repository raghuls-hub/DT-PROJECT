import React, { useEffect, useRef, useState } from 'react';

const CameraStream = ({ cameraUrl, onClose }) => {
  const videoRef = useRef(null);
  const pcRef = useRef(null);
  const [status, setStatus] = useState('connecting'); // connecting, connected, error

  useEffect(() => {
    let pc;
    
    const startWebRTC = async () => {
      setStatus('connecting');
      pc = new RTCPeerConnection();
      pcRef.current = pc;

      // Ensure we receive Video (transceiver pattern is standard for receive-only)
      pc.addTransceiver('video', { direction: 'recvonly' });

      pc.ontrack = (event) => {
        console.log(`[WebRTC] Received track for ${cameraUrl}`);
        if (videoRef.current && event.streams && event.streams[0]) {
          videoRef.current.srcObject = event.streams[0];
          setStatus('connected');
        }
      };

      pc.onconnectionstatechange = () => {
        console.log(`[WebRTC] State: ${pc.connectionState} for ${cameraUrl}`);
        if (pc.connectionState === 'failed' || pc.connectionState === 'disconnected') {
           setStatus('error');
        }
      };

      try {
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);

        // POST the offer to the FastAPI backend
        const response = await fetch('http://localhost:8000/offer', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            sdp: pc.localDescription.sdp,
            type: pc.localDescription.type,
            camera_url: cameraUrl
          })
        });

        if (!response.ok) throw new Error("Failed to signal backend.");
        
        const answer = await response.json();
        await pc.setRemoteDescription(new RTCSessionDescription(answer));

      } catch (err) {
        console.error("WebRTC Error:", err);
        setStatus('error');
      }
    };

    startWebRTC();

    return () => {
      console.log(`[WebRTC] Unmounting & Closing peer for ${cameraUrl}`);
      if (pcRef.current) {
        pcRef.current.close();
      }
    };
  }, [cameraUrl]);

  return (
    <div className="camera-card glass-panel">
      <div className="camera-header">
        <div className="camera-title">
          <span className={`status-indicator status-${status}`}></span>
          {cameraUrl}
        </div>
        <button className="btn-close" onClick={onClose} title="Remove Camera">
          ✕
        </button>
      </div>
      <div className="video-container">
        <video 
          ref={videoRef} 
          autoPlay 
          playsInline 
          controls={false}
          muted // crucial for autoplay
        />
      </div>
    </div>
  );
};

export default CameraStream;
