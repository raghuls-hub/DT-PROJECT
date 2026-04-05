import React, { useState, useEffect, useRef } from 'react';

const API = 'http://localhost:8000';

/* ─── Inline Modal ─────────────────────────────────────────────────────────── */
const Modal = ({ open, onClose, children }) => {
  if (!open) return null;
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={e => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>✕</button>
        {children}
      </div>
    </div>
  );
};

/* ─── Worker Management ───────────────────────────────────────────────────── */
const WorkerManagement = () => {
  const [workers, setWorkers]     = useState([]);
  const [form, setForm]           = useState({ name: '', dob: '', department: '', email: '' });
  const [formError, setFormError] = useState('');
  const [loading, setLoading]     = useState(false);
  const [qrModal, setQrModal]     = useState(null);   // { name, employee_id, qr_code }
  const [editModal, setEditModal] = useState(null);   // worker doc
  const [editForm, setEditForm]   = useState({});
  const [attendanceModal, setAttendanceModal] = useState(null); // { worker, records }
  const [confirmDelete, setConfirmDelete] = useState(null);      // worker_id

  const fetchWorkers = async () => {
    try {
      const r = await fetch(`${API}/workers`);
      if (!r.ok) throw new Error();
      setWorkers(await r.json());
    } catch {
      setFormError('Failed to load workers.');
    }
  };

  useEffect(() => { fetchWorkers(); }, []);

  const handleAdd = async () => {
    setFormError('');
    if (!form.name.trim())       return setFormError('Name is required.');
    if (!form.dob.trim())        return setFormError('Date of birth is required.');
    if (!form.department.trim()) return setFormError('Department is required.');

    setLoading(true);
    try {
      const r = await fetch(`${API}/workers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || 'Failed to add worker.');
      setWorkers(prev => [data, ...prev]);
      setForm({ name: '', dob: '', department: '', email: '' });
    } catch (e) {
      setFormError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await fetch(`${API}/workers/${id}`, { method: 'DELETE' });
      setWorkers(prev => prev.filter(w => w._id !== id));
    } catch { setFormError('Delete failed.'); }
    setConfirmDelete(null);
  };

  const handleEditSubmit = async () => {
    try {
      const r = await fetch(`${API}/workers/${editModal._id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editForm),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || 'Update failed.');
      setWorkers(prev => prev.map(w => w._id === data._id ? data : w));
      setEditModal(null);
    } catch (e) { setFormError(e.message); }
  };

  const openAttendance = async (worker) => {
    try {
      const r = await fetch(`${API}/attendance?date=`);
      const all = await r.json();
      const records = all.filter(a => a.worker_id === worker._id)
                         .sort((a, b) => b.timestamp.localeCompare(a.timestamp));
      setAttendanceModal({ worker, records });
    } catch { setFormError('Could not load attendance.'); }
  };

  const downloadQR = (name, b64) => {
    const a = document.createElement('a');
    a.href = `data:image/png;base64,${b64}`;
    a.download = `${name.replace(/ /g, '_')}_QR.png`;
    a.click();
  };

  return (
    <div>
      <div className="section-header">
        <h1 className="section-title">Worker Management</h1>
        <p className="section-subtitle">Add, update, or remove workers. Each worker gets a unique ID and QR code for attendance.</p>
      </div>

      {/* Add Form */}
      <div className="glass-card add-camera-form" style={{ flexWrap: 'wrap' }}>
        <div className="form-group">
          <label className="form-label">Full Name</label>
          <input id="worker-name" className="form-input" placeholder="e.g. John Doe"
            value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
        </div>
        <div className="form-group">
          <label className="form-label">Date of Birth</label>
          <input id="worker-dob" className="form-input" type="date"
            value={form.dob} onChange={e => setForm(f => ({ ...f, dob: e.target.value }))} />
        </div>
        <div className="form-group">
          <label className="form-label">Department</label>
          <input id="worker-dept" className="form-input" placeholder="e.g. Security"
            value={form.department} onChange={e => setForm(f => ({ ...f, department: e.target.value }))} />
        </div>
        <div className="form-group">
          <label className="form-label">Email (optional)</label>
          <input id="worker-email" className="form-input" placeholder="john@example.com"
            value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
        </div>
        <button id="add-worker-btn" className="btn btn-primary" onClick={handleAdd}
          disabled={loading} style={{ alignSelf: 'flex-end' }}>
          {loading ? '⏳ Creating...' : '+ Add Worker'}
        </button>
      </div>
      {formError && <p style={{ color: 'var(--danger)', fontSize: '13px', marginBottom: '16px', paddingLeft: '4px' }}>⚠ {formError}</p>}

      {/* Worker Table */}
      <div className="glass-card camera-list">
        <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 1fr 1fr auto', gap: '16px', padding: '12px 20px', borderBottom: '1px solid var(--glass-border)', background: 'rgba(0,0,0,0.2)' }}>
          {['Name', 'Employee ID', 'Department', 'DOB', 'Actions'].map(h =>
            <span key={h} className="camera-list-col">{h}</span>)}
        </div>

        {workers.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">👷</div>
            <div className="empty-title">No workers yet</div>
            <div className="empty-desc">Add a worker using the form above.</div>
          </div>
        ) : workers.map(w => (
          <div key={w._id} className="camera-row"
            style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 1fr 1fr auto', gap: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              {/* QR Thumbnail */}
              <img src={`data:image/png;base64,${w.qr_code}`} alt="QR"
                style={{ width: 36, height: 36, borderRadius: 4, cursor: 'pointer', border: '1px solid var(--glass-border)' }}
                onClick={() => setQrModal(w)} title="View QR Code" />
              <span style={{ fontWeight: 600 }}>{w.name}</span>
            </div>
            <span style={{ fontFamily: 'monospace', fontSize: 13, color: 'var(--accent)' }}>{w.employee_id}</span>
            <span style={{ fontSize: 13, color: 'var(--text-2)' }}>{w.department}</span>
            <span style={{ fontSize: 13, color: 'var(--text-3)' }}>{w.dob}</span>
            <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
              <button className="btn btn-ghost btn-sm" onClick={() => openAttendance(w)} title="Attendance History">📋</button>
              <button className="btn btn-ghost btn-sm" onClick={() => { setEditModal(w); setEditForm({ name: w.name, dob: w.dob, department: w.department, email: w.email }); }}>✏️</button>
              <button className="btn btn-danger btn-sm" onClick={() => setConfirmDelete(w._id)}>🗑</button>
            </div>
          </div>
        ))}
      </div>

      {/* QR Modal */}
      <Modal open={!!qrModal} onClose={() => setQrModal(null)}>
        {qrModal && (
          <div style={{ textAlign: 'center', padding: '8px' }}>
            <h3 style={{ marginBottom: 4 }}>{qrModal.name}</h3>
            <p style={{ color: 'var(--accent)', fontFamily: 'monospace', marginBottom: 16 }}>{qrModal.employee_id}</p>
            <img src={`data:image/png;base64,${qrModal.qr_code}`} alt="QR"
              style={{ width: 220, height: 220, borderRadius: 8, border: '2px solid var(--glass-border)' }} />
            <div style={{ marginTop: 16 }}>
              <button className="btn btn-primary" onClick={() => downloadQR(qrModal.name, qrModal.qr_code)}>
                ⬇ Download QR
              </button>
            </div>
          </div>
        )}
      </Modal>

      {/* Edit Modal */}
      <Modal open={!!editModal} onClose={() => setEditModal(null)}>
        {editModal && (
          <div style={{ minWidth: 320 }}>
            <h3 style={{ marginBottom: 20 }}>Edit Worker</h3>
            {['name', 'dob', 'department', 'email'].map(field => (
              <div className="form-group" key={field} style={{ marginBottom: 12 }}>
                <label className="form-label">{field.charAt(0).toUpperCase() + field.slice(1)}</label>
                <input className="form-input" type={field === 'dob' ? 'date' : 'text'}
                  value={editForm[field] || ''}
                  onChange={e => setEditForm(f => ({ ...f, [field]: e.target.value }))} />
              </div>
            ))}
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={handleEditSubmit}>Save Changes</button>
              <button className="btn btn-ghost" onClick={() => setEditModal(null)}>Cancel</button>
            </div>
          </div>
        )}
      </Modal>

      {/* Confirm Delete Modal */}
      <Modal open={!!confirmDelete} onClose={() => setConfirmDelete(null)}>
        <div style={{ textAlign: 'center', padding: '8px' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>⚠️</div>
          <h3 style={{ marginBottom: 8 }}>Delete Worker?</h3>
          <p style={{ color: 'var(--text-2)', marginBottom: 20, fontSize: 14 }}>
            This will permanently delete the worker and all their attendance records.
          </p>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
            <button className="btn btn-danger" onClick={() => handleDelete(confirmDelete)}>Yes, Delete</button>
            <button className="btn btn-ghost" onClick={() => setConfirmDelete(null)}>Cancel</button>
          </div>
        </div>
      </Modal>

      {/* Attendance History Modal */}
      <Modal open={!!attendanceModal} onClose={() => setAttendanceModal(null)}>
        {attendanceModal && (
          <div style={{ minWidth: 440, maxHeight: '70vh', overflowY: 'auto' }}>
            <h3 style={{ marginBottom: 4 }}>{attendanceModal.worker.name}</h3>
            <p style={{ color: 'var(--text-2)', fontSize: 13, marginBottom: 16 }}>
              {attendanceModal.worker.employee_id} · {attendanceModal.records.length} records
            </p>
            {attendanceModal.records.length === 0 ? (
              <div className="empty-state" style={{ padding: '30px 0' }}>
                <div className="empty-icon">📋</div>
                <div className="empty-title" style={{ fontSize: 15 }}>No attendance records</div>
              </div>
            ) : attendanceModal.records.map(r => (
              <div key={r._id} style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0', borderBottom: '1px solid var(--glass-border)', fontSize: 13 }}>
                <span style={{ color: 'var(--text-2)' }}>{r.date}</span>
                <span style={{ color: 'var(--text-2)' }}>{r.time}</span>
                <span style={{ color: 'var(--success)', fontWeight: 600 }}>✓ {r.status}</span>
              </div>
            ))}
          </div>
        )}
      </Modal>
    </div>
  );
};

export default WorkerManagement;
