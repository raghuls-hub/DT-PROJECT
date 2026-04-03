import React, { useState } from 'react';
import CameraStream from './components/CameraStream';
import './index.css';

function App() {
  const [cameraUrls, setCameraUrls] = useState([]);
  const [inputUrl, setInputUrl] = useState('');

  const handleAddCamera = () => {
    if (inputUrl.trim() === '') return;
    if (!cameraUrls.includes(inputUrl)) {
      setCameraUrls([...cameraUrls, inputUrl]);
    }
    setInputUrl('');
  };

  const handleRemoveCamera = (urlToRemove) => {
    // Notify the backend to cleanly close the thread
    fetch('http://localhost:8000/close_camera', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ camera_url: urlToRemove }),
    }).catch(err => console.error("Error closing remote camera:", err));

    // Remove from UI
    setCameraUrls(cameraUrls.filter(url => url !== urlToRemove));
  };

  return (
    <div>
      {/* Input Section */}
      <div className="input-section glass-panel">
        <input
          type="text"
          className="camera-input"
          placeholder="Enter a Live Stream URL (RTSP / HTTP / IP Camera)..."
          value={inputUrl}
          onChange={(e) => setInputUrl(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAddCamera()}
        />
        <button className="btn-add" onClick={handleAddCamera}>
          Add Camera
        </button>
      </div>

      {/* Live Monitoring Section */}
      <div className="monitor-grid">
        {cameraUrls.map((url) => (
          <CameraStream 
            key={url} 
            cameraUrl={url} 
            onClose={() => handleRemoveCamera(url)} 
          />
        ))}
      </div>
    </div>
  );
}

export default App;
