import os
import time
import shutil
from fastapi import FastAPI, UploadFile, File, Form, Query, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.detector import VideoProcessor

app = FastAPI(title="Traffic Rules Violation Detection System Web App")

# Enable CORS for local testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths calculated dynamically relative to this file
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_APP_DIR = os.path.dirname(BACKEND_DIR)
STATIC_DIR = os.path.join(WEB_APP_DIR, "static")
FRONTEND_DIR = os.path.join(WEB_APP_DIR, "frontend")

# Consolidated project Resources folder (self-contained inside web_app)
RESOURCES_DIR = os.path.join(WEB_APP_DIR, "Resources")
if not os.path.exists(RESOURCES_DIR):
    # Fallback to original layout path if needed
    PARENT_DIR = os.path.dirname(WEB_APP_DIR)
    WORKSPACE_DIR = os.path.join(PARENT_DIR, "Traffic-Signal-Violation-Detection-System-master")
    if not os.path.exists(WORKSPACE_DIR):
        WORKSPACE_DIR = r"c:\Users\bisha\Desktop\Traffic-Signal-Violation-Detection-System-master\Traffic-Signal-Violation-Detection-System-master"
    RESOURCES_DIR = os.path.join(WORKSPACE_DIR, "Resources")


os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(FRONTEND_DIR, exist_ok=True)

# Initialize global processor
processor = VideoProcessor(static_dir=STATIC_DIR)

# Load historical violations from database on startup
try:
    print("Loading historical violation logs from database on startup...")
    db_violations = processor.db.get_all_violations()
    for v in reversed(db_violations):
        violation_info = {
            "id": len(processor.violations) + 1,
            "track_id": -1,
            "violation_id": v["violation_id"],
            "video_filename": v["video_filename"],
            "location": v["location"],
            "timestamp": v["timestamp_in_video"],
            "violation_type": v["violation_type"],
            "vehicle_type": v["vehicle_type"],
            "license_plate": v["license_plate"],
            "confidence": float(v["confidence"]),
            "crop_url": v["crop_url"],
            "detail_url": v["detail_url"],
            "challan_number": v["challan_number"],
            "challan_amount": float(v["challan_amount"]),
            "challan_status": v["challan_status"],
            "violator_name": v.get("violator_name", "Rajesh Kumar"),
            "violator_mobile": v.get("violator_mobile", "+91 98765 43210"),
            "query_status": v.get("query_status", "NONE"),
            "query_chat": v.get("query_chat", "[]")
        }
        processor.violations.insert(0, violation_info)
    print(f"Loaded {len(db_violations)} violations from database.")
except Exception as e:
    print(f"Error loading database logs on startup: {e}")

processing_progress = 0.0

def run_analysis_in_background(video_path: str):
    global processing_progress
    processing_progress = 0.0
    
    def progress_callback(progress_val):
        global processing_progress
        processing_progress = progress_val
        
    try:
        processor.process_video_batch(video_path, progress_callback=progress_callback)
    except Exception as e:
        print(f"Error in background video processing: {e}")
    finally:
        processing_progress = 100.0
        processor.is_running = False

def ping_self():
    import urllib.request
    import time
    app_domain = os.getenv("APP_DOMAIN")
    if not app_domain:
        print("No APP_DOMAIN environment variable set. Skipping self-ping keep-alive.")
        return
        
    if not app_domain.startswith("http"):
        app_domain = "https://" + app_domain
        
    print(f"Self-ping keep-alive service initiated for: {app_domain}")
    while True:
        time.sleep(540) # 9 minutes
        try:
            print(f"Self-pinging {app_domain} to keep service awake...")
            req = urllib.request.Request(
                app_domain,
                headers={'User-Agent': 'Mozilla/5.0 SentinelKeepAlive'}
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                response.read()
            print("Self-ping successful.")
        except Exception as e:
            print(f"Self-ping failed: {e}")

@app.on_event("startup")
def startup_event():
    import threading
    if os.getenv("APP_DOMAIN"):
        threading.Thread(target=ping_self, daemon=True).start()




class ROIModel(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    mode: str

class SignalModel(BaseModel):
    state: str

class DirectionConfigModel(BaseModel):
    allowed_direction: str  # "normal" or "reverse"

class ParkingConfigModel(BaseModel):
    parking_time_limit: float  # seconds

class TripleRiderConfigModel(BaseModel):
    max_allowed_riders: int
    inference_source: str

class HelmetConfigModel(BaseModel):
    inference_source: str

class AnalyzeModel(BaseModel):
    filename: str
    mode: str
    sampling_interval: float = 0.3

@app.get("/", response_class=HTMLResponse)
def get_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return """
    <html>
        <head><title>Setup Required</title></head>
        <body style="font-family: sans-serif; text-align: center; padding-top: 100px;">
            <h1>Traffic Violation Detection Web App</h1>
            <p>Frontend files are not created yet. Please check again later.</p>
        </body>
    </html>
    """

@app.get("/videos")
def list_videos():
    """Lists all video files available in Resources folder."""
    if not os.path.exists(RESOURCES_DIR):
        return []
    
    videos = []
    for f in os.listdir(RESOURCES_DIR):
        if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
            file_path = os.path.join(RESOURCES_DIR, f)
            size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 2)
            videos.append({"name": f, "size": f"{size_mb} MB"})
    return videos

@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """Allows uploading new video files into the Resources folder."""
    os.makedirs(RESOURCES_DIR, exist_ok=True)
    
    # Secure filename
    clean_name = os.path.basename(file.filename)
    dest_path = os.path.join(RESOURCES_DIR, clean_name)
    
    try:
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"filename": clean_name, "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

@app.get("/preview")
def get_video_preview(filename: str = Query(..., description="Name of video file in Resources")):
    """Reads the first frame of the video, saves it as a static image, and returns resolution."""
    import cv2
    
    video_path = os.path.join(RESOURCES_DIR, filename)
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video file not found")
        
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise HTTPException(status_code=400, detail="Could not open video file")
        
    ret, frame = cap.read()
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    
    if not ret:
        raise HTTPException(status_code=500, detail="Failed to read the first frame of the video")
        
    # Save preview image
    preview_path = os.path.join(STATIC_DIR, "preview.jpg")
    cv2.imwrite(preview_path, frame)
    
    # Cache buster to force browser reload
    return {
        "url": f"/static/preview.jpg?t={int(time.time())}",
        "width": width,
        "height": height
    }

@app.post("/set_roi")
def set_roi(roi: ROIModel):
    """Sets coordinates for either the line segment (signal/direction) or bounding rectangle (parking)."""
    processor.set_roi(roi.mode, roi.x1, roi.y1, roi.x2, roi.y2)
    return {
        "status": "success", 
        "mode": processor.mode,
        "line": processor.line,
        "parking_roi": processor.parking_roi
    }

@app.post("/toggle_signal")
def toggle_signal(model: SignalModel):
    """Toggles the traffic signal state (RED or GREEN) for signal mode."""
    state = model.state.upper()
    if state not in ("RED", "GREEN"):
        raise HTTPException(status_code=400, detail="Invalid signal state. Use RED or GREEN.")
    processor.set_signal_state(state)
    return {"status": "success", "signal_state": processor.signal_state}

@app.post("/config/direction")
def configure_direction(model: DirectionConfigModel):
    """Configures the wrong way direction logic (allowed direction of travel)."""
    allowed = model.allowed_direction.lower()
    if allowed not in ("normal", "reverse"):
        raise HTTPException(status_code=400, detail="Invalid allowed direction. Use 'normal' or 'reverse'.")
    processor.set_direction_config(allowed)
    return {"status": "success", "allowed_direction": processor.allowed_direction}

@app.post("/config/parking")
def configure_parking(model: ParkingConfigModel):
    """Configures the parking stationary duration limit in seconds."""
    if model.parking_time_limit <= 0:
        raise HTTPException(status_code=400, detail="Duration must be positive.")
    processor.set_parking_config(model.parking_time_limit)
    return {"status": "success", "parking_time_limit": processor.parking_time_limit}

@app.post("/config/triple_riding")
def configure_triple_riding(model: TripleRiderConfigModel):
    """Configures the triple rider detection parameters."""
    if model.max_allowed_riders < 1:
        raise HTTPException(status_code=400, detail="Max allowed riders must be positive.")
    source = model.inference_source.lower()
    if source not in ("local", "roboflow"):
        raise HTTPException(status_code=400, detail="Invalid inference source. Use 'local' or 'roboflow'.")
    processor.max_allowed_riders = model.max_allowed_riders
    processor.inference_source = source
    return {
        "status": "success",
        "max_allowed_riders": processor.max_allowed_riders,
        "inference_source": processor.inference_source
    }

@app.post("/config/helmet")
def configure_helmet(model: HelmetConfigModel):
    """Configures the helmet detection parameters."""
    source = model.inference_source.lower()
    if source not in ("local", "roboflow"):
        raise HTTPException(status_code=400, detail="Invalid inference source. Use 'local' or 'roboflow'.")
    processor.inference_source = source
    return {
        "status": "success",
        "inference_source": processor.inference_source
    }

@app.post("/analyze")
def start_analyze(model: AnalyzeModel, background_tasks: BackgroundTasks):
    """Starts background video batch processing."""
    if processor.is_running:
        raise HTTPException(status_code=400, detail="Analysis already running")
        
    video_path = os.path.join(RESOURCES_DIR, model.filename)
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video file not found")
        
    # Configure mode and sampling interval
    processor.mode = model.mode.lower()
    processor.sampling_interval = model.sampling_interval
    
    global processing_progress
    processing_progress = 0.0
    processor.is_running = True
    
    background_tasks.add_task(run_analysis_in_background, video_path)
    return {"status": "success", "message": "Analysis started in background"}

@app.get("/progress")
def get_progress():
    """Returns the current progress of batch processing."""
    global processing_progress
    return {
        "progress": processing_progress,
        "is_running": processor.is_running
    }

@app.get("/current_frame")
def get_current_frame():
    """Returns the latest annotated sampled frame from memory as a JPEG image."""
    if processor.latest_frame_bytes is None:
        # Return a transparent 1x1 pixel PNG to prevent broken image icon in browser
        transparent_1x1_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        from fastapi import Response
        return Response(content=transparent_1x1_png, media_type="image/png")
    from fastapi import Response
    return Response(content=processor.latest_frame_bytes, media_type="image/jpeg")

@app.post("/stop")
def stop_processing():
    """Stops the active video processing stream."""
    processor.stop()
    return {"status": "success"}

@app.get("/stats")
def get_stats():
    """Returns the current statistics, detected violations, and configuration state."""
    return {
        "stats": processor.stats,
        "violations": processor.violations,
        "mode": processor.mode,
        "signal_state": processor.signal_state,
        "allowed_direction": processor.allowed_direction,
        "parking_time_limit": processor.parking_time_limit,
        "max_allowed_riders": processor.max_allowed_riders,
        "inference_source": processor.inference_source,
        "is_running": processor.is_running
    }

@app.post("/clear_violations")
def clear_violations():
    """Clears all violation history and resets count statistics."""
    processor.reset_stats()
    try:
        processor.db.clear_all_violations()
    except Exception as e:
        print(f"Error clearing database table: {e}")
        
    # Clean the static violations folder
    violations_folder = os.path.join(STATIC_DIR, "violations")
    if os.path.exists(violations_folder):
        for f in os.listdir(violations_folder):
            file_path = os.path.join(violations_folder, f)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Error deleting file {file_path}: {e}")
    return {"status": "success"}

@app.get("/violation/{violation_id}", response_class=HTMLResponse)
def get_violation_details(violation_id: str):
    """Renders a beautiful e-challan and details page for the user."""
    v = processor.db.get_violation_by_id(violation_id)
    if not v:
        return HTMLResponse(
            status_code=404,
            content=f"""
            <html>
                <head>
                    <title>Violation Not Found</title>
                    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;700&display=swap" rel="stylesheet">
                    <style>
                        body {{ font-family: 'Outfit', sans-serif; background: #0f172a; color: #fff; text-align: center; padding-top: 100px; }}
                        h1 {{ color: #f97316; }}
                        a {{ color: #38bdf8; text-decoration: none; font-weight: bold; }}
                    </style>
                </head>
                <body>
                    <h1>404 - Violation Record Not Found</h1>
                    <p>The violation ID <strong>{violation_id}</strong> could not be found in our records.</p>
                    <p><a href="/ui/index.html">Return to Monitor Console</a></p>
                </body>
            </html>
            """
        )
        
    badge_class = "badge-paid" if v["challan_status"] == "PAID" else "badge-pending"
    disabled_attr = "disabled" if v["challan_status"] == "PAID" else ""
    pay_btn_style = "background: #22c55e; box-shadow: none;" if v["challan_status"] == "PAID" else ""
    pay_btn_text = "Payment Successful" if v["challan_status"] == "PAID" else "Pay Online"
    
    # Violator details and query status
    violator_name = v.get("violator_name") or "Rajesh Kumar"
    violator_mobile = v.get("violator_mobile") or "+91 98765 43210"
    query_chat_json = v.get("query_chat") or "[]"
    query_status = v.get("query_status") or "NONE"
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Challan Details - {v['violation_id']}</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
        <style>
            :root {{
                --primary: #0f172a;
                --accent: #f97316;
                --accent-green: #22c55e;
                --bg-gradient: linear-gradient(135deg, #1e293b, #0f172a);
                --card-bg: rgba(30, 41, 59, 0.7);
                --border-color: rgba(255, 255, 255, 0.1);
            }}
            
            body {{
                margin: 0;
                font-family: 'Outfit', sans-serif;
                background: var(--bg-gradient);
                color: #f8fafc;
                min-height: 100vh;
                display: flex;
                flex-direction: column;
            }}
            
            header {{
                background: rgba(15, 23, 42, 0.9);
                border-bottom: 2px solid var(--accent);
                padding: 15px 20px;
                text-align: center;
                box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            }}
            
            .gov-title {{
                font-weight: 800;
                font-size: 16px;
                letter-spacing: 2px;
                color: #fff;
                margin: 0;
                text-transform: uppercase;
            }}
            
            .gov-subtitle {{
                font-size: 11px;
                color: #94a3b8;
                margin: 5px 0 0 0;
                letter-spacing: 1px;
            }}
            
            .container {{
                max-width: 800px;
                margin: 40px auto;
                padding: 0 20px;
                flex-grow: 1;
            }}
            
            .card {{
                background: var(--card-bg);
                backdrop-filter: blur(12px);
                border: 1px solid var(--border-color);
                border-radius: 16px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.5);
                padding: 30px;
                margin-bottom: 30px;
            }}
            
            .grid {{
                display: grid;
                grid-template-columns: 1fr;
                gap: 30px;
            }}
            
            @media(min-width: 600px) {{
                .grid {{
                    grid-template-columns: 1fr 1fr;
                }}
            }}
            
            .evidence-container {{
                text-align: center;
            }}
            
            .evidence-img {{
                width: 100%;
                max-height: 300px;
                object-fit: contain;
                border-radius: 12px;
                border: 2px solid #ef4444;
                box-shadow: 0 5px 15px rgba(0,0,0,0.4);
            }}
            
            .badge {{
                display: inline-block;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 800;
                border-radius: 20px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            
            .badge-pending {{
                background: rgba(234, 179, 8, 0.2);
                color: #eab308;
                border: 1px solid #eab308;
            }}
            
            .badge-paid {{
                background: rgba(34, 197, 94, 0.2);
                color: #22c55e;
                border: 1px solid #22c55e;
            }}
            
            .violation-title {{
                font-size: 24px;
                font-weight: 800;
                margin-top: 0;
                color: #fff;
                border-bottom: 1px solid var(--border-color);
                padding-bottom: 10px;
            }}
            
            .detail-item {{
                margin-bottom: 15px;
            }}
            
            .label {{
                font-size: 12px;
                color: #94a3b8;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            
            .val {{
                font-size: 16px;
                font-weight: 600;
                margin-top: 4px;
            }}
            
            .challan-box {{
                background: rgba(15, 23, 42, 0.5);
                border: 1px dashed var(--border-color);
                border-radius: 12px;
                padding: 20px;
                text-align: center;
            }}
            
            .amount {{
                font-size: 32px;
                font-weight: 800;
                color: var(--accent);
                margin: 10px 0;
            }}
            
            .btn {{
                background: linear-gradient(90deg, #f97316, #ea580c);
                color: #fff;
                border: none;
                border-radius: 8px;
                padding: 14px 28px;
                font-size: 16px;
                font-weight: 800;
                cursor: pointer;
                width: 100%;
                transition: all 0.3s;
                text-transform: uppercase;
                box-shadow: 0 4px 15px rgba(249, 115, 22, 0.4);
            }}
            
            .btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(249, 115, 22, 0.6);
            }}
            
            .btn:disabled {{
                background: #475569;
                box-shadow: none;
                cursor: not-allowed;
                transform: none;
            }}
            
            /* Chat message bubbles styling */
            .message-bubble {{
                padding: 10px 14px;
                border-radius: 12px;
                max-width: 75%;
                font-size: 14px;
                line-height: 1.4;
                word-break: break-word;
                margin-bottom: 5px;
                display: flex;
                flex-direction: column;
            }}
            .bubble-user {{
                background: #f97316;
                color: #fff;
                align-self: flex-end;
                border-bottom-right-radius: 2px;
            }}
            .bubble-authority {{
                background: #334155;
                color: #f8fafc;
                align-self: flex-start;
                border-bottom-left-radius: 2px;
            }}
            .bubble-time {{
                font-size: 10px;
                color: rgba(255,255,255,0.6);
                text-align: right;
                margin-top: 4px;
                display: block;
            }}
            
            footer {{
                text-align: center;
                padding: 20px;
                font-size: 11px;
                color: #64748b;
                border-top: 1px solid var(--border-color);
            }}
        </style>
    </head>
    <body>

        <header>
            <p class="gov-title">🛡️ Ministry of Road Transport & Highways</p>
            <p class="gov-subtitle">Government of India • e-Challan Portal</p>
        </header>

        <div class="container">
            <div class="card">
                <h1 class="violation-title">{v['violation_type']}</h1>
                
                <div class="grid">
                    <div class="evidence-container">
                        <div class="label">Evidence Photo</div>
                        <img class="evidence-img" src="{v['crop_url']}" alt="Violation Crop Image" style="margin-top: 10px;">
                        <p style="font-size: 11px; color: #94a3b8; margin-top: 5px;">Target vehicle highlighted in red box</p>
                    </div>
                    
                    <div>
                        <div class="detail-item">
                            <div class="label">Violation ID</div>
                            <div class="val" style="color: var(--accent);">{v['violation_id']}</div>
                        </div>
                        
                        <div class="detail-item">
                            <div class="label">Violator Name</div>
                            <div class="val" style="color: #fff; font-weight: bold;">{violator_name}</div>
                        </div>
                        
                        <div class="detail-item">
                            <div class="label">Mobile Number</div>
                            <div class="val" style="font-family: monospace; color: #94a3b8;">{violator_mobile}</div>
                        </div>
                        
                        <div class="detail-item">
                            <div class="label">Vehicle Class</div>
                            <div class="val" style="text-transform: uppercase;">{v['vehicle_type']}</div>
                        </div>
                        
                        <div class="detail-item">
                            <div class="label">License Plate</div>
                            <div class="val" style="font-family: monospace; font-weight: bold; color: #38bdf8;">{v['license_plate']}</div>
                        </div>
                        
                        <div class="detail-item">
                            <div class="label">Location</div>
                            <div class="val">{v['location']}</div>
                        </div>
                        
                        <div class="detail-item">
                            <div class="label">Timestamp in Video</div>
                            <div class="val">{v['timestamp_in_video']}</div>
                        </div>
                        
                        <div class="detail-item">
                            <div class="label">Detection Confidence</div>
                            <div class="val">{v['confidence']}%</div>
                        </div>
                    </div>
                </div>
                
                <div class="challan-box" style="margin-top: 30px;">
                    <div class="label">Challan Number</div>
                    <div class="val" style="font-family: monospace; font-size: 18px; margin-bottom: 15px;">{v['challan_number']}</div>
                    
                    <div style="margin-bottom: 15px;">
                        <span id="challanBadge" class="badge {badge_class}">{v['challan_status']}</span>
                    </div>
                    
                    <div class="label">Fine Amount Due</div>
                    <div class="amount">₹{float(v['challan_amount']):,.2f}</div>
                    
                    <div style="margin-top: 20px;">
                        <button id="payBtn" class="btn" style="{pay_btn_style}" {disabled_attr}>{pay_btn_text}</button>
                    </div>
                </div>
            </div>

            <!-- Raise Query / Dispute Card -->
            <div class="card" style="margin-top: 30px;">
                <h2 class="violation-title" style="font-size: 20px; border-bottom: 1px solid var(--border-color); padding-bottom: 10px; margin-bottom: 15px;">Raise a Dispute / Query</h2>
                <p style="font-size: 13px; color: #94a3b8; margin-bottom: 15px; font-style: italic;">
                    If you believe this violation was detected incorrectly (e.g. wrong vehicle, false classification), you can file a query directly below and chat with our support bot.
                </p>
                
                <!-- Chat Message Box -->
                <div id="chatBox" style="background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border-color); border-radius: 12px; padding: 15px; max-height: 250px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; margin-bottom: 15px; min-height: 80px;">
                    <div style="text-align: center; color: #94a3b8; font-size: 12px; font-style: italic; padding: 10px; width: 100%;" id="emptyChatMsg">
                        No queries raised yet. Submit a message below to start a query.
                    </div>
                </div>
                
                <!-- Message Input Area -->
                <div style="display: flex; gap: 10px;">
                    <textarea id="queryInput" placeholder="Type your dispute message here (e.g., This is not my vehicle)..." style="flex-grow: 1; background: rgba(15, 23, 42, 0.8); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px; color: #fff; font-family: inherit; font-size: 14px; resize: none; height: 50px; min-height: 40px; box-sizing: border-box;"></textarea>
                    <button id="sendQueryBtn" class="btn" style="width: auto; padding: 0 20px; font-size: 14px; height: 50px; margin-top: 0; box-shadow: none;">Send</button>
                </div>
                
                <div style="margin-top: 15px; display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--border-color); padding-top: 10px;">
                    <span style="font-size: 12px; color: #94a3b8;">Dispute Status: <strong id="queryStatusLabel" style="color: #94a3b8; text-transform: uppercase;">None</strong></span>
                </div>
            </div>
        </div>

        <footer>
            <p>This is a secure, official system-generated challan portal.</p>
            <p>© 2026 National Informatics Centre (NIC) • Ministry of Road Transport & Highways.</p>
        </footer>

        <script>
            const payBtn = document.getElementById("payBtn");
            const challanBadge = document.getElementById("challanBadge");
            
            payBtn.addEventListener("click", async () => {{
                payBtn.disabled = true;
                payBtn.textContent = "Processing payment...";
                
                try {{
                    const res = await fetch("/violation/{v['violation_id']}/pay", {{
                        method: "POST"
                    }});
                    
                    if (res.ok) {{
                        challanBadge.textContent = "PAID";
                        challanBadge.className = "badge badge-paid";
                        payBtn.textContent = "Payment Successful";
                        payBtn.style.background = "#22c55e";
                        payBtn.style.boxShadow = "0 4px 15px rgba(34, 197, 94, 0.4)";
                    }} else {{
                        alert("Payment failed. Please try again.");
                        payBtn.disabled = false;
                        payBtn.textContent = "Pay Online";
                    }}
                }} catch (e) {{
                    console.error(e);
                    alert("Error connecting to server.");
                    payBtn.disabled = false;
                    payBtn.textContent = "Pay Online";
                }}
            }});

            // Dispute query bot implementation
            const chatBox = document.getElementById("chatBox");
            const queryInput = document.getElementById("queryInput");
            const sendQueryBtn = document.getElementById("sendQueryBtn");
            const queryStatusLabel = document.getElementById("queryStatusLabel");
            const emptyChatMsg = document.getElementById("emptyChatMsg");
            
            let chatHistory = {query_chat_json};
            let queryStatus = "{query_status}";
            
            function renderChat() {{
                if (chatHistory.length === 0) {{
                    emptyChatMsg.style.display = "block";
                    queryStatusLabel.textContent = "None";
                    queryStatusLabel.style.color = "#94a3b8";
                    return;
                }}
                
                emptyChatMsg.style.display = "none";
                chatBox.innerHTML = "";
                
                chatHistory.forEach(msg => {{
                    const bubble = document.createElement("div");
                    bubble.className = "message-bubble " + (msg.sender === "user" ? "bubble-user" : "bubble-authority");
                    
                    const text = document.createElement("div");
                    text.textContent = msg.message;
                    bubble.appendChild(text);
                    
                    const timeEl = document.createElement("span");
                    timeEl.className = "bubble-time";
                    timeEl.textContent = msg.timestamp;
                    bubble.appendChild(timeEl);
                    
                    chatBox.appendChild(bubble);
                }});
                
                chatBox.scrollTop = chatBox.scrollHeight;
                
                // Update status label
                queryStatusLabel.textContent = queryStatus.replace("_", " ");
                if (queryStatus === "UNDER_REVIEW") {{
                    queryStatusLabel.style.color = "#eab308";
                }} else if (queryStatus === "RESOLVED") {{
                    queryStatusLabel.style.color = "#22c55e";
                }} else {{
                    queryStatusLabel.style.color = "#94a3b8";
                }}
            }}
            
            renderChat();
            
            sendQueryBtn.addEventListener("click", async () => {{
                const msgText = queryInput.value.trim();
                if (!msgText) return;
                
                sendQueryBtn.disabled = true;
                queryInput.disabled = true;
                
                try {{
                    const res = await fetch("/violation/{v['violation_id']}/query", {{
                        method: "POST",
                        headers: {{ "Content-Type": "application/json" }},
                        body: JSON.stringify({{ message: msgText }})
                    }});
                    
                    if (res.ok) {{
                        const data = await res.json();
                        chatHistory = data.chat;
                        queryStatus = data.query_status;
                        queryInput.value = "";
                        renderChat();
                    }} else {{
                        alert("Failed to send query message. Please try again.");
                    }}
                }} catch (e) {{
                    console.error(e);
                    alert("Error connecting to server.");
                }} finally {{
                    sendQueryBtn.disabled = false;
                    queryInput.disabled = false;
                    queryInput.focus();
                }}
            }});
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/violation/{violation_id}/pay")
def pay_violation_challan(violation_id: str):
    """API endpoint to pay a challan, updating its status to PAID."""
    success = processor.db.update_challan_status(violation_id, "PAID")
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update challan payment in database.")
    
    # Also update in-memory violation list status to keep UI in sync
    for v in processor.violations:
        if v.get("violation_id") == violation_id:
            v["challan_status"] = "PAID"
            break
            
    return {"status": "success", "violation_id": violation_id, "challan_status": "PAID"}

class QueryModel(BaseModel):
    message: str

@app.post("/violation/{violation_id}/query")
def submit_violation_query(violation_id: str, model: QueryModel):
    """Adds a message to the query chat for a violation, updating its status to UNDER_REVIEW."""
    v = processor.db.get_violation_by_id(violation_id)
    if not v:
        raise HTTPException(status_code=404, detail="Violation record not found.")
        
    import json
    try:
        chat = json.loads(v.get("query_chat") or "[]")
    except Exception:
        chat = []
        
    # Append the user's message
    user_msg = {
        "sender": "user",
        "message": model.message,
        "timestamp": time.strftime("%H:%M")
    }
    chat.append(user_msg)
    
    # If it is the first query message, append an automated traffic authority reply
    if len([m for m in chat if m["sender"] == "user"]) == 1:
        authority_msg = {
            "sender": "authority",
            "message": f"Hello {v.get('violator_name', 'Citizen')}. We have received your query regarding Challan {v['challan_number']}. Our manual review team is analyzing the video frame of camera source. We will notify you once a decision is made. Status: Under Review.",
            "timestamp": time.strftime("%H:%M")
        }
        chat.append(authority_msg)
    else:
        # Subsequent messages can trigger a generic automated status update response
        authority_msg = {
            "sender": "authority",
            "message": "Thank you for the additional information. Your query remains under review by our department. We will update you as soon as possible.",
            "timestamp": time.strftime("%H:%M")
        }
        chat.append(authority_msg)
        
    chat_json = json.dumps(chat)
    success = processor.db.update_query_chat(violation_id, chat_json, "UNDER_REVIEW")
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update query chat in database.")
        
    # Also update in-memory violation list status to keep UI in sync
    for violation in processor.violations:
        if violation.get("violation_id") == violation_id:
            violation["query_status"] = "UNDER_REVIEW"
            violation["query_chat"] = chat_json
            break
            
    return {"status": "success", "query_status": "UNDER_REVIEW", "chat": chat}

@app.get("/api/violations")
def get_all_db_violations():
    """Endpoint to return all violations directly from the database, sorted by log date descending."""
    try:
        violations = processor.db.get_all_violations()
        # Ensure fields like confidence and challan_amount are floats
        formatted = []
        for idx, v in enumerate(violations):
            formatted.append({
                "id": len(violations) - idx,  # Maintain sequential UI numbering
                "violation_id": v["violation_id"],
                "video_filename": v["video_filename"],
                "location": v["location"],
                "timestamp": v["timestamp_in_video"],
                "violation_type": v["violation_type"],
                "vehicle_type": v["vehicle_type"],
                "license_plate": v["license_plate"],
                "confidence": float(v["confidence"]),
                "crop_url": v["crop_url"],
                "detail_url": v["detail_url"],
                "challan_number": v["challan_number"],
                "challan_amount": float(v["challan_amount"]),
                "challan_status": v["challan_status"],
                "violator_name": v.get("violator_name") or "Rajesh Kumar",
                "violator_mobile": v.get("violator_mobile") or "+91 98765 43210",
                "query_status": v.get("query_status") or "NONE",
                "query_chat": v.get("query_chat") or "[]"
            })
        return formatted
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch database logs: {str(e)}")

class AdminReplyModel(BaseModel):
    message: str
    status: str  # "UNDER_REVIEW" or "RESOLVED"

@app.post("/api/violation/{violation_id}/reply")
def reply_violation_query(violation_id: str, model: AdminReplyModel):
    """Allows admin/operator to reply to a dispute query, optionally resolving it."""
    v = processor.db.get_violation_by_id(violation_id)
    if not v:
        raise HTTPException(status_code=404, detail="Violation record not found.")
        
    import json
    try:
        chat = json.loads(v.get("query_chat") or "[]")
    except Exception:
        chat = []
        
    # Append admin reply
    admin_msg = {
        "sender": "authority",
        "message": model.message,
        "timestamp": time.strftime("%H:%M")
    }
    chat.append(admin_msg)
    
    chat_json = json.dumps(chat)
    success = processor.db.update_query_chat(violation_id, chat_json, model.status)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update dispute status in database.")
        
    # Also update in-memory violation list status to keep UI in sync
    for violation in processor.violations:
        if violation.get("violation_id") == violation_id:
            violation["query_status"] = model.status
            violation["query_chat"] = chat_json
            break
            
    return {"status": "success", "query_status": model.status, "chat": chat}


# Mount static directories (at the bottom to avoid overriding REST API routing precedence)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/videos_raw", StaticFiles(directory=RESOURCES_DIR), name="videos_raw")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

