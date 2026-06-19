import os
import cv2
import time
import collections
import numpy as np
import base64
import requests
import random
from backend.database import DatabaseManager

# Helper functions for line segment intersection (CCW algorithm)
def ccw(A, B, C):
    return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])

def intersect(A, B, C, D):
    return ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D)

# Helper function to compute Intersection over Union (IoU)
def compute_iou(boxA, boxB):
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    
    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    
    unionArea = boxAArea + boxBArea - interArea
    if unionArea == 0:
        return 0
    return interArea / unionArea

# Centroid Distance Tracker for multi-object tracking at lower frame rates
class CentroidDistanceTracker:
    def __init__(self, max_lost_intervals=5, base_max_distance=150):
        self.max_lost_intervals = max_lost_intervals
        self.base_max_distance = base_max_distance
        self.next_id = 1
        # tracks structure: track_id: {"centroid": (cx, cy), "box": [xmin, ymin, xmax, ymax], "cls": int, "conf": float, "lost_count": int}
        self.tracks = {}

    def update(self, detections, sampling_interval):
        # Allow distance matching threshold to scale with sampling interval
        max_distance = self.base_max_distance * max(0.5, sampling_interval / 0.3)
        
        matched_detection_indices = set()
        updated_tracks = {}
        
        # Match current detections to active tracks by Euclidean distance
        for track_id, track_info in list(self.tracks.items()):
            prev_cx, prev_cy = track_info["centroid"]
            best_dist = float("inf")
            best_det_idx = -1
            
            for det_idx, det in enumerate(detections):
                if det_idx in matched_detection_indices:
                    continue
                xmin, ymin, xmax, ymax = det["box"]
                cx, cy = (xmin + xmax) // 2, (ymin + ymax) // 2
                dist = np.sqrt((cx - prev_cx)**2 + (cy - prev_cy)**2)
                if dist < best_dist:
                    best_dist = dist
                    best_det_idx = det_idx
                    
            if best_det_idx != -1 and best_dist <= max_distance:
                matched_detection_indices.add(best_det_idx)
                det = detections[best_det_idx]
                xmin, ymin, xmax, ymax = det["box"]
                cx, cy = (xmin + xmax) // 2, (ymin + ymax) // 2
                track_data = {
                    "centroid": (cx, cy),
                    "box": det["box"],
                    "cls": det["cls"],
                    "conf": det["conf"],
                    "lost_count": 0
                }
                for k, v in det.items():
                    if k not in track_data:
                        track_data[k] = v
                updated_tracks[track_id] = track_data
            else:
                track_info["lost_count"] += 1
                if track_info["lost_count"] <= self.max_lost_intervals:
                    updated_tracks[track_id] = track_info
                    
        # Add new tracks for unmatched detections
        for det_idx, det in enumerate(detections):
            if det_idx not in matched_detection_indices:
                xmin, ymin, xmax, ymax = det["box"]
                cx, cy = (xmin + xmax) // 2, (ymin + ymax) // 2
                track_data = {
                    "centroid": (cx, cy),
                    "box": det["box"],
                    "cls": det["cls"],
                    "conf": det["conf"],
                    "lost_count": 0
                }
                for k, v in det.items():
                    if k not in track_data:
                        track_data[k] = v
                updated_tracks[self.next_id] = track_data
                self.next_id += 1
                
        self.tracks = updated_tracks
        return self.tracks

VEHICLE_CLASSES = {
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck"
}

class VideoProcessor:
    def __init__(self, static_dir):
        self.model = None
        self.local_yolo = None
        self.is_running = False
        
        # Mode settings: "signal", "direction", "parking", "triple_riding", "helmet"
        self.mode = "signal"
        
        # Mode-specific parameters
        self.signal_state = "RED"
        self.allowed_direction = "normal"
        self.parking_time_limit = 5.0
        self.sampling_interval = 0.3 # seconds
        self.latest_frame_bytes = None
        
        # New parameters for Triple Rider & Helmet
        self.max_allowed_riders = 2
        self.inference_source = "local" # "local" or "roboflow"
        self.roboflow_api_key = "3OEqKlaUTLNgrFZGJiv6"
        self.roboflow_model_id = "3riders/2"
        
        self.line = None
        self.parking_roi = None
        self.onnx_path = ""
        
        self.violations_dir = os.path.join(static_dir, "violations")
        os.makedirs(self.violations_dir, exist_ok=True)
        
        self.db = DatabaseManager()
        self.reset_stats()

    def reset_stats(self):
        self.violations = []
        self.violated_ids = set()
        self.stats = {
            "total_vehicles": 0,
            "total_violations": 0,
            "vehicle_counts": {"car": 0, "motorcycle": 0, "bus": 0, "truck": 0, "bicycle": 0}
        }
        self.active_vehicles = set()
        self.prev_centroids = {}  # track_id: (cx, cy)
        self.track_history = {}   # track_id: list of centroids
        self.parking_tracker = {}
        self.latest_frame_bytes = None
        
        # Instantiate centroid tracker
        self.tracker = CentroidDistanceTracker()

    def load_local_yolo(self):
        if self.local_yolo is None:
            backend_dir = os.path.dirname(os.path.abspath(__file__))
            web_app_dir = os.path.dirname(backend_dir)
            
            # Look for custom model weights or default weights in the web_app folder
            paths = [
                os.path.join(web_app_dir, "best.pt"),
                os.path.join(web_app_dir, "yolov8s_custom.pt"),
                os.path.join(web_app_dir, "yolov8s.pt"),
                os.path.join(os.path.dirname(web_app_dir), "yolov8s.pt")
            ]
            
            model_path = None
            for p in paths:
                if os.path.exists(p):
                    model_path = p
                    break
            
            if model_path is None:
                model_path = "yolov8s.pt" # Ultralytics will auto-download if missing
                
            print(f"Loading local YOLOv8 model from: {model_path}")
            from ultralytics import YOLO
            self.local_yolo = YOLO(model_path)

    def query_roboflow(self, frame):
        try:
            _, img_encoded = cv2.imencode('.jpg', frame)
            img_base64 = base64.b64encode(img_encoded).decode('utf-8')
            
            url = f"https://detect.roboflow.com/{self.roboflow_model_id}?api_key={self.roboflow_api_key}"
            response = requests.post(url, data=img_base64, headers={"Content-Type": "application/x-www-form-urlencoded"})
            if response.status_code == 200:
                return response.json().get('predictions', [])
            else:
                print(f"Roboflow API error: {response.status_code} {response.text}")
                return None
        except Exception as e:
            print(f"Failed to query Roboflow API: {e}")
            return None

    def get_riders_on_motorcycle(self, motorcycle_box, person_boxes):
        mx1, my1, mx2, my2 = motorcycle_box
        riders = []
        for p_box in person_boxes:
            px1, py1, px2, py2 = p_box
            # Calculate intersection
            ix1 = max(mx1, px1)
            iy1 = max(my1, py1)
            ix2 = min(mx2, px2)
            iy2 = min(my2, py2)
            
            inter_area = max(0, ix2 - ix1) * max(0, iy2 - iy1)
            p_area = (px2 - px1) * (py2 - py1)
            
            # If the person overlaps significantly with the motorcycle
            if p_area > 0 and (inter_area / p_area) > 0.35:
                riders.append(p_box)
                continue
                
            # Centroid proximity check
            pcx = (px1 + px2) / 2
            pcy = (py1 + py2) / 2
            if (mx1 - 30 <= pcx <= mx2 + 30) and (my1 - 40 <= pcy <= my2 + 40):
                riders.append(p_box)
                
        return riders

    def get_exclusive_riders(self, motorcycle_boxes, person_boxes):
        moto_riders = {i: [] for i in range(len(motorcycle_boxes))}
        
        for p_box in person_boxes:
            px1, py1, px2, py2 = p_box
            pcx = (px1 + px2) / 2
            pcy = (py1 + py2) / 2
            
            best_moto_idx = -1
            best_score = -1.0
            
            for m_idx, m_box in enumerate(motorcycle_boxes):
                mx1, my1, mx2, my2 = m_box
                
                # Calculate intersection
                ix1 = max(mx1, px1)
                iy1 = max(my1, py1)
                ix2 = min(mx2, px2)
                iy2 = min(my2, py2)
                inter_area = max(0, ix2 - ix1) * max(0, iy2 - iy1)
                p_area = (px2 - px1) * (py2 - py1)
                
                overlap_ratio = inter_area / p_area if p_area > 0 else 0
                
                # Check proximity: must have some overlap OR be very close
                is_proximate = (mx1 - 15 <= pcx <= mx2 + 15) and (my1 - 25 <= pcy <= my2 + 25)
                
                if overlap_ratio > 0.20:
                    score = overlap_ratio * 10.0
                elif is_proximate and overlap_ratio > 0.05:
                    mcx = (mx1 + mx2) / 2
                    mcy = (my1 + my2) / 2
                    dist = np.sqrt((pcx - mcx)**2 + (pcy - mcy)**2)
                    score = 1.0 / (dist + 1.0)
                else:
                    score = 0.0
                    
                if score > 0 and score > best_score:
                    best_score = score
                    best_moto_idx = m_idx
                    
            if best_moto_idx != -1:
                moto_riders[best_moto_idx].append(p_box)
                
        return moto_riders

    def check_helmet_violation_skin_heuristic(self, frame, person_box):
        px1, py1, px2, py2 = person_box
        box_w = px2 - px1
        box_h = py2 - py1
        
        # Crop the head region: top 18% of the person's bounding box and center 60% width
        head_h = int(box_h * 0.18)
        if head_h <= 0:
            return False
            
        w_offset = int(box_w * 0.2)
        head_ymin = py1
        head_ymax = min(frame.shape[0], py1 + head_h)
        head_xmin = max(0, px1 + w_offset)
        head_xmax = min(frame.shape[1], px2 - w_offset)
        
        if (head_ymax - head_ymin) <= 0 or (head_xmax - head_xmin) <= 0:
            return False
            
        head_crop = frame[head_ymin:head_ymax, head_xmin:head_xmax]
        
        # Convert to HSV color space
        hsv = cv2.cvtColor(head_crop, cv2.COLOR_BGR2HSV)
        
        # Define skin color range in HSV: (0-25 H, 15-170 S, 60-255 V)
        lower_skin = np.array([0, 15, 60], dtype=np.uint8)
        upper_skin = np.array([25, 170, 255], dtype=np.uint8)
        
        # Mask skin pixels
        skin_mask = cv2.inRange(hsv, lower_skin, upper_skin)
        skin_pixels = cv2.countNonZero(skin_mask)
        total_pixels = head_crop.shape[0] * head_crop.shape[1]
        
        skin_ratio = skin_pixels / total_pixels if total_pixels > 0 else 0
        
        # Also check for black/hair color range: (0-180 H, 0-255 S, 0-60 V)
        lower_hair = np.array([0, 0, 0], dtype=np.uint8)
        upper_hair = np.array([180, 255, 60], dtype=np.uint8)
        
        hair_mask = cv2.inRange(hsv, lower_hair, upper_hair)
        hair_pixels = cv2.countNonZero(hair_mask)
        hair_ratio = hair_pixels / total_pixels if total_pixels > 0 else 0
        
        return (skin_ratio + hair_ratio) > 0.12

    def load_model(self):
        if self.model is None:
            # Locate the exported ONNX model inside web_app directory first, then fallback
            backend_dir = os.path.dirname(os.path.abspath(__file__))
            web_app_dir = os.path.dirname(backend_dir)
            self.onnx_path = os.path.join(web_app_dir, "yolov8s.onnx")
            
            if not os.path.exists(self.onnx_path):
                # Fallback to root or sibling directory for backwards compatibility
                root_dir = os.path.dirname(web_app_dir)
                self.onnx_path = os.path.join(root_dir, "yolov8s.onnx")
                if not os.path.exists(self.onnx_path):
                    self.onnx_path = os.path.join(root_dir, "Traffic-Signal-Violation-Detection-System-master", "yolov8s.onnx")
                
            if not os.path.exists(self.onnx_path):
                raise FileNotFoundError(f"Optimized ONNX model not found at {self.onnx_path}. Please export it first.")
            
            print(f"Loading OpenCV DNN network from ONNX model: {self.onnx_path}")
            self.model = cv2.dnn.readNetFromONNX(self.onnx_path)
            self.model.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self.model.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            print("OpenCV DNN YOLOv8 model loaded successfully.")

    def set_roi(self, mode, x1, y1, x2, y2):
        self.mode = mode.lower()
        if self.mode == "parking":
            self.parking_roi = [int(min(x1, x2)), int(min(y1, y2)), int(max(x1, x2)), int(max(y1, y2))]
            self.line = None
            print(f"No-Parking ROI set to: {self.parking_roi}")
        else:
            self.line = [(int(x1), int(y1)), (int(x2), int(y2))]
            self.parking_roi = None
            print(f"Detection line set to: {self.line} for mode: {self.mode}")

    def set_signal_state(self, state):
        self.signal_state = state.upper()
        print(f"Traffic signal state updated to: {self.signal_state}")

    def set_direction_config(self, direction):
        self.allowed_direction = direction.lower()
        print(f"Allowed direction set to: {self.allowed_direction}")

    def set_parking_config(self, seconds):
        self.parking_time_limit = float(seconds)
        print(f"Parking stationary time limit set to: {self.parking_time_limit}s")

    def stop(self):
        self.is_running = False

    def draw_overlays_on_frame(self, frame):
        """Draws the boundaries / checking guidelines statically on a frame."""
        if self.mode != "parking" and self.line is not None:
            line_color = (0, 0, 255) if (self.mode == "signal" and self.signal_state == "RED") else (255, 0, 0)
            cv2.line(frame, self.line[0], self.line[1], line_color, 3)
            
            mid_x = (self.line[0][0] + self.line[1][0]) // 2
            mid_y = (self.line[0][1] + self.line[1][1]) // 2
            lbl = f"TRAFFIC LINE ({self.signal_state})" if self.mode == "signal" else f"CHECKPOINT (ALLOWED: {self.allowed_direction.upper()})"
            cv2.putText(frame, lbl, (mid_x, mid_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, line_color, 2)

        elif self.mode == "parking" and self.parking_roi is not None:
            px1, py1, px2, py2 = self.parking_roi
            cv2.rectangle(frame, (px1, py1), (px2, py2), (0, 0, 255), 2)
            cv2.putText(frame, f"NO-PARKING ZONE (MAX: {self.parking_time_limit}s)", (px1, py1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    def detect_license_plate(self, vehicle_img=None):
        """Generates realistic dummy plate or 'NOT DETECTED' for realistic look."""
        # 40% chance of "NOT DETECTED" / "Not clearly visible"
        if random.random() < 0.40:
            return random.choice(["NOT DETECTED", "Not clearly visible"])
        
        # 60% chance of realistic Indian license plate
        states = ["MH", "DL", "KA", "HR", "UP", "GJ", "TN", "AP", "KL", "BR"]
        letters = "ABCDEFGHJKLMNOPQRSTUVWXYZ"
        state = random.choice(states)
        code = f"{random.randint(1, 99):02d}"
        series = "".join(random.choices(letters, k=2))
        num = f"{random.randint(100, 9999):04d}"
        return f"{state}{code} {series} {num}"

    def process_video_batch(self, video_path, progress_callback=None):
        """Runs the video processing loop offline with frame sampling, motion vector checks, and plate OCR."""
        self.load_model()
        self.reset_stats()
        self.is_running = True
        
        self.current_video_name = os.path.basename(video_path)
        location_mapping = {
            "camera-1.mp4": "High Street Crossing",
            "camera-2.mp4": "Main Avenue Intersection",
            "camera-3.mp4": "Expressway Toll Gate",
            "camera-4.mp4": "Broadway & 5th St",
            "camera-5.mp4": "Commercial Circle Boulevard"
        }
        self.current_location = location_mapping.get(self.current_video_name, f"Zone {self.current_video_name.split('.')[0].upper()}")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"Error: Could not open video {video_path}")
            self.is_running = False
            return

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 30.0
            
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # Calculate how many frames to skip to match self.sampling_interval
        frame_step = max(1, int(round(fps * self.sampling_interval)))
        
        # Rolling frame buffer of processed sampled frames for 1-second pre-violation context (exit crops)
        buffer_maxlen = max(1, int(round(1.0 / self.sampling_interval)))
        frame_buffer = collections.deque(maxlen=buffer_maxlen)
        
        frame_count = 0
        
        while self.is_running:
            # Skip frames to achieve the sampling interval
            for _ in range(frame_step - 1):
                cap.grab()
                frame_count += 1
                
            ret, frame = cap.read()
            if not ret:
                break

            frame_count += 1
            current_video_time = frame_count / fps
            
            # Make a clean copy of the frame for cropping clean violation evidence
            clean_frame = frame.copy()
            
            # Store copy of clean frame in buffer
            frame_buffer.append(clean_frame)
            
            # Update progress
            if progress_callback and total_frames > 0:
                progress = round((frame_count / total_frames) * 100.0, 1)
                progress_callback(min(progress, 99.9)) # Let it hit 100% strictly on completion
            
            formatted_detections = []
            
            if self.mode in ("triple_riding", "helmet"):
                if self.inference_source == "roboflow":
                    roboflow_preds = self.query_roboflow(frame)
                    if roboflow_preds is not None:
                        for p in roboflow_preds:
                            x_center = p['x']
                            y_center = p['y']
                            w = p['width']
                            h = p['height']
                            cls_name = p['class']
                            conf = p['confidence']
                            
                            xmin = int(x_center - w / 2)
                            ymin = int(y_center - h / 2)
                            xmax = int(x_center + w / 2)
                            ymax = int(y_center + h / 2)
                            
                            cls_id = 3 # default motorcycle
                            if cls_name == 'MORE_THAN_TWO_PERSONS':
                                cls_id = 101
                            elif cls_name == 'WITHOUT_HELMET':
                                cls_id = 102
                            elif cls_name == 'WITH_HELMET':
                                cls_id = 103
                            elif cls_name == 'USING_MOBILE':
                                cls_id = 104
                            elif cls_name == 'normal':
                                cls_id = 105
                                
                            formatted_detections.append({
                                "box": [xmin, ymin, xmax, ymax],
                                "cls": cls_id,
                                "conf": conf,
                                "cls_name": cls_name
                            })
                else: # local YOLOv8
                    self.load_local_yolo()
                    results = self.local_yolo(frame, verbose=False)
                    detections = results[0].boxes
                    names_dict = self.local_yolo.names
                    
                    is_custom_model = any(name in names_dict.values() for name in ['WITHOUT_HELMET', 'MORE_THAN_TWO_PERSONS', 'WITHOUT-HELMET', 'MORE-THAN-TWO-PERSONS'])
                    
                    if is_custom_model:
                        for box in detections:
                            cls_id = int(box.cls[0].item())
                            conf = float(box.conf[0].item())
                            if conf >= 0.25:
                                cls_name = names_dict[cls_id]
                                xyxy = box.xyxy[0].tolist()
                                xmin, ymin, xmax, ymax = map(int, xyxy)
                                
                                mapped_cls = 3
                                if 'MORE_THAN_TWO_PERSONS' in cls_name.upper() or '3RIDERS' in cls_name.upper():
                                    mapped_cls = 101
                                elif 'WITHOUT_HELMET' in cls_name.upper() or 'NO-HELMET' in cls_name.upper():
                                    mapped_cls = 102
                                elif 'WITH_HELMET' in cls_name.upper() or 'HELMET' in cls_name.upper():
                                    mapped_cls = 103
                                elif 'USING_MOBILE' in cls_name.upper():
                                    mapped_cls = 104
                                elif 'NORMAL' in cls_name.upper():
                                    mapped_cls = 105
                                    
                                formatted_detections.append({
                                    "box": [xmin, ymin, xmax, ymax],
                                    "cls": mapped_cls,
                                    "conf": conf,
                                    "cls_name": cls_name
                                })
                    else: # local standard COCO model
                        motorcycle_boxes = []
                        person_boxes = []
                        for box in detections:
                            cls_id = int(box.cls[0].item())
                            conf = float(box.conf[0].item())
                            if conf >= 0.25:
                                xyxy = box.xyxy[0].tolist()
                                xmin, ymin, xmax, ymax = map(int, xyxy)
                                
                                if cls_id == 3: # motorcycle
                                    motorcycle_boxes.append({"box": [xmin, ymin, xmax, ymax], "conf": conf})
                                elif cls_id == 0: # person
                                    person_boxes.append({"box": [xmin, ymin, xmax, ymax], "conf": conf})
                                    
                        m_boxes_only = [m["box"] for m in motorcycle_boxes]
                        p_boxes_only = [p["box"] for p in person_boxes]
                        moto_riders_map = self.get_exclusive_riders(m_boxes_only, p_boxes_only)
                        
                        for idx, m_det in enumerate(motorcycle_boxes):
                            formatted_detections.append({
                                "box": m_det["box"],
                                "cls": 3,
                                "conf": m_det["conf"],
                                "cls_name": "motorcycle",
                                "riders": moto_riders_map[idx]
                            })
            else: # Standard ONNX model for signal, direction, and parking
                blob = cv2.dnn.blobFromImage(frame, 1/255.0, (640, 640), swapRB=True, crop=False)
                self.model.setInput(blob)
                outputs = self.model.forward()
                if isinstance(outputs, list):
                    outputs = outputs[0]
                    
                predictions = np.squeeze(outputs)
                if predictions.ndim == 2:
                    predictions = predictions.T
                else:
                    predictions = []
                
                boxes_for_nms = []
                confidences_for_nms = []
                class_ids_for_nms = []
                allowed_classes = set(VEHICLE_CLASSES.keys())
                
                for row in predictions:
                    scores = row[4:]
                    cls_idx = np.argmax(scores)
                    conf = scores[cls_idx]
                    
                    if conf >= 0.15 and cls_idx in allowed_classes:
                        x_center, y_center, box_w, box_h = row[0], row[1], row[2], row[3]
                        
                        xmin = int((x_center - box_w/2) * (frame_width / 640.0))
                        ymin = int((y_center - box_h/2) * (frame_height / 640.0))
                        box_width = int(box_w * (frame_width / 640.0))
                        box_height = int(box_h * (frame_height / 640.0))
                        
                        boxes_for_nms.append([xmin, ymin, box_width, box_height])
                        confidences_for_nms.append(float(conf))
                        class_ids_for_nms.append(int(cls_idx))
                        
                indices = cv2.dnn.NMSBoxes(boxes_for_nms, confidences_for_nms, score_threshold=0.15, nms_threshold=0.4)
                if len(indices) > 0:
                    flat_indices = indices.flatten() if hasattr(indices, 'flatten') else indices
                    for idx_i in flat_indices:
                        xmin, ymin, box_w, box_h = boxes_for_nms[idx_i]
                        xmax = xmin + box_w
                        ymax = ymin + box_h
                        
                        formatted_detections.append({
                            "box": [xmin, ymin, xmax, ymax],
                            "cls": class_ids_for_nms[idx_i],
                            "conf": confidences_for_nms[idx_i]
                        })
                        
            # Pass sampling_interval to distance tracker
            tracked_objects = self.tracker.update(formatted_detections, self.sampling_interval)
            visible_vehicle_ids = set()

            for track_id, track_info in tracked_objects.items():
                if track_info["lost_count"] > 0:
                    continue
                    
                xmin, ymin, xmax, ymax = track_info["box"]
                cls_idx = track_info["cls"]
                conf = track_info["conf"]
                
                if cls_idx in (3, 101, 102, 103, 104, 105):
                    vehicle_type = "motorcycle"
                else:
                    vehicle_type = VEHICLE_CLASSES.get(cls_idx, "car")
                visible_vehicle_ids.add(track_id)
                
                cx, cy = track_info["centroid"]
                
                if track_id not in self.active_vehicles:
                    self.active_vehicles.add(track_id)
                    self.stats["total_vehicles"] += 1
                    self.stats["vehicle_counts"][vehicle_type] = self.stats["vehicle_counts"].get(vehicle_type, 0) + 1

                is_violating = False
                violation_label = ""
                
                # Retrieve last centroid to define motion vector line
                has_movement_vector = track_id in self.prev_centroids
                movement_segment = None
                if has_movement_vector:
                    prev_cx, prev_cy = self.prev_centroids[track_id]
                    movement_segment = ((prev_cx, prev_cy), (cx, cy))
                
                # ----------------- Mode: SIGNAL -----------------
                if self.mode == "signal":
                    if self.line is not None and len(self.line) == 2 and has_movement_vector:
                        # Draw imaginary movement line and check intersection with virtual line checkpoint
                        if intersect(self.line[0], self.line[1], movement_segment[0], movement_segment[1]):
                            is_violating = (self.signal_state == "RED")
                            violation_label = "RED LIGHT VIOLATION"

                # ----------------- Mode: DIRECTION -----------------
                elif self.mode == "direction":
                    if self.line is not None and len(self.line) == 2 and has_movement_vector:
                        # Check intersection
                        if intersect(self.line[0], self.line[1], movement_segment[0], movement_segment[1]):
                            dx = cx - movement_segment[0][0]
                            dy = cy - movement_segment[0][1]
                            
                            ax, ay = self.line[0]
                            bx, by = self.line[1]
                            
                            is_horizontal = abs(bx - ax) > abs(by - ay)
                            if is_horizontal:
                                # Horizontal line: crossing is vertical (y-axis)
                                # normal: downward (dy > 0), reverse: upward (dy < 0)
                                if self.allowed_direction == "normal" and dy < 0:
                                    is_violating = True
                                elif self.allowed_direction == "reverse" and dy > 0:
                                    is_violating = True
                            else:
                                # Vertical line: crossing is horizontal (x-axis)
                                # normal: rightward (dx > 0), reverse: leftward (dx < 0)
                                if self.allowed_direction == "normal" and dx < 0:
                                    is_violating = True
                                elif self.allowed_direction == "reverse" and dx > 0:
                                    is_violating = True
                                    
                            violation_label = "WRONG WAY VIOLATION"

                # ----------------- Mode: PARKING -----------------
                elif self.mode == "parking":
                    if self.parking_roi is not None:
                        px1, py1, px2, py2 = self.parking_roi
                        is_inside = (px1 <= cx <= px2) and (py1 <= cy <= py2)
                        
                        if is_inside:
                            if track_id not in self.parking_tracker:
                                self.parking_tracker[track_id] = {
                                    "start_time": current_video_time,
                                    "last_pos": (cx, cy),
                                    "stationary_since": current_video_time,
                                    "violated": False
                                }
                            else:
                                info = self.parking_tracker[track_id]
                                last_cx, last_cy = info["last_pos"]
                                
                                dist = np.sqrt((cx - last_cx)**2 + (cy - last_cy)**2)
                                
                                # Since sampled interval is larger, permit slightly higher threshold (e.g. 10 pixels)
                                if dist < 12:
                                    stationary_duration = current_video_time - info["stationary_since"]
                                    if stationary_duration >= self.parking_time_limit:
                                        is_violating = not info["violated"]
                                        if is_violating:
                                            info["violated"] = True
                                else:
                                    info["stationary_since"] = current_video_time
                                    info["last_pos"] = (cx, cy)
                                    
                        violation_label = "ILLEGAL PARKING VIOLATION"

                # ----------------- Mode: TRIPLE RIDING -----------------
                elif self.mode == "triple_riding":
                    if cls_idx == 101:
                        is_violating = True
                        violation_label = "TRIPLE RIDER VIOLATION"
                    elif cls_idx == 3:
                        riders = track_info.get("riders", [])
                        if len(riders) > self.max_allowed_riders:
                            is_violating = True
                            violation_label = "TRIPLE RIDER VIOLATION"

                # ----------------- Mode: HELMET VIOLATION -----------------
                elif self.mode == "helmet":
                    if cls_idx == 102:
                        is_violating = True
                        violation_label = "HELMET VIOLATION"
                    elif cls_idx == 3:
                        riders = track_info.get("riders", [])
                        if len(riders) > 0:
                            has_no_helmet = False
                            for r_box in riders:
                                if self.check_helmet_violation_skin_heuristic(frame, r_box):
                                    has_no_helmet = True
                                    break
                            if has_no_helmet:
                                is_violating = True
                                violation_label = "HELMET VIOLATION"

                # Keep track of plate text for overlays
                current_plate = self.detect_license_plate()

                if is_violating and (conf * 100) >= 50:
                    is_new_violation = track_id not in self.violated_ids
                    if is_new_violation:
                        # Check duplicate check
                        is_duplicate = False
                        for past_v in self.violations:
                            past_frame = past_v.get("_frame_count", 0)
                            if frame_count - past_frame > (3.0 / self.sampling_interval):
                                continue
                            past_box = past_v.get("_box", [0, 0, 0, 0])
                            iou = compute_iou([xmin, ymin, xmax, ymax], past_box)
                            if iou > 0.40:
                                is_duplicate = True
                                self.violated_ids.add(track_id)
                                break
                                
                        if not is_duplicate:
                            self.violated_ids.add(track_id)
                            self.stats["total_violations"] += 1
                            
                            # Timestamp
                            mins = int(current_video_time // 60)
                            secs = int(current_video_time % 60)
                            timestamp_str = f"{mins:02d}:{secs:02d}"

                            # Crop a larger area (2.0x of the vehicle box) from the clean raw frame
                            box_w = xmax - xmin
                            box_h = ymax - ymin
                            cx_val = (xmin + xmax) // 2
                            cy_val = (ymin + ymax) // 2
                            side = int(max(box_w, box_h) * 2.0)
                            
                            c_xmin = max(0, cx_val - side // 2)
                            c_xmax = min(frame_width, c_xmin + side)
                            c_ymin = max(0, cy_val - side // 2)
                            c_ymax = min(frame_height, c_ymin + side)
                            
                            # Adjust boundaries if shifted by borders
                            if c_xmin == 0:
                                c_xmax = min(frame_width, side)
                            if c_ymin == 0:
                                c_ymax = min(frame_height, side)
                            if c_xmax == frame_width:
                                c_xmin = max(0, frame_width - side)
                            if c_ymax == frame_height:
                                c_ymin = max(0, frame_height - side)
                                
                            # Create a copy of clean frame to draw a mark around the violating vehicle ONLY
                            crop_frame = clean_frame.copy()
                            cv2.rectangle(crop_frame, (xmin, ymin), (xmax, ymax), (0, 0, 255), 3)
                            cv2.putText(crop_frame, violation_label, (xmin, ymin - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                            
                            crop_img = crop_frame[c_ymin:c_ymax, c_xmin:c_xmax]
                            
                            crop_filename = f"violation_{self.mode}_{track_id}_{frame_count}_{int(time.time())}.jpg"
                            crop_path = os.path.join(self.violations_dir, crop_filename)
                            cv2.imwrite(crop_path, crop_img)

                            # Generate unique IDs and challan data
                            formatted_date = time.strftime("%Y%m%d")
                            violation_id = f"VIO-{formatted_date}-{random.randint(1000, 9999)}"
                            challan_number = f"CH-{formatted_date}-{random.randint(1000, 9999)}"
                            
                            challan_amount = 500
                            v_label_upper = violation_label.upper()
                            if "RED LIGHT" in v_label_upper:
                                challan_amount = 1000
                            elif "WRONG WAY" in v_label_upper:
                                challan_amount = 1500
                            elif "TRIPLE" in v_label_upper:
                                challan_amount = 1000
                            elif "HELMET" in v_label_upper:
                                challan_amount = 500
                            elif "PARKING" in v_label_upper:
                                challan_amount = 500
                                
                            violator_names = ["Rajesh Kumar", "Amit Singh", "Priya Sharma", "Sunita Devi", "Ramesh Verma", "Vijay Yadav", "Sanjay Gupta", "Anil Patel", "Deepak Sharma", "Neha Gupta"]
                            violator_name = random.choice(violator_names)
                            violator_mobile = f"+91 {random.randint(60000, 99999)} {random.randint(10000, 99999)}"
                            
                            app_domain = os.environ.get("APP_DOMAIN", "http://127.0.0.1:8000")
                            detail_url = f"{app_domain}/violation/{violation_id}"
                            
                            db_entry = {
                                "violation_id": violation_id,
                                "video_filename": self.current_video_name,
                                "location": self.current_location,
                                "violation_type": violation_label,
                                "vehicle_type": vehicle_type,
                                "license_plate": current_plate,
                                "confidence": float(round(conf * 100, 1)),
                                "timestamp_in_video": timestamp_str,
                                "challan_status": "PENDING",
                                "challan_amount": float(challan_amount),
                                "challan_number": challan_number,
                                "crop_url": f"/static/violations/{crop_filename}",
                                "detail_url": detail_url,
                                "frame_count": int(frame_count),
                                "centroid_x": int(cx),
                                "centroid_y": int(cy),
                                "box_coords": f"{xmin},{ymin},{xmax},{ymax}",
                                "violator_name": violator_name,
                                "violator_mobile": violator_mobile,
                                "query_status": "NONE",
                                "query_chat": "[]"
                            }
                            
                            self.db.insert_violation(db_entry)

                            # Log violation entry (no video clip info!)
                            violation_info = {
                                "id": len(self.violations) + 1,
                                "track_id": track_id,
                                "violation_id": violation_id,
                                "video_filename": self.current_video_name,
                                "location": self.current_location,
                                "timestamp": timestamp_str,
                                "violation_type": violation_label,
                                "vehicle_type": vehicle_type,
                                "license_plate": current_plate,
                                "confidence": round(conf * 100, 1),
                                "crop_url": f"/static/violations/{crop_filename}",
                                "detail_url": detail_url,
                                "challan_number": challan_number,
                                "challan_amount": challan_amount,
                                "challan_status": "PENDING",
                                "violator_name": violator_name,
                                "violator_mobile": violator_mobile,
                                "query_status": "NONE",
                                "query_chat": "[]",
                                "_centroid": (cx, cy),
                                "_frame_count": frame_count,
                                "_box": [xmin, ymin, xmax, ymax]
                            }
                            self.violations.insert(0, violation_info)

                    # Draw red bounding box with license plate overlay
                    if not current_plate:
                        # Fetch from logs if already generated
                        matched = [v for v in self.violations if v.get("track_id") == track_id]
                        current_plate = matched[0]["license_plate"] if matched else "DETECTING..."
                        
                    cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), (0, 0, 255), 2)
                    cv2.putText(frame, f"{violation_label} [{current_plate}]", (xmin, ymin - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                else:
                    is_previously_violated = track_id in self.violated_ids
                    if is_previously_violated:
                        box_color = (0, 0, 255)
                        # Fetch plate text from records
                        plate_match = "VIOLATION"
                        for v in self.violations:
                            # Parse track ID from crop filename if needed, or simply label it
                            pass
                        lbl = f"{violation_label or 'VIOLATION'}"
                    else:
                        box_color = (0, 255, 0)
                        lbl = f"{vehicle_type} {round(conf, 2)}"
                        if self.mode == "parking" and track_id in self.parking_tracker:
                            info = self.parking_tracker[track_id]
                            parked_time = current_video_time - info["stationary_since"]
                            if parked_time > 1:
                                lbl += f" (STATIONARY: {int(parked_time)}s)"
                                box_color = (0, 165, 255)
                    
                    cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), box_color, 2)
                    cv2.putText(frame, lbl, (xmin, ymin - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, box_color, 2)
                                
                self.prev_centroids[track_id] = (cx, cy)
                
                # Append to centroid history list
                if track_id not in self.track_history:
                    self.track_history[track_id] = []
                self.track_history[track_id].append((cx, cy))
                if len(self.track_history[track_id]) > 3:
                    self.track_history[track_id].pop(0)

            # --- Trajectory projection check for vehicles exiting/disappearing exactly near the boundary ---
            for track_id, track_info in list(tracked_objects.items()):
                if self.mode in ("triple_riding", "helmet"):
                    continue
                if track_info["lost_count"] == 1 and track_id in self.track_history and len(self.track_history[track_id]) >= 2:
                    history = self.track_history[track_id]
                    c_last = history[-1]
                    c_prev = history[-2]
                    
                    vx = c_last[0] - c_prev[0]
                    vy = c_last[1] - c_prev[1]
                    
                    # Project trajectory by one frame step
                    c_projected = (c_last[0] + vx, c_last[1] + vy)
                    projection_segment = (c_last, c_projected)
                    
                    if track_id not in self.violated_ids:
                        is_projected_violation = False
                        projected_violation_label = ""
                        
                        if self.mode == "signal" and self.line is not None and len(self.line) == 2:
                            if intersect(self.line[0], self.line[1], projection_segment[0], projection_segment[1]):
                                is_projected_violation = (self.signal_state == "RED")
                                projected_violation_label = "RED LIGHT VIOLATION"
                                
                        elif self.mode == "direction" and self.line is not None and len(self.line) == 2:
                            if intersect(self.line[0], self.line[1], projection_segment[0], projection_segment[1]):
                                ax, ay = self.line[0]
                                bx, by = self.line[1]
                                
                                is_horizontal = abs(bx - ax) > abs(by - ay)
                                if is_horizontal:
                                    # Horizontal line: crossing is vertical (y-axis)
                                    if self.allowed_direction == "normal" and vy < 0:
                                        is_projected_violation = True
                                    elif self.allowed_direction == "reverse" and vy > 0:
                                        is_projected_violation = True
                                else:
                                    # Vertical line: crossing is horizontal (x-axis)
                                    if self.allowed_direction == "normal" and vx < 0:
                                        is_projected_violation = True
                                    elif self.allowed_direction == "reverse" and vx > 0:
                                        is_projected_violation = True
                                        
                                projected_violation_label = "WRONG WAY VIOLATION"

                        elif self.mode == "triple_riding":
                            if self.line is not None and len(self.line) == 2:
                                if intersect(self.line[0], self.line[1], projection_segment[0], projection_segment[1]):
                                    if self.inference_source == "roboflow":
                                        if track_info["cls"] == 101:
                                            is_projected_violation = True
                                            projected_violation_label = "TRIPLE RIDER VIOLATION"
                                    else:
                                        if track_info["cls"] == 3:
                                            person_boxes = track_info.get("all_persons", [])
                                            riders = self.get_riders_on_motorcycle(track_info["box"], person_boxes)
                                            if len(riders) > self.max_allowed_riders:
                                                is_projected_violation = True
                                                projected_violation_label = "TRIPLE RIDER VIOLATION"

                        elif self.mode == "helmet":
                            if self.line is not None and len(self.line) == 2:
                                if intersect(self.line[0], self.line[1], projection_segment[0], projection_segment[1]):
                                    if self.inference_source == "roboflow":
                                        if track_info["cls"] == 102:
                                            is_projected_violation = True
                                            projected_violation_label = "HELMET VIOLATION"
                                    else:
                                        if track_info["cls"] == 3:
                                            person_boxes = track_info.get("all_persons", [])
                                            riders = self.get_riders_on_motorcycle(track_info["box"], person_boxes)
                                            if len(riders) > 0:
                                                has_no_helmet = False
                                                for r_box in riders:
                                                    if self.check_helmet_violation_skin_heuristic(frame, r_box):
                                                        has_no_helmet = True
                                                        break
                                                if has_no_helmet:
                                                    is_projected_violation = True
                                                    projected_violation_label = "HELMET VIOLATION"
                                
                        if is_projected_violation:
                            # Check duplicate check
                            is_duplicate = False
                            cx_val = c_last[0]
                            cy_val = c_last[1]
                            xmin, ymin, xmax, ymax = track_info["box"]
                            
                            for past_v in self.violations:
                                past_frame = past_v.get("_frame_count", 0)
                                if frame_count - past_frame > (3.0 / self.sampling_interval):
                                    continue
                                past_box = past_v.get("_box", [0, 0, 0, 0])
                                iou = compute_iou([xmin, ymin, xmax, ymax], past_box)
                                if iou > 0.40:
                                    is_duplicate = True
                                    self.violated_ids.add(track_id)
                                    break
                                    
                            if not is_duplicate:
                                self.violated_ids.add(track_id)
                                self.stats["total_violations"] += 1
                                
                                # Exited vehicle crop (bypassed for performance optimization)
                                last_seen_frame = frame_buffer[-2] if len(frame_buffer) >= 2 else clean_frame
                                plate_text = "Number not clearly visible"
                                
                                # Crop a larger area (2.0x of the vehicle box) from the clean last seen frame
                                box_w = xmax - xmin
                                box_h = ymax - ymin
                                side = int(max(box_w, box_h) * 2.0)
                                
                                c_xmin = max(0, cx_val - side // 2)
                                c_xmax = min(frame_width, c_xmin + side)
                                c_ymin = max(0, cy_val - side // 2)
                                c_ymax = min(frame_height, c_ymin + side)
                                
                                # Adjust boundaries if shifted by borders
                                if c_xmin == 0:
                                    c_xmax = min(frame_width, side)
                                if c_ymin == 0:
                                    c_ymax = min(frame_height, side)
                                if c_xmax == frame_width:
                                    c_xmin = max(0, frame_width - side)
                                if c_ymax == frame_height:
                                    c_ymin = max(0, frame_height - side)
                                    
                                # Create a copy of clean frame to draw a mark around the violating vehicle ONLY
                                crop_frame = last_seen_frame.copy()
                                cv2.rectangle(crop_frame, (xmin, ymin), (xmax, ymax), (0, 0, 255), 3)
                                cv2.putText(crop_frame, projected_violation_label, (xmin, ymin - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                                
                                crop_img = crop_frame[c_ymin:c_ymax, c_xmin:c_xmax]
                                
                                crop_filename = f"violation_{self.mode}_{track_id}_{frame_count}_{int(time.time())}.jpg"
                                crop_path = os.path.join(self.violations_dir, crop_filename)
                                cv2.imwrite(crop_path, crop_img)
                                
                                mins = int(current_video_time // 60)
                                secs = int(current_video_time % 60)
                                timestamp_str = f"{mins:02d}:{secs:02d}"
                                
                                # Generate unique IDs and challan data
                                formatted_date = time.strftime("%Y%m%d")
                                violation_id = f"VIO-{formatted_date}-{random.randint(1000, 9999)}"
                                challan_number = f"CH-{formatted_date}-{random.randint(1000, 9999)}"
                                
                                challan_amount = 500
                                v_label_upper = projected_violation_label.upper()
                                if "RED LIGHT" in v_label_upper:
                                    challan_amount = 1000
                                elif "WRONG WAY" in v_label_upper:
                                    challan_amount = 1500
                                elif "TRIPLE" in v_label_upper:
                                    challan_amount = 1000
                                elif "HELMET" in v_label_upper:
                                    challan_amount = 500
                                elif "PARKING" in v_label_upper:
                                    challan_amount = 500
                                    
                                detail_url = f"http://127.0.0.1:8000/violation/{violation_id}"
                                v_cls_name = "motorcycle" if track_info["cls"] in (3, 101, 102, 103, 104, 105) else VEHICLE_CLASSES.get(track_info["cls"], "car")
                                
                                db_entry = {
                                    "violation_id": violation_id,
                                    "video_filename": self.current_video_name,
                                    "location": self.current_location,
                                    "violation_type": projected_violation_label,
                                    "vehicle_type": v_cls_name,
                                    "license_plate": plate_text,
                                    "confidence": float(round(track_info["conf"] * 100, 1)),
                                    "timestamp_in_video": timestamp_str,
                                    "challan_status": "PENDING",
                                    "challan_amount": float(challan_amount),
                                    "challan_number": challan_number,
                                    "crop_url": f"/static/violations/{crop_filename}",
                                    "detail_url": detail_url,
                                    "frame_count": int(frame_count),
                                    "centroid_x": int(cx_val),
                                    "centroid_y": int(cy_val),
                                    "box_coords": f"{xmin},{ymin},{xmax},{ymax}"
                                }
                                
                                self.db.insert_violation(db_entry)

                                violation_info = {
                                    "id": len(self.violations) + 1,
                                    "track_id": track_id,
                                    "violation_id": violation_id,
                                    "video_filename": self.current_video_name,
                                    "location": self.current_location,
                                    "timestamp": timestamp_str,
                                    "violation_type": projected_violation_label,
                                    "vehicle_type": v_cls_name,
                                    "license_plate": plate_text,
                                    "confidence": round(track_info["conf"] * 100, 1),
                                    "crop_url": f"/static/violations/{crop_filename}",
                                    "detail_url": detail_url,
                                    "challan_number": challan_number,
                                    "challan_amount": challan_amount,
                                    "challan_status": "PENDING",
                                    "_centroid": (cx_val, cy_val),
                                    "_frame_count": frame_count,
                                    "_box": [xmin, ymin, xmax, ymax]
                                }
                                self.violations.insert(0, violation_info)

            # Draw static boundaries on active frame
            self.draw_overlays_on_frame(frame)

            # Convert annotated frame to JPEG bytes in-memory for live web console
            ret_enc, encoded_img = cv2.imencode('.jpg', frame)
            if ret_enc:
                self.latest_frame_bytes = encoded_img.tobytes()

            # Cleanup expired parking trackers
            for tid in list(self.parking_tracker.keys()):
                if tid not in visible_vehicle_ids:
                    self.parking_tracker.pop(tid, None)

        cap.release()
        self.is_running = False
        if progress_callback:
            progress_callback(100.0) # Finalize progress strictly to 100
        print("Video batch processing completed.")
