import asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from aiortc import RTCPeerConnection, RTCSessionDescription
from pydantic import BaseModel
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv()

from stream_manager import stream_factory
from database import get_camera_collection

app = FastAPI(title="Smart Safety CCTV System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Pydantic Models ───────────────────────────────────────────────────────────

class OfferRequest(BaseModel):
    sdp: str
    type: str
    camera_url: str

class CameraIn(BaseModel):
    name: str
    url: str

# ─── Helpers ───────────────────────────────────────────────────────────────────

def _serialize(doc: dict) -> dict:
    """Convert MongoDB _id ObjectId to string for JSON serialization."""
    doc["_id"] = str(doc["_id"])
    return doc

# ─── Track all peer connections for clean shutdown ─────────────────────────────

pcs = set()

# ─── Camera CRUD API ───────────────────────────────────────────────────────────

@app.get("/cameras")
async def list_cameras():
    """Return all saved cameras from MongoDB."""
    col = get_camera_collection()
    cameras = await col.find().to_list(length=200)
    return [_serialize(c) for c in cameras]

@app.post("/cameras", status_code=201)
async def add_camera(camera: CameraIn):
    """Save a new camera to MongoDB."""
    col = get_camera_collection()
    doc = {"name": camera.name, "url": camera.url}
    result = await col.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc

@app.delete("/cameras/{camera_id}")
async def delete_camera(camera_id: str):
    """Delete a camera from MongoDB and stop its stream thread."""
    col = get_camera_collection()
    
    try:
        oid = ObjectId(camera_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid camera ID")
    
    cam = await col.find_one({"_id": oid})
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Stop the live stream thread if it's running
    stream_factory.close_track(cam["url"])
    
    await col.delete_one({"_id": oid})
    return {"status": "success", "deleted": camera_id}

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

    video_track = stream_factory.get_or_create_track(params.camera_url)
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
