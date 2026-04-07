# Smart Safety & CCTV Monitoring System

A robust, real-time AI-powered monitoring solution for industrial safety. This system leverages Computer Vision to detect PPE violations (Hardhat, Mask, Safety Vest), fire outbreaks, and fall incidents using high-performance ONNX models and WebRTC streaming.

## 🚀 Features

- **Real-Time AI Analytics**: Low-latency detection using YOLO models optimized with ONNX Runtime.
- **PPE Monitoring**: Automated checks for Hardhats, Masks, and Safety Vests.
- **Fire & Fall Detection**: Immediate identification of safety hazards.
- **WebRTC Streaming**: Efficient video streaming from cameras to the dashboard.
- **Attendance Management**: QR-code based worker attendance integration.
- **Interactive Dashboard**: Modern UI built with React and Vite.

## 🛠️ Tech Stack

- **Backend**: FastAPI, aiortc, OpenCV, Motor (MongoDB), Ultralytics (YOLO).
- **Frontend**: React, Vite, CSS (Modern Premium Design).
- **Database**: MongoDB.
- **AI/ML**: ONNX Runtime (GPU accelerated where available).

## 📋 Prerequisites

Before you begin, ensure you have the following installed:
- [Python 3.10+](https://www.python.org/downloads/)
- [Node.js & NPM](https://nodejs.org/)
- [MongoDB](https://www.mongodb.com/try/download/community) (Running locally or on Atlas)

## ⚙️ Installation & Setup

### 1. Clone the Repository
```bash
git clone <repository-url>
cd DT-Project
```

### 2. Models
The detection models are already included in the repository under the `models/` directory:
- `PPE_detection.onnx`
- `fire_detection.onnx`
- `fall_detection.onnx`

### 3. Backend Setup
1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On Linux/macOS:
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure environment variables:
   Create a `.env` file in the `backend/` folder (or edit the existing one):
   ```env
   MONGODB_URI=mongodb://localhost:27017
   ```
5. Start the backend server:
   ```bash
   uvicorn main:app --reload
   ```

### 4. Frontend Setup
1. Navigate to the frontend directory:
   ```bash
   cd ../frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the development server:
   ```bash
   npm run dev
   ```

## 🖥️ Usage

1. Open your browser and navigate to the frontend URL (usually `http://localhost:5173`).
2. Add your camera streams in the settings/dashboard.
3. Configure detection thresholds and PPE requirements for each camera.
4. Monitor real-time detections and alerts.

## 📁 Project Structure

```text
DT-Project/
├── backend/            # FastAPI application logic
│   ├── models/         # Perception & Detection services
│   ├── main.py         # Entry point
│   └── requirements.txt
├── frontend/           # React + Vite application
│   ├── src/            # Components & Styles
│   └── package.json
├── models/             # Compiled ONNX model weights
├── videos/             # Sample videos for testing
└── scripts/            # Helper test scripts (test_model_on_video.py, etc.)
```

## ⚖️ License
[Your License Choice] - See the LICENSE file for details.
