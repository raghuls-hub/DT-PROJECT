import asyncio
import qrcode
import io
import base64
from datetime import datetime, date
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from aiortc import RTCPeerConnection, RTCSessionDescription
from pydantic import BaseModel
from typing import Optional, List
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv()

from stream_manager import stream_factory
from database import (
    get_camera_collection,
    get_worker_collection,
    get_attendance_collection,
)

app = FastAPI(title="Smart Safety CCTV System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Helpers ───────────────────────────────────────────────────────────────────

def _serialize(doc: dict) -> dict:
    doc["_id"] = str(doc["_id"])
    return doc

def _generate_employee_id(name: str, dob: str) -> str:
    """
    Generate a human-readable employee ID from name and DOB.
    Format: <FIRST3><LAST3>-<DDMMYYYY>
    Example: John Doe 15/03/1995 → JOHDOE-15031995
    """
    parts = name.strip().upper().split()
    first = parts[0][:3]
    last  = parts[-1][-3:] if len(parts) > 1 else parts[0][-3:]
    # Normalize DOB: accept YYYY-MM-DD or DD/MM/YYYY
    dob_clean = dob.replace("-", "").replace("/", "")
    if len(dob_clean) == 8:
        if dob[4] in ("-", "/"):      # YYYY-MM-DD → DDMMYYYY
            dob_clean = dob_clean[6:] + dob_clean[4:6] + dob_clean[:4]
    return f"{first}{last}-{dob_clean}"

def _generate_qr_b64(data: str) -> str:
    """Generate a QR code for the given data string and return as base64 PNG."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=8,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

async def _unique_employee_id(col, base_id: str) -> str:
    """Ensure the employee_id is unique; append suffix if collision."""
    eid = base_id
    suffix = 2
    while await col.find_one({"employee_id": eid}):
        eid = f"{base_id}-{suffix}"
        suffix += 1
    return eid

# ─── Pydantic Models ───────────────────────────────────────────────────────────

class OfferRequest(BaseModel):
    sdp: str
    type: str
    camera_url: str
    monitored_ppe: Optional[List[str]] = []

class CameraIn(BaseModel):
    name: str
    url: str
    endpoint: Optional[str] = None  # Ntfy.sh endpoint for alerts

class WorkerIn(BaseModel):
    name: str
    dob: str          # Expected: YYYY-MM-DD or DD/MM/YYYY
    department: str
    email: Optional[str] = ""

class WorkerUpdate(BaseModel):
    name: Optional[str] = None
    dob: Optional[str] = None
    department: Optional[str] = None
    email: Optional[str] = None

class ScanRequest(BaseModel):
    qr_data: str      # The decoded string from the QR code

# ─── Peer Connections ─────────────────────────────────────────────────────────

pcs = set()

# ─── Camera CRUD ──────────────────────────────────────────────────────────────

@app.get("/cameras")
async def list_cameras():
    col = get_camera_collection()
    cameras = await col.find().to_list(length=200)
    return [_serialize(c) for c in cameras]

@app.post("/cameras", status_code=201)
async def add_camera(camera: CameraIn):
    col = get_camera_collection()
    doc = {
        "name": camera.name, 
        "url": camera.url,
        "endpoint": camera.endpoint  # Store ntfy.sh endpoint
    }
    result = await col.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc

@app.put("/cameras/{camera_id}")
async def update_camera(camera_id: str, camera: CameraIn):
    col = get_camera_collection()
    try:
        oid = ObjectId(camera_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid camera ID")
    
    existing = await col.find_one({"_id": oid})
    if not existing:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    update_fields = {}
    if camera.name is not None:
        update_fields["name"] = camera.name.strip()
    if camera.url is not None:
        update_fields["url"] = camera.url.strip()
    if camera.endpoint is not None:
        update_fields["endpoint"] = camera.endpoint.strip() if camera.endpoint else None
    
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update.")
    
    await col.update_one({"_id": oid}, {"$set": update_fields})
    updated = await col.find_one({"_id": oid})
    return _serialize(updated)

@app.delete("/cameras/{camera_id}")
async def delete_camera(camera_id: str):
    col = get_camera_collection()
    try:
        oid = ObjectId(camera_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid camera ID")
    cam = await col.find_one({"_id": oid})
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    stream_factory.close_track(cam["url"])
    await col.delete_one({"_id": oid})
    return {"status": "success", "deleted": camera_id}

# ─── Worker CRUD ──────────────────────────────────────────────────────────────

@app.get("/workers")
async def list_workers():
    col = get_worker_collection()
    workers = await col.find().sort("created_at", -1).to_list(length=1000)
    return [_serialize(w) for w in workers]

@app.post("/workers", status_code=201)
async def create_worker(worker: WorkerIn):
    col = get_worker_collection()

    if not worker.name.strip():
        raise HTTPException(status_code=400, detail="Worker name cannot be empty.")
    if not worker.dob.strip():
        raise HTTPException(status_code=400, detail="Date of birth is required.")
    if not worker.department.strip():
        raise HTTPException(status_code=400, detail="Department is required.")

    # Generate unique employee_id
    base_id    = _generate_employee_id(worker.name, worker.dob)
    employee_id = await _unique_employee_id(col, base_id)

    # Generate QR code encoding the employee_id
    qr_b64 = _generate_qr_b64(employee_id)

    doc = {
        "name":        worker.name.strip(),
        "dob":         worker.dob.strip(),
        "department":  worker.department.strip(),
        "email":       worker.email.strip() if worker.email else "",
        "employee_id": employee_id,
        "qr_code":     qr_b64,
        "created_at":  datetime.utcnow().isoformat(),
    }
    result = await col.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc

@app.put("/workers/{worker_id}")
async def update_worker(worker_id: str, worker: WorkerUpdate):
    col = get_worker_collection()
    try:
        oid = ObjectId(worker_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid worker ID")

    existing = await col.find_one({"_id": oid})
    if not existing:
        raise HTTPException(status_code=404, detail="Worker not found")

    update_fields = {}
    if worker.name is not None:
        update_fields["name"] = worker.name.strip()
    if worker.dob is not None:
        update_fields["dob"] = worker.dob.strip()
    if worker.department is not None:
        update_fields["department"] = worker.department.strip()
    if worker.email is not None:
        update_fields["email"] = worker.email.strip()

    # Regenerate employee_id and QR if name or DOB changed
    if "name" in update_fields or "dob" in update_fields:
        new_name = update_fields.get("name", existing["name"])
        new_dob  = update_fields.get("dob",  existing["dob"])
        base_id  = _generate_employee_id(new_name, new_dob)
        # Allow same ID if only updating unrelated fields of same person
        new_eid  = base_id
        suffix   = 2
        while True:
            conflict = await col.find_one({"employee_id": new_eid, "_id": {"$ne": oid}})
            if not conflict:
                break
            new_eid = f"{base_id}-{suffix}"
            suffix += 1
        update_fields["employee_id"] = new_eid
        update_fields["qr_code"]     = _generate_qr_b64(new_eid)

    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update.")

    await col.update_one({"_id": oid}, {"$set": update_fields})
    updated = await col.find_one({"_id": oid})
    return _serialize(updated)

@app.delete("/workers/{worker_id}")
async def delete_worker(worker_id: str):
    wcol = get_worker_collection()
    acol = get_attendance_collection()
    try:
        oid = ObjectId(worker_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid worker ID")

    worker = await wcol.find_one({"_id": oid})
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    # Delete worker and all their attendance records
    await wcol.delete_one({"_id": oid})
    await acol.delete_many({"worker_id": worker_id})
    return {"status": "success", "deleted": worker_id}

# ─── Attendance ────────────────────────────────────────────────────────────────

@app.post("/attendance/scan")
async def scan_attendance(req: ScanRequest):
    """Receive a QR-decoded string, look up the worker, and mark attendance."""
    if not req.qr_data or not req.qr_data.strip():
        raise HTTPException(status_code=400, detail="QR data is empty or invalid.")

    qr_data    = req.qr_data.strip()
    wcol       = get_worker_collection()
    acol       = get_attendance_collection()

    # Find worker by employee_id encoded in QR
    worker = await wcol.find_one({"employee_id": qr_data})
    if not worker:
        raise HTTPException(
            status_code=404,
            detail=f"No worker registered with ID '{qr_data}'. QR code not found in system."
        )

    today = date.today().isoformat()   # "YYYY-MM-DD"
    now   = datetime.now()

    # Duplicate check — only one attendance record per worker per day
    existing = await acol.find_one({"worker_id": str(worker["_id"]), "date": today})
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"{worker['name']} is already marked Present for today at {existing['time']}."
        )

    record = {
        "worker_id":   str(worker["_id"]),
        "employee_id": worker["employee_id"],
        "name":        worker["name"],
        "department":  worker["department"],
        "date":        today,
        "time":        now.strftime("%I:%M %p"),
        "timestamp":   now.isoformat(),
        "status":      "Present",
    }
    await acol.insert_one(record)
    record.pop("_id", None)
    return {"status": "success", "message": f"{worker['name']} marked Present at {record['time']}", "record": record}

@app.get("/attendance")
async def get_attendance(date: Optional[str] = None):
    """Return attendance records. Optional ?date=YYYY-MM-DD filter."""
    acol = get_attendance_collection()
    query = {"date": date} if date else {}
    records = await acol.find(query).sort("timestamp", -1).to_list(length=5000)
    return [_serialize(r) for r in records]

@app.get("/attendance/today")
async def get_today_attendance():
    today = date.today().isoformat()
    acol  = get_attendance_collection()
    records = await acol.find({"date": today}).sort("timestamp", -1).to_list(length=1000)
    return [_serialize(r) for r in records]

# ─── WebRTC Signaling ──────────────────────────────────────────────────────────

@app.post("/offer")
async def offer(params: OfferRequest):
    offer_sdp = RTCSessionDescription(sdp=params.sdp, type=params.type)
    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print(f"Connection state is {pc.connectionState}: {params.camera_url}")
        if pc.connectionState in ("failed", "closed"):
            pcs.discard(pc)

    # Get camera endpoint from database
    camera_col = get_camera_collection()
    camera_doc = await camera_col.find_one({"url": params.camera_url})
    endpoint = camera_doc.get("endpoint") if camera_doc else None

    video_track = stream_factory.get_or_create_track(
        params.camera_url, 
        params.monitored_ppe,
        endpoint
    )
    pc.addTrack(video_track)

    await pc.setRemoteDescription(offer_sdp)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}

@app.post("/close_camera")
async def close_camera(payload: dict):
    url = payload.get("camera_url")
    if url:
        stream_factory.close_track(url)
        return {"status": "success", "msg": f"Closed {url}"}
    return {"status": "error", "msg": "Missing camera_url"}

# ─── Graceful Shutdown ─────────────────────────────────────────────────────────

@app.on_event("shutdown")
async def on_shutdown():
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
