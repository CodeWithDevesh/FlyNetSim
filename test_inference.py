import cv2
from ultralytics import YOLO
import numpy as np

img = np.zeros((640, 640, 4), dtype=np.uint8)
model = YOLO('best.pt')
try:
    model.predict(img)
except Exception as e:
    print("FAILED:", e)
