import asyncio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from aiortc import RTCPeerConnection, RTCSessionDescription
from pydantic import BaseModel

# Import our custom stream isolated factory
from stream_manager import stream_factory

app = FastAPI(title="Real-Time Video Analytics Signaling (Stage 1)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow React frontend Dev Server requests
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class OfferRequest(BaseModel):
    sdp: str
    type: str
    camera_url: str

# Keep track of peer connections to gracefully close on shutdown
pcs = set()

@app.post("/offer")
async def offer(params: OfferRequest):
    """
    WebRTC Signaling Endpoint.
    Receives an SDP Offer and a Target Camera URL.
    Spawns/Reuses the isolated Network track and returns the SDP Answer.
    """
    offer_sdp = RTCSessionDescription(sdp=params.sdp, type=params.type)
    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print(f"Connection state is {pc.connectionState}")
        if pc.connectionState == "failed" or pc.connectionState == "closed":
            pcs.discard(pc)

    # 1. Ask StreamManager for the isolated background track for this specific URL
    video_track = stream_factory.get_or_create_track(params.camera_url)
    
    # 2. Attach the generated aiortc track to this unique WebRTC peer connection
    pc.addTrack(video_track)

    # 3. Handle standard WebRTC SDP negotiation
    await pc.setRemoteDescription(offer_sdp)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return {
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    }

@app.post("/close_camera")
async def close_camera(payload: dict):
    """
    Hard-closes a camera ingestion thread when the user clicks 'X'
    """
    url = payload.get("camera_url")
    if url:
        stream_factory.close_track(url)
        return {"status": "success", "msg": f"Closed {url} and released threads."}
    return {"status": "error", "msg": "Missing camera_url"}

@app.on_event("shutdown")
async def on_shutdown():
    # close peering connections to free resources gracefully
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
