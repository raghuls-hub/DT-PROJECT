import asyncio
import qrcode
import io
import base64
import cv2
import numpy as np
import os
from datetime import datetime, date
from fastapi import FastAPI, HTTPException, UploadFile, File
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
from models.ppe_service import PPEService, PersonPPEStatus, detect_ppe_for_attendance
from config import AVAILABLE_PPE_OPTIONS, MONITORED_PPE_TYPES

# ─── Setup Paths ───────────────────────────────────────────────────────────────
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

app = FastAPI(title="Smart Safety CCTV System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Initialize PPE Services ───────────────────────────────────────────────────
# Live monitoring service — used exclusively by stream_manager / WebRTC pipeline
ppe_service = PPEService(model_path=os.path.join(ROOT_DIR, "models", "basic-model.onnx"))

# Attendance service — completely separate instance so attendance detection
# never blocks or interferes with live monitoring inference
ppe_service_attendance = PPEService(model_path=os.path.join(ROOT_DIR, "models", "basic-model.onnx"))

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
    required_ppe: Optional[List[str]] = None  # PPE classes required for this scan

class PPEDetectionRequest(BaseModel):
    required_ppe: List[str]
    frame_base64: Optional[str] = None  # Base64 encoded frame from browser
    camera_url: Optional[str] = None    # Alternative: camera URL from stream_factory

class PPEVerificationRequest(BaseModel):
    worker_id: str
    camera_url: str
    required_ppe: List[str]

class PPEVerificationResponse(BaseModel):
    worker_name: str
    required_ppe: List[str]
    detected_ppe: List[str]
    missing_ppe: List[str]
    ppe_verified: bool
    message: str

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
    """Receive a QR-decoded string, look up the worker, and create a pending attendance record.
    If required_ppe is provided, attendance will be marked as pending_verification.
    """
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

    # Determine attendance status based on PPE requirements
    if req.required_ppe and len(req.required_ppe) > 0:
        status = "pending_verification"
        message = f"{worker['name']} - Pending PPE verification"
    else:
        status = "Present"
        message = f"{worker['name']} marked Present at {now.strftime('%I:%M %p')}"

    record = {
        "worker_id":   str(worker["_id"]),
        "employee_id": worker["employee_id"],
        "name":        worker["name"],
        "department":  worker["department"],
        "date":        today,
        "time":        now.strftime("%I:%M %p"),
        "timestamp":   now.isoformat(),
        "status":      status,
        "required_ppe": req.required_ppe if req.required_ppe else [],
        "detected_ppe": [],
        "verified_at": None,
    }
    result = await acol.insert_one(record)
    record_id = str(result.inserted_id)
    record["_id"] = record_id
    record.pop("_id", None)
    
    return {
        "status": "success",
        "message": message,
        "record_id": record_id,
        "requires_ppe_verification": status == "pending_verification",
        "record": record
    }

@app.post("/attendance/verify-ppe")
async def verify_ppe_for_attendance(record_id: str, detected_ppe: List[str] = None):
    """Finalize attendance after PPE verification."""
    if not record_id:
        raise HTTPException(status_code=400, detail="Record ID is required.")
    
    acol = get_attendance_collection()
    
    try:
        oid = ObjectId(record_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid record ID.")
    
    record = await acol.find_one({"_id": oid})
    if not record:
        raise HTTPException(status_code=404, detail="Attendance record not found.")
    
    if record["status"] != "pending_verification":
        raise HTTPException(status_code=400, detail="Record is not pending PPE verification.")
    
    # Check if detected PPE meets requirements
    detected_ppe = detected_ppe or []
    required_ppe = set(record.get("required_ppe", []))
    detected_ppe_set = set(detected_ppe)
    
    missing_ppe = required_ppe - detected_ppe_set
    
    if missing_ppe:
        # PPE verification failed
        await acol.update_one(
            {"_id": oid},
            {
                "$set": {
                    "status": "rejected",
                    "detected_ppe": detected_ppe,
                    "verified_at": datetime.now().isoformat(),
                    "rejection_reason": f"Missing PPE: {', '.join(missing_ppe)}"
                }
            }
        )
        raise HTTPException(
            status_code=400,
            detail=f"PPE verification failed. Missing: {', '.join(missing_ppe)}"
        )
    
    # PPE verification passed
    now = datetime.now()
    await acol.update_one(
        {"_id": oid},
        {
            "$set": {
                "status": "Present",
                "detected_ppe": detected_ppe,
                "verified_at": now.isoformat(),
            }
        }
    )
    
    updated_record = await acol.find_one({"_id": oid})
    return {
        "status": "success",
        "message": f"{updated_record['name']} marked Present (PPE verified)",
        "record": _serialize(updated_record)
    }

@app.post("/attendance/verify-ppe-frame")
async def verify_ppe_frame(req: PPEDetectionRequest):
    """Run PPE detection on a base64 frame or camera URL.
    
    Accepts either:
    - frame_base64: Base64 encoded JPEG frame from browser camera
    - camera_url: Network camera URL to detect from
    """
    if not req.required_ppe or len(req.required_ppe) == 0:
        raise HTTPException(status_code=400, detail="No PPE classes specified to verify.")
    
    frame = None
    try:
        # Option 1: Use base64 frame from browser
        if req.frame_base64:
            import base64
            frame_bytes = base64.b64decode(req.frame_base64.split(",")[-1])
            nparr = np.frombuffer(frame_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if frame is None:
                raise ValueError("Failed to decode base64 frame")
        
        # Option 2: Use network camera
        elif req.camera_url:
            track = stream_factory.get_track(req.camera_url)
            if not track or not hasattr(track, 'latest_frame'):
                raise HTTPException(status_code=404, detail="Camera not accessible.")
            frame = track.latest_frame
            if frame is None:
                raise HTTPException(status_code=400, detail="No frame available from camera.")
        
        else:
            raise HTTPException(status_code=400, detail="Either frame_base64 or camera_url required.")
        
        if frame is None:
            raise HTTPException(status_code=400, detail="Could not obtain frame for detection.")
        
        # Run attendance-specific PPE detection in its own thread
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            detect_ppe_for_attendance,
            ppe_service_attendance,
            frame,
            req.required_ppe,
        )

        return {
            "status": "success",
            **result,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PPE detection error: {str(e)}")

@app.post("/attendance/verify-ppe-from-camera")
async def verify_ppe_from_camera(worker_id: str, camera_url: str, required_ppe: str):
    """Run PPE detection on a camera feed and return detected PPE for verification.
    
    Query params:
    - worker_id: worker identifier
    - camera_url: camera URL to detect from
    - required_ppe: comma-separated PPE classes (e.g., "Hardhat,Safety Vest")
    """
    if not required_ppe or required_ppe.strip() == "":
        raise HTTPException(status_code=400, detail="No PPE classes specified to verify.")
    
    # Parse comma-separated required_ppe
    required_ppe_list = [ppe.strip() for ppe in required_ppe.split(",")]
    
    try:
        # Get the camera track from stream_factory
        track = stream_factory.get_track(camera_url)
        if not track or not hasattr(track, 'latest_frame'):
            raise HTTPException(status_code=404, detail="Camera not accessible or no frame available.")
        
        # Get the latest frame
        frame = track.latest_frame
        if frame is None:
            raise HTTPException(status_code=400, detail="No frame available from camera.")
        
        # Run PPE detection
        detections = ppe_service.detect_ppe(frame)
        person_statuses = ppe_service.process_person_logic(detections, required_ppe_list)
        
        if not person_statuses:
            raise HTTPException(status_code=400, detail="No person detected in camera feed.")
        
        # Get the first person's PPE status
        person_status = person_statuses[0]
        detected_ppe = person_status.present_ppe
        
        return {
            "status": "success",
            "detected_ppe": detected_ppe,
            "missing_ppe": person_status.missing_ppe,
            "ppe_verified": not person_status.violations,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PPE verification error: {str(e)}")

@app.get("/ppe/options")
async def get_ppe_options():
    """Return available PPE classes for selection."""
    return {
        "available_ppe": MONITORED_PPE_TYPES,
        "all_ppe": AVAILABLE_PPE_OPTIONS
    }

@app.delete("/attendance/{record_id}")
async def cancel_attendance(record_id: str):
    """Delete a pending_verification attendance record (e.g. PPE timed out)."""
    acol = get_attendance_collection()
    try:
        oid = ObjectId(record_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid record ID.")
    record = await acol.find_one({"_id": oid})
    if not record:
        raise HTTPException(status_code=404, detail="Record not found.")
    if record["status"] != "pending_verification":
        raise HTTPException(status_code=400, detail="Only pending records can be cancelled.")
    await acol.delete_one({"_id": oid})
    return {"status": "cancelled", "record_id": record_id}

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
