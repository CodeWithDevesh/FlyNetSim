import cv2, torch, numpy as np
import ultralytics.data.base as base
from ultralytics import YOLO
base.imread = lambda p, flags=cv2.IMREAD_COLOR: cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_UNCHANGED)

model = YOLO('best.pt')
model.train(data='/kaggle/working/dataset_patched.yaml', epochs=1, imgsz=1024, batch=1, device=0, hsv_h=0, hsv_s=0, hsv_v=0)
# Actually we just want to initialize the dataloader
