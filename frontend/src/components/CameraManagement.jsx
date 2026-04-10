import React, { useState, useEffect } from "react";

const API = "http://localhost:8000";

const CameraManagement = ({ cameras, onCamerasChange }) => {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [endpoint, setEndpoint] = useState(""); // NEW: Endpoint state
  const [editingId, setEditingId] = useState(null); // NEW: Track which camera is being edited
  const [editName, setEditName] = useState(""); // NEW: Edit form states
  const [editUrl, setEditUrl] = useState("");
  const [editEndpoint, setEditEndpoint] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleAdd = async () => {
    if (!name.trim() || !url.trim()) {
      setError("Both name and URL are required.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${API}/cameras`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          url: url.trim(),
          endpoint: endpoint.trim() || null, // NEW: Include endpoint
        }),
      });
      if (!res.ok) throw new Error("Failed to add camera.");
      const added = await res.json();
      onCamerasChange([...cameras, added]);
      setName("");
      setUrl("");
      setEndpoint(""); // NEW: Reset endpoint field
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (cam) => {
    try {
      await fetch(`${API}/cameras/${cam._id}`, { method: "DELETE" });
      onCamerasChange(cameras.filter((c) => c._id !== cam._id));
    } catch (err) {
      console.error("Delete failed:", err);
    }
  };

  const handleEdit = (cam) => {
    setEditingId(cam._id);
    setEditName(cam.name);
    setEditUrl(cam.url);
    setEditEndpoint(cam.endpoint || "");
  };

  const handleUpdate = async () => {
    if (!editName.trim() || !editUrl.trim()) {
      setError("Both name and URL are required.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${API}/cameras/${editingId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: editName.trim(),
          url: editUrl.trim(),
          endpoint: editEndpoint.trim() || null,
        }),
      });
      if (!res.ok) throw new Error("Failed to update camera.");
      const updated = await res.json();
      onCamerasChange(cameras.map((c) => (c._id === editingId ? updated : c)));
      setEditingId(null);
      setEditName("");
      setEditUrl("");
      setEditEndpoint("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditName("");
    setEditUrl("");
    setEditEndpoint("");
  };

  return (
    <div>
      <div className="section-header">
        <h1 className="section-title">Camera Management</h1>
        <p className="section-subtitle">
          Add and manage your CCTV camera sources. Cameras are persisted to the
          database.
        </p>
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
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
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
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          />
        </div>
        <div className="form-group">
          <label className="form-label">Alert Endpoint (Optional)</label>
          <input
            id="camera-endpoint-input"
            className="form-input"
            placeholder="e.g. warehouse-alerts (for ntfy.sh notifications)"
            value={endpoint}
            onChange={(e) => setEndpoint(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          />
        </div>
        <button
          id="add-camera-btn"
          className="btn btn-primary"
          onClick={handleAdd}
          disabled={loading}
          style={{ alignSelf: "flex-end" }}
        >
          {loading ? "⏳ Adding..." : "+ Add Camera"}
        </button>
      </div>
      {error && (
        <p
          style={{
            color: "var(--danger)",
            fontSize: "13px",
            marginBottom: "16px",
            paddingLeft: "4px",
          }}
        >
          ⚠ {error}
        </p>
      )}

      {/* Camera List */}
      <div className="glass-card camera-list">
        <div className="camera-list-header">
          <span className="camera-list-col">Name</span>
          <span className="camera-list-col">Stream URL</span>
          <span className="camera-list-col">Alert Endpoint</span>
          <span className="camera-list-col">Actions</span>
        </div>

        {cameras.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📷</div>
            <div className="empty-title">No cameras yet</div>
            <div className="empty-desc">Add a camera above to get started.</div>
          </div>
        ) : (
          cameras.map((cam) =>
            editingId === cam._id ? (
              // Edit Form
              <div className="camera-row edit-row" key={cam._id}>
                <div
                  className="form-group"
                  style={{ flex: 1, marginRight: "8px" }}
                >
                  <input
                    className="form-input"
                    placeholder="Camera Name"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                  />
                </div>
                <div
                  className="form-group"
                  style={{ flex: 2, marginRight: "8px" }}
                >
                  <input
                    className="form-input"
                    placeholder="Stream URL"
                    value={editUrl}
                    onChange={(e) => setEditUrl(e.target.value)}
                  />
                </div>
                <div
                  className="form-group"
                  style={{ flex: 1, marginRight: "8px" }}
                >
                  <input
                    className="form-input"
                    placeholder="Alert Endpoint"
                    value={editEndpoint}
                    onChange={(e) => setEditEndpoint(e.target.value)}
                  />
                </div>
                <div className="camera-actions">
                  <button
                    className="btn btn-success btn-sm"
                    onClick={handleUpdate}
                    disabled={loading}
                  >
                    {loading ? "⏳" : "💾 Save"}
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={handleCancelEdit}
                  >
                    ❌ Cancel
                  </button>
                </div>
              </div>
            ) : (
              // Display Row
              <div className="camera-row" key={cam._id}>
                <div className="camera-name">
                  <span
                    className="cam-dot"
                    style={{ background: "var(--accent)" }}
                  ></span>
                  {cam.name}
                </div>
                <div className="camera-url-cell" title={cam.url}>
                  {cam.url}
                </div>
                <div
                  className="camera-endpoint-cell"
                  title={cam.endpoint || "No endpoint set"}
                >
                  {cam.endpoint || "—"}
                </div>
                <div className="camera-actions">
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={() => handleEdit(cam)}
                  >
                    ✏️ Edit
                  </button>
                  <button
                    id={`delete-cam-${cam._id}`}
                    className="btn btn-danger btn-sm"
                    onClick={() => handleDelete(cam)}
                  >
                    🗑 Delete
                  </button>
                </div>
              </div>
            ),
          )
        )}
      </div>
    </div>
  );
};

export default CameraManagement;
