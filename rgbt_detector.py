import os
import cv2
import numpy as np
import torch
import ultralytics.data.base as base
from ultralytics import YOLO

# Monkey-patch Ultralytics imread so dataloaders and predictors preserve the 4th (Thermal) channel
base.imread = lambda p, flags=cv2.IMREAD_COLOR: cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_UNCHANGED)


class RGBTDetector:
    """
    Multispectral 4-Channel Early-Fusion Detector for Autonomous Drone Vision.
    Supports both standard YOLOv8 4-channel and high-resolution P2-head 1-class ('human') models.
    """

    def __init__(self, model_path="best.pt", conf_thresh=0.20, iou_thresh=0.45, imgsz=1024, device=None):
        self.model_path = model_path
        self.conf_thresh = conf_thresh
        self.iou_thresh = iou_thresh
        self.imgsz = imgsz
        self.device = device or ("0" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.nc = 1
        self.names = {0: "human"}
        self.is_p2 = False

        self._load_model()

    def _load_model(self):
        if not os.path.exists(self.model_path):
            print(f"[RGBTDetector] Model weights not found at: {self.model_path}")
            return False

        try:
            print(f"[RGBTDetector] Loading weights from {self.model_path} on {self.device}...")
            self.model = YOLO(self.model_path)
            
            # Inspect loaded model architecture
            if hasattr(self.model, "names") and self.model.names:
                self.names = self.model.names
                self.nc = len(self.names)
            
            # Check if this is the P2 architecture (4 detection scales)
            try:
                detect_module = self.model.model.model[-1]
                nl = getattr(detect_module, "nl", 3)
                self.is_p2 = (nl == 4)
            except Exception:
                self.is_p2 = False

            print(f"[RGBTDetector] Loaded successfully!")
            print(f"               Architecture: {'YOLOv8-P2 (4 heads)' if self.is_p2 else 'YOLOv8 Standard (3 heads)'}")
            print(f"               Classes ({self.nc}): {list(self.names.values())}")
            return True
        except Exception as e:
            print(f"[RGBTDetector] Error loading model: {e}")
            self.model = None
            return False

    def is_ready(self):
        return self.model is not None

    def preprocess_4channel(self, img_input):
        """
        Accepts:
          - str / Path: file path to 4-channel PNG
          - np.ndarray (H, W, 4): BGRA image from cv2.imread(..., cv2.IMREAD_UNCHANGED)
          - tuple (vis_bgr, thm_gray): separate visible and thermal frames from dual drone cameras
        Returns:
          - img_prepared: 4-channel numpy array ready for model inference
          - img_bgra_orig: Original BGRA image for rendering
        """
        if isinstance(img_input, str):
            if not os.path.exists(img_input):
                raise FileNotFoundError(f"Image not found at {img_input}")
            img_bgra = cv2.imread(img_input, cv2.IMREAD_UNCHANGED)
            if img_bgra is None or img_bgra.shape[-1] != 4:
                raise ValueError(f"Failed to load valid 4-channel image from {img_input}")
        elif isinstance(img_input, (tuple, list)) and len(img_input) == 2:
            vis_bgr, thm_gray = img_input
            if len(thm_gray.shape) == 3:
                thm_gray = cv2.cvtColor(thm_gray, cv2.COLOR_BGR2GRAY)
            # Ensure spatial dimensions match
            if vis_bgr.shape[:2] != thm_gray.shape[:2]:
                thm_gray = cv2.resize(thm_gray, (vis_bgr.shape[1], vis_bgr.shape[0]))
            img_bgra = np.dstack((vis_bgr[:, :, 0], vis_bgr[:, :, 1], vis_bgr[:, :, 2], thm_gray))
        elif isinstance(img_input, np.ndarray):
            if img_input.shape[-1] != 4:
                raise ValueError(f"Expected 4-channel array, got shape {img_input.shape}")
            img_bgra = img_input
        else:
            raise TypeError("Unsupported image input format.")

        # If trained with the P2 1-class script, channel ordering was [Thermal, Blue, Green, Red]
        # which corresponds to indices [3, 0, 1, 2] of OpenCV BGRA.
        if self.nc == 1 or self.is_p2:
            img_prepared = np.ascontiguousarray(img_bgra[:, :, [3, 0, 1, 2]])
        else:
            # Fallback for earlier 4-class checkpoint
            img_prepared = np.ascontiguousarray(img_bgra)

        return img_prepared, img_bgra

    def detect(self, img_input, conf=None):
        """
        Runs 4-channel inference and returns structured detection objects:
        [{"box": [x1, y1, x2, y2], "conf": 0.88, "class_id": 0, "class_name": "human"}, ...]
        """
        if not self.is_ready():
            raise RuntimeError("Model is not loaded. Call _load_model() or verify best.pt exists.")

        conf = conf if conf is not None else self.conf_thresh
        img_prepared, img_bgra = self.preprocess_4channel(img_input)

        results = self.model.predict(
            source=img_prepared,
            conf=conf,
            iou=self.iou_thresh,
            imgsz=self.imgsz,
            verbose=False,
            device=self.device
        )

        detections = []
        if len(results) > 0 and results[0].boxes is not None:
            boxes = results[0].boxes
            for i in range(len(boxes)):
                xyxy = boxes.xyxy[i].cpu().numpy().tolist()
                score = float(boxes.conf[i].cpu().numpy())
                cls_id = int(boxes.cls[i].cpu().numpy())
                cls_name = self.names.get(cls_id, f"cls_{cls_id}")
                detections.append({
                    "box": [round(coord, 1) for coord in xyxy],
                    "conf": round(score, 3),
                    "class_id": cls_id,
                    "class_name": cls_name
                })

        return detections, img_bgra

    def render_annotated(self, img_bgra, detections, mode="rgb"):
        """
        Renders bounding boxes and labels onto the image.
        Modes:
          - 'rgb': Bounding boxes drawn on standard Visible RGB.
          - 'thermal': Bounding boxes drawn on Thermal IR colored with INFERNO colormap.
          - 'multispectral': 3-panel panoramic view (Visible | Thermal IR | Fused Detection).
        """
        h, w = img_bgra.shape[:2]
        vis_bgr = img_bgra[:, :, :3].copy()
        thm_gray = img_bgra[:, :, 3].copy()

        # Generate thermal color representation
        thm_colored = cv2.applyColorMap(thm_gray, cv2.COLORMAP_INFERNO)

        # Draw boxes on visible
        annotated_vis = vis_bgr.copy()
        for det in detections:
            x1, y1, x2, y2 = [int(v) for v in det["box"]]
            conf = det["conf"]
            label = f"{det['class_name']} {conf:.2f}"

            # Box
            cv2.rectangle(annotated_vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
            # Label banner
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(annotated_vis, (x1, max(0, y1 - 20)), (x1 + tw + 6, max(0, y1)), (0, 255, 0), -1)
            cv2.putText(annotated_vis, label, (x1 + 3, max(14, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)

        if mode == "rgb":
            return cv2.cvtColor(annotated_vis, cv2.COLOR_BGR2RGB)

        if mode == "thermal":
            annotated_thm = thm_colored.copy()
            for det in detections:
                x1, y1, x2, y2 = [int(v) for v in det["box"]]
                cv2.rectangle(annotated_thm, (x1, y1), (x2, y2), (0, 255, 255), 2)
            return cv2.cvtColor(annotated_thm, cv2.COLOR_BGR2RGB)

        if mode == "multispectral":
            # Draw on thermal as well
            annotated_thm = thm_colored.copy()
            for det in detections:
                x1, y1, x2, y2 = [int(v) for v in det["box"]]
                cv2.rectangle(annotated_thm, (x1, y1), (x2, y2), (255, 255, 255), 2)

            # Create side-by-side: Visible | Thermal | Fused
            alpha = 0.6
            fused = cv2.addWeighted(vis_bgr, 1 - alpha, thm_colored, alpha, 0)
            for det in detections:
                x1, y1, x2, y2 = [int(v) for v in det["box"]]
                label = f"{det['class_name']} {det['conf']:.2f}"
                cv2.rectangle(fused, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(fused, label, (x1, max(15, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

            # Add headers
            def add_header(img, text):
                res = img.copy()
                cv2.rectangle(res, (0, 0), (w, 30), (20, 20, 20), -1)
                cv2.putText(res, text, (15, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
                return res

            p1 = add_header(annotated_vis, "Visible Channel (RGB)")
            p2 = add_header(annotated_thm, "Thermal Infrared (LWIR)")
            p3 = add_header(fused, "4-Channel Early Fusion AI Output")

            combined = np.hstack((p1, p2, p3))
            return cv2.cvtColor(combined, cv2.COLOR_BGR2RGB)

        return cv2.cvtColor(annotated_vis, cv2.COLOR_BGR2RGB)
