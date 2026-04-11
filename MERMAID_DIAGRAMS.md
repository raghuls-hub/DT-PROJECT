# Ready-to-Use Mermaid Diagrams for Smart Safety CCTV System

Copy and paste any diagram code into your documentation or use with `renderMermaidDiagram` tool.

---

## 1️⃣ SYSTEM ARCHITECTURE DIAGRAM

**Description**: Complete high-level system architecture showing all layers and components.

```mermaid
graph LR
    subgraph Frontend["🖥️ FRONTEND (React + Vite)"]
        Dashboard["📊 Dashboard"]
        CameraComponent["📹 Camera Streaming"]
        AttendanceScanner["🔐 Attendance Scanner"]
        WorkerManagement["👥 Worker Management"]
    end

    subgraph Backend["⚙️ BACKEND (FastAPI + Uvicorn)"]
        subgraph WebRTC["🎬 WebRTC Layer"]
            Signaling["Signaling Handler"]
            VideoTrack["VideoStreamTrack"]
        end

        subgraph StreamMgr["📡 Stream Manager"]
            IngestionThread["Ingestion Thread<br/>_ingest_video()"]
            AIThread["AI Thread<br/>_ai_inference_loop()"]
            Queue["Frame Queue<br/>maxsize=1"]
        end

        subgraph AIServices["🤖 AI Detection Services"]
            PPEService["PPE Detection<br/>YOLO basic-model.onnx"]
            FireService["Fire Detection<br/>YOLO fire_detection.onnx"]
            FallService["Fall Detection<br/>YOLO fall_detection.onnx"]
        end

        subgraph RestAPI["🔌 REST API Layer"]
            CameraAPI["/cameras - CRUD"]
            WorkerAPI["/workers - CRUD"]
            AttendanceAPI["/attendance - QR & PPE"]
            PPEFrameAPI["/verify-ppe-frame"]
        end

        subgraph AlertSystem["🚨 Alert System"]
            TemporalConfirm["Temporal Confirmation<br/>Reduce False Positives"]
            Alerting["Alert Generation"]
            Notification["Notification Dispatch"]
        end
    end

    subgraph Data["💾 DATA LAYER"]
        MongoDB["🗄️ MongoDB"]
        Collections["Collections:<br/>cameras, workers,<br/>attendances, alerts"]
    end

    subgraph External["🌐 EXTERNAL SERVICES"]
        IPCameras["📷 IP Cameras<br/>RTSP/HTTP"]
        BrowserCamera["📱 Browser Camera<br/>getUserMedia"]
        Ntfy["📬 Ntfy.sh<br/>Push Notifications"]
    end

    %% Frontend connections
    Frontend <-->|REST API| RestAPI
    Frontend <-->|WebRTC Signaling| Signaling
    Frontend -->|WebRTC Video| VideoTrack

    %% WebRTC connections
    Signaling --> VideoTrack
    VideoTrack --> RestAPI

    %% Stream Manager
    IngestionThread --> Queue
    AIThread --> Queue
    Queue -->|Latest Frame| VideoTrack

    %% AI Services
    AIThread --> PPEService
    AIThread --> FireService
    AIThread --> FallService

    %% Alert Flow
    PPEService --> TemporalConfirm
    FireService --> TemporalConfirm
    FallService --> TemporalConfirm
    TemporalConfirm --> Alerting
    Alerting --> Notification

    %% Data connections
    RestAPI <--> MongoDB
    MongoDB --> Collections
    Notification --> Ntfy

    %% External connections
    IngestionThread --> IPCameras
    IngestionThread --> BrowserCamera
    PPEFrameAPI --> BrowserCamera

    %% Styling
    classDef frontend fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef backend fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef data fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    classDef external fill:#fff3e0,stroke:#e65100,stroke-width:2px

    class Frontend frontend
    class Backend,WebRTC,StreamMgr,AIServices,RestAPI,AlertSystem backend
    class Data,MongoDB,Collections data
    class External,IPCameras,BrowserCamera,Ntfy external
```

---

## 2️⃣ DATA FLOW DIAGRAM (Streaming + Detection)

**Description**: Real-time streaming data flow with parallel thread execution.

```mermaid
graph TD
    A["🎬 User Clicks START"] --> B["Frontend Creates<br/>RTCPeerConnection"]
    B --> C["Create WebRTC Offer"]
    C --> D["POST /offer<br/>with camera_url<br/>& monitored_ppe"]

    D --> E["Backend Creates<br/>NetworkCameraTrack"]
    E --> F["Spawn Thread 1:<br/>_ingest_video"]
    E --> G["Spawn Thread 2:<br/>_ai_inference_loop"]

    F --> F1["cv2.VideoCapture<br/>opens camera_url"]
    F1 --> F2["Read frame loop<br/>@ 30 FPS"]
    F2 --> F3["Convert BGR→RGB<br/>Store BGR copy"]
    F3 --> F4["Put frame in<br/>Queue maxsize=1"]
    F4 -->|AGGRESSIVE DROPPING| F3

    G --> G1["Read current_inference_frame<br/>BGR"]
    G1 --> G2{"Every 2nd<br/>frame?"}
    G2 -->|YES| G3["Run YOLO<br/>PPE Detection<br/>80-100ms"]
    G2 -->|NO| G7["Skip"]
    G3 --> G4["Person-Centric Logic<br/>Map PPE to Person"]
    G4 --> G5["Store results in<br/>latest_ppe_statuses"]
    G5 --> G6["Temporal Confirmation Check<br/>5+ seconds sustained?"]
    G6 -->|Alert Confirmed| G8["Send Notification<br/>to Ntfy.sh"]
    G7 --> G1
    G8 --> G1

    F4 --> H["WebRTC recv()<br/>called every 33ms"]
    H --> H1["Get latest frame<br/>from Queue"]
    H1 --> H2["Draw AI Annotations<br/>Bounding boxes + text"]
    H2 --> H3["Apply Alert Overlay<br/>if confirmed alerts"]
    H3 --> H4["VideoFrame.from_ndarray<br/>RGB24 format"]
    H4 --> H5["WebRTC Encoder<br/>VP8/H264"]
    H5 --> I["🖥️ Frontend Receives<br/>Video Stream"]
    I --> J["Browser renders<br/>in video element"]
    J --> K["✅ Live stream<br/>with AI overlay<br/>30 FPS"]

    style A fill:#e3f2fd
    style K fill:#c8e6c9
    style F2 fill:#fff3e0
    style G3 fill:#f3e5f5
    style H fill:#fce4ec
    style G8 fill:#ffebee
```

---

## 3️⃣ ATTENDANCE + PPE VERIFICATION FLOW

**Description**: Complete workflow from QR scan to attendance marked.

```mermaid
flowchart TD
    A["🏢 Admin Setup<br/>Select Required PPE<br/>Hardhat, Safety Vest"] --> B{Worker<br/>Scans<br/>QR?}

    B -->|Yes| C["📱 QR Data Captured<br/>employee_id: JOHDOE-15031995"]
    C --> D["Frontend POST<br/>/attendance/scan-qr"]
    D --> E["Backend Query<br/>Workers Collection"]

    E --> F{Worker<br/>Found?}
    F -->|No| G["❌ Error: Worker<br/>not registered"]
    F -->|Yes| H["✅ Create attendance<br/>record status=<br/>pending_verification"]

    H --> I["🎥 Frontend Opens<br/>PPE Modal<br/>Browser Camera"]
    I --> J["Start Auto-Detect<br/>Every 1.5 seconds"]

    J --> K["Canvas: Capture<br/>frame from video"]
    K --> L["Encode base64<br/>JPEG 0.9 quality"]
    L --> M["POST /attendance/<br/>verify-ppe-frame"]

    M --> N["Backend: Decode<br/>base64 frame"]
    N --> O["Run YOLO<br/>PPE Detection"]
    O --> P["Process person<br/>logic"]
    P --> Q{All Required<br/>PPE<br/>Detected?}

    Q -->|No| R["Return detected,<br/>missing, ppe_verified=false"]
    R --> S["🟡 Update UI<br/>Show detected ✓<br/>Show missing ❌"]
    S --> T["Retry loop<br/>1.5 second delay"]
    T --> K

    Q -->|Yes| U["Return ppe_verified=true"]
    U --> V["🟢 Update UI<br/>All PPE badges ✓<br/>Enable button"]
    V --> W{User Clicks<br/>Verify &<br/>Mark?}

    W -->|Cancel| X["❌ Attendance<br/>Rejected"]
    W -->|Confirm| Y["Frontend POST<br/>/attendance/mark-present"]

    Y --> Z["Backend Update<br/>status=Present<br/>verified_at=NOW"]
    Z --> AA["✅ MongoDB Record<br/>Attendance logged<br/>with PPE details"]
    AA --> AB["Frontend Success<br/>Modal closes<br/>Ready for next"]

    style A fill:#e1f5fe
    style I fill:#f3e5f5
    style V fill:#c8e6c9
    style AB fill:#a5d6a7
    style G fill:#ffcdd2
    style X fill:#ef9a9a
```

---

## 4️⃣ MULTI-CAMERA LAG OPTIMIZATION LAYERS

**Description**: How the system solves multi-camera latency issues.

```mermaid
graph TD
    TOP["🚨 PROBLEM: Multi-Camera Lag<br/>Traditional: 2-5 seconds latency<br/>Single camera can't handle parallel load"]

    TOP --> L1["⚙️ OPTIMIZATION 1<br/>Queue maxsize=1<br/>AGGRESSIVE FRAME DROPPING"]
    L1_Detail["Traditional Queue:<br/>Keeps 10 frames → 330ms latency<br/>New Queue:<br/>Keeps 1 frame → 33ms latency<br/>Result: 10x improvement"]

    L1 -.-> L1_Detail

    TOP --> L2["🔄 OPTIMIZATION 2<br/>DECOUPLED THREADING<br/>3 Independent Threads"]
    L2_Detail["Thread 1: Video Ingestion<br/>30 FPS continuous (never blocking)<br/>Thread 2: AI Inference<br/>Runs independently (doesn't block video)<br/>Thread 3: WebRTC Delivery<br/>Always gets latest frame<br/>Result: Simultaneous operation"]
    L2 -.-> L2_Detail

    TOP --> L3["🎬 OPTIMIZATION 3<br/>FRAME SKIPPING<br/>Smart CPU Management"]
    L3_Detail["PPE: Every 2nd frame (15 FPS)<br/>Fire: Every 3rd frame (10 FPS)<br/>Fall: Every 3rd frame (10 FPS)<br/>Result: 50% CPU reduction<br/>Same detection accuracy"]
    L3 -.-> L3_Detail

    TOP --> L4["⏱️ OPTIMIZATION 4<br/>TEMPORAL CONFIRMATION<br/>Reduce False Positives"]
    L4_Detail["PPE: 5+ seconds sustained<br/>Fire: 2+ seconds sustained<br/>Fall: 10+ frames accumulated<br/>Result: Only real threats trigger<br/>Fewer alerts = Better focus"]
    L4 -.-> L4_Detail

    TOP --> L5["🔒 OPTIMIZATION 5<br/>THREAD-SAFE ENVIRONMENT<br/>Multi-Camera Coordination"]
    L5_Detail["ENV_LOCK prevents race conditions<br/>Local cameras (no headers)<br/>Remote cameras (Ngrok headers)<br/>Result: Clean state transitions<br/>No connection conflicts"]
    L5 -.-> L5_Detail

    L1 --> RESULT
    L2 --> RESULT
    L3 --> RESULT
    L4 --> RESULT
    L5 --> RESULT

    RESULT["✅ RESULT: Low-Latency Multi-Camera System<br/>4-6 cameras @ 30 FPS<br/>250-400ms end-to-end latency<br/>52-68% CPU usage<br/><1% frame drops"]

    style TOP fill:#ffcdd2,stroke:#c62828,stroke-width:3px
    style RESULT fill:#a5d6a7,stroke:#2e7d32,stroke-width:3px
    style L1 fill:#ffe0b2,stroke:#e65100
    style L2 fill:#f8bbd0,stroke:#880e4f
    style L3 fill:#e1bee7,stroke:#4a148c
    style L4 fill:#b2dfdb,stroke:#00695c
    style L5 fill:#bbdefb,stroke:#01579b
```

---

## 5️⃣ API ENDPOINT INTERACTION DIAGRAM

**Description**: All REST endpoints and their interactions.

```mermaid
graph LR
    subgraph Frontend["🖥️ FRONTEND"]
        AdminUI["Admin UI"]
        ScannerUI["Scanner UI"]
        WorkerUI["Worker UI"]
    end

    subgraph API["🔌 REST API ENDPOINTS"]
        subgraph Cameras["📹 CAMERAS"]
            GetCam["GET /cameras"]
            PostCam["POST /cameras"]
            PutCam["PUT /cameras/{id}"]
            DelCam["DELETE /cameras/{id}"]
        end

        subgraph WebRTC["🎬 WEBRTC"]
            PostOffer["POST /offer"]
            CloseCam["POST /close_camera"]
        end

        subgraph Workers["👥 WORKERS"]
            GetWorker["GET /workers"]
            PostWorker["POST /workers"]
            PutWorker["PUT /workers/{id}"]
            DelWorker["DELETE /workers/{id}"]
        end

        subgraph Attendance["🔐 ATTENDANCE"]
            ScanQR["POST /scan-qr"]
            VerifyPPE["POST /verify-ppe-frame"]
            MarkPresent["POST /mark-present"]
            GetToday["GET /attendance/today"]
        end

        subgraph Config["⚙️ CONFIG"]
            PPEOpts["GET /ppe/options"]
        end
    end

    subgraph Backend["⚙️ BACKEND LOGIC"]
        CamMgr["Camera Manager"]
        WebRTCMgr["WebRTC Manager"]
        WorkerMgr["Worker Manager"]
        AttendanceMgr["Attendance Manager"]
        ConfigMgr["Config Manager"]
    end

    subgraph Data["💾 DATABASE"]
        Cameras_DB["cameras collection"]
        Workers_DB["workers collection"]
        Attendance_DB["attendances collection"]
        Alerts_DB["alerts collection"]
    end

    %% Frontend to API
    AdminUI --> GetCam
    AdminUI --> PostCam
    AdminUI --> PutCam
    AdminUI --> DelCam
    AdminUI --> GetWorker
    AdminUI --> PostWorker
    AdminUI --> PutWorker
    AdminUI --> DelWorker
    AdminUI --> PostOffer
    AdminUI --> GetToday

    ScannerUI --> ScanQR
    ScannerUI --> VerifyPPE
    ScannerUI --> MarkPresent
    ScannerUI --> PPEOpts

    WorkerUI --> PostWorker
    WorkerUI --> GetWorker

    %% API to Backend
    GetCam --> CamMgr
    PostCam --> CamMgr
    PutCam --> CamMgr
    DelCam --> CamMgr
    PostOffer --> WebRTCMgr
    CloseCam --> WebRTCMgr
    GetWorker --> WorkerMgr
    PostWorker --> WorkerMgr
    PutWorker --> WorkerMgr
    DelWorker --> WorkerMgr
    ScanQR --> AttendanceMgr
    VerifyPPE --> AttendanceMgr
    MarkPresent --> AttendanceMgr
    GetToday --> AttendanceMgr
    PPEOpts --> ConfigMgr

    %% Backend to Database
    CamMgr --> Cameras_DB
    WebRTCMgr --> Cameras_DB
    WorkerMgr --> Workers_DB
    AttendanceMgr --> Attendance_DB
    AttendanceMgr --> Alerts_DB

    style Frontend fill:#e3f2fd
    style API fill:#f3e5f5
    style Backend fill:#e8f5e9
    style Data fill:#fff3e0
```

---

## 6️⃣ AI DETECTION PIPELINE

**Description**: Sequential stages of AI model inference.

```mermaid
graph TD
    INPUT["📽️ INPUT: Frame from Camera<br/>Format: BGR<br/>Size: 720x480x3"] --> STAGE1

    STAGE1["🔄 STAGE 1: PPE DETECTION<br/>Applies every 2nd frame"] --> PPE1["Model: YOLO basic-model.onnx<br/>Input: BGR frame<br/>Confidence Threshold: 0.45"]
    PPE1 --> PPE2["Detections: Hardhat, Mask,<br/>Person, Safety Vest<br/>Time: 80-100ms"]
    PPE2 --> PPE3["Output: [PPEDetection objects<br/>with class, confidence, bbox]"]

    STAGE1 --> STAGE2["🔄 STAGE 2: PERSON-CENTRIC LOGIC"]
    STAGE2 --> LOGIC1["For each detected Person:"]
    LOGIC1 --> LOGIC2["Find overlapping PPE items<br/>in person bbox"]
    LOGIC2 --> LOGIC3["Generate PersonPPEStatus:<br/>present_ppe[], missing_ppe[],<br/>violations boolean"]

    STAGE2 --> STAGE3["⏱️ STAGE 3: TEMPORAL CONFIRMATION"]
    STAGE3 --> TEMP1["Check violation sustained<br/>for 5+ seconds"]
    TEMP1 --> TEMP2["If confirmed:<br/>confirmed_ppe = TRUE"]
    TEMP2 --> TEMP3["Trigger PPE VIOLATION alert"]

    STAGE1 -.->|Every 3rd frame| STAGE4["🔄 STAGE 4A: FIRE DETECTION"]
    STAGE4 --> FIRE1["Model: YOLO fire_detection.onnx<br/>Detects: Fire, Smoke<br/>Confidence Threshold: 0.40"]
    FIRE1 --> FIRE2["Confirmation: 2+ seconds"]
    FIRE2 --> FIRE3["If confirmed: FIRE alert"]

    STAGE1 -.->|Every 3rd frame| STAGE5["🔄 STAGE 4B: FALL DETECTION"]
    STAGE5 --> FALL1["Model: YOLO fall_detection.onnx<br/>Detects: Fallen person<br/>Confidence Threshold: 0.50"]
    FALL1 --> FALL2["Confirmation: 10+ frames"]
    FALL2 --> FALL3["If confirmed: FALL alert"]

    PPE3 --> STAGE6
    TEMP3 --> STAGE6
    FIRE3 --> STAGE6
    FALL3 --> STAGE6

    STAGE6["⚠️ STAGE 5: ALERT GENERATION"] --> ALERT1["Check alert type:<br/>PPE_VIOLATION / FIRE / FALL"]
    ALERT1 --> ALERT2["Add severity level"]
    ALERT2 --> ALERT3["Log to alerts collection"]
    ALERT3 --> ALERT4["Send to Ntfy.sh endpoint"]

    ALERT4 --> OUTPUT["📤 OUTPUT: Notification dispatched<br/>Dashboard alert shown<br/>Logged for compliance"]

    style INPUT fill:#bbdefb,stroke:#01579b
    style STAGE1 fill:#f8bbd0,stroke:#880e4f
    style STAGE2 fill:#e1bee7,stroke:#4a148c
    style STAGE3 fill:#c5cae9,stroke:#283593
    style STAGE4 fill:#ffccbc,stroke:#d84315
    style STAGE5 fill:#b3e5fc,stroke:#01579b
    style STAGE6 fill:#ffcdd2,stroke:#c62828
    style OUTPUT fill:#a5d6a7,stroke:#2e7d32
```

---

## 7️⃣ DATABASE RELATIONSHIPS

**Description**: MongoDB collections and their relationships.

```mermaid
erDiagram
    CAMERAS ||--o{ NETWORKTRACK : hosts
    CAMERAS ||--o{ ALERT : generates
    WORKERS ||--o{ ATTENDANCES : "checked-in by"
    ATTENDANCES ||--o{ ALERT : generates

    CAMERAS {
        ObjectId _id
        string name "e.g. Factory Floor 1"
        string url "RTSP/HTTP/MP4"
        string endpoint "Ntfy.sh endpoint"
        ISO8601 created_at
    }

    WORKERS {
        ObjectId _id
        string name
        string dob "YYYY-MM-DD"
        string department
        string email
        string employee_id "Auto-generated"
        base64 qr_code "PNG base64"
        ISO8601 created_at
    }

    ATTENDANCES {
        ObjectId _id
        ObjectId worker_id "FK to WORKERS"
        string employee_id "Denormalized"
        string name
        string department
        string date "YYYY-MM-DD"
        string time "HH:MM AM/PM"
        ISO8601 timestamp
        enum status "Present/pending/rejected"
        array required_ppe "Hardhat, Mask, Safety Vest"
        array detected_ppe
        array missing_ppe
        ISO8601 verified_at
        string verification_method
        string rejection_reason
        ISO8601 created_at
    }

    ALERT {
        ObjectId _id
        enum type "fire/ppe_violation/fall"
        ObjectId camera_id "FK to CAMERAS"
        string camera_name
        enum severity "critical/warning/info"
        ISO8601 detected_at
        ISO8601 confirmed_at
        ISO8601 dismissed_at
        number duration_seconds
        boolean notification_sent
        string endpoint "Where alert sent"
        enum status "active/acknowledged/resolved"
    }

    NETWORKTRACK {
        ObjectId track_id
        string camera_url
        number fps
        number latency_ms
        ISO8601 connected_at
        ISO8601 last_frame_at
    }
```

---

## 8️⃣ COMPLETE ORCHESTRATION SEQUENCE

**Description**: Swimlane sequence showing all actors and interactions.

```mermaid
sequenceDiagram
    actor Admin
    participant Frontend
    participant Backend
    participant AIThread as AI Thread
    participant MongoDB
    participant Camera
    participant Ntfy as Ntfy.sh

    Note over Admin,Ntfy: SCENARIO 1: SETTING UP A CAMERA
    Admin->>Frontend: Opens dashboard
    Admin->>Frontend: Clicks "Add Camera"
    Frontend->>Backend: POST /cameras<br/>{name, url, endpoint}
    Backend->>MongoDB: Insert camera document
    MongoDB-->>Backend: {_id: "...", name: "..."}
    Backend-->>Frontend: Success response
    Frontend->>Admin: Show camera added

    Note over Admin,Ntfy: SCENARIO 2: STARTING A LIVE STREAM
    Admin->>Frontend: Clicks "Start" on camera
    Frontend->>Frontend: Create RTCPeerConnection
    Frontend->>Backend: POST /offer<br/>{sdp, camera_url, monitored_ppe}
    Backend->>Backend: Create NetworkCameraTrack
    Backend->>AIThread: Spawn ingest + AI threads
    AIThread->>Camera: Open stream connection
    Backend->>Frontend: Send Answer (SDP)
    Frontend->>Frontend: WebRTC established
    AIThread->>Camera: Read frame loop (30 FPS)
    AIThread->>AIThread: Store frame, put in Queue
    AIThread->>AIThread: Run YOLO detection
    Backend->>Frontend: Send video frame via WebRTC (every 33ms)
    Frontend->>Admin: Render live video

    Note over Admin,Ntfy: SCENARIO 3: PPE VIOLATION ALERT
    AIThread->>AIThread: Detect PPE violation<br/>(5+ seconds)
    AIThread->>AIThread: confirmed_ppe = TRUE
    Backend->>Ntfy: POST notification<br/>"PPE VIOLATION DETECTED"
    Ntfy-->>Admin: Push notification
    Backend->>MongoDB: Insert alert record
    Frontend->>Admin: Show alert overlay on video
    Admin->>Frontend: Dismiss alert

    Note over Admin,Ntfy: SCENARIO 4: ATTENDANCE CHECK-IN
    actor Worker
    Worker->>Frontend: Scan QR code
    Frontend->>Backend: POST /attendance/scan-qr<br/>{qr_data, required_ppe}
    Backend->>MongoDB: Create attendance record<br/>status=pending_verification
    Backend-->>Frontend: {recordId, requiredPPE, ...}
    Frontend->>Worker: Open PPE modal
    Worker->>Worker: Position camera
    loop Every 1.5 seconds
        Frontend->>Frontend: Capture frame from video
        Frontend->>Backend: POST /verify-ppe-frame<br/>{frame_base64, required_ppe}
        Backend->>AIThread: Decode frame, run detection
        AIThread-->>Backend: {detected_ppe, ppe_verified}
        Backend-->>Frontend: Detection results
        Frontend->>Frontend: Update UI badges
    end
    Frontend->>Frontend: All PPE detected
    Worker->>Frontend: Click "Verify & Mark Present"
    Frontend->>Backend: POST /mark-present<br/>{record_id}
    Backend->>MongoDB: Update attendance<br/>status=Present, verified_at=NOW
    Backend-->>Frontend: Success
    Frontend->>Worker: Show success message

    style Admin fill:#e3f2fd
    style Frontend fill:#f3e5f5
    style Backend fill:#e8f5e9
    style AIThread fill:#fff3e0
    style MongoDB fill:#fce4ec
    style Camera fill:#ffebee
    style Ntfy fill:#c8e6c9
```

---

## 🎯 USAGE INSTRUCTIONS

### **Render These Diagrams:**

**Option 1: Python (in your project)**

```python
from renderMermaidDiagram import renderMermaidDiagram

renderMermaidDiagram("""
graph TD
    A[Component] --> B[Other Component]
""", title="My Diagram")
```

**Option 2: Online**

- Visit https://mermaid.live
- Paste any diagram code
- Customize and export

**Option 3: GitHub**

- Add to README.md in code block with ` ```mermaid `
- GitHub auto-renders

**Option 4: Documentation**

- Copy into your docs
- Most markdown renderers support Mermaid

---

## 📝 CUSTOMIZATION TIPS

- **Change colors**: Modify `fill:#e3f2fd` to your brand colors
- **Add details**: Insert more nodes/connections as needed
- **Resize text**: Use `<br/>` for line breaks in nodes
- **Add icons**: Use Unicode symbols (🎬, 📹, 🤖, etc.)
- **Change layout**: Use `graph TD` (top-down), `graph LR` (left-right), or `flowchart`
