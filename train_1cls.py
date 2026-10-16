#!/usr/bin/env python3
"""
4-Channel Early-Fusion YOLOv8-P2 Training Script for Multispectral Drone Vision.
Derived from Kaggle training pipeline (notebook3424d3e7da.ipynb).
"""

import os
import cv2
import torch
import numpy as np
from ultralytics import YOLO
import ultralytics.data.base as base

MODE = os.environ.get('MODE', '4ch')        # '4ch' or 'thermal'
IMGSZ = int(os.environ.get('IMGSZ', 1024))
EPOCHS = int(os.environ.get('EPOCHS', 40))
BATCH = int(os.environ.get('BATCH', 32))
NAME = f'human_{MODE}_{EPOCHS}ep'
CH = 3 if MODE == 'thermal' else 4

data_yaml = os.path.abspath('dataset_1cls_4ch.yaml')
model_yaml = os.path.abspath('yolov8n-p2-1cls-4ch.yaml')

def imread_custom(p, flags=cv2.IMREAD_COLOR):
    img = cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_UNCHANGED)
    if MODE == 'thermal':
        return np.ascontiguousarray(img[:, :, [3, 3, 3]])
    # Permute BGRA from OpenCV to [Thermal, Blue, Green, Red]
    return np.ascontiguousarray(img[:, :, [3, 0, 1, 2]])

base.imread = imread_custom

print(f"=== Starting Training [{NAME}] ===")
print(f"Model YAML: {model_yaml}")
print(f"Data YAML:  {data_yaml}")
print(f"Channels:   {CH}")
print(f"Image Size: {IMGSZ}")

model = YOLO(model_yaml).load('yolov8n.pt')

if MODE == '4ch':
    w3 = YOLO('yolov8n.pt').model.model[0].conv.weight.data
    with torch.no_grad():
        c = model.model.model[0].conv.weight
        c[:, :3] = w3
        c[:, 3:] = w3.mean(1, keepdim=True)
    print("Initialized 4th channel using mean of pretrained weights.")

device_spec = '0' if torch.cuda.is_available() else 'cpu'

model.train(
    data=data_yaml,
    epochs=EPOCHS,
    imgsz=IMGSZ,
    batch=BATCH,
    device=device_spec,
    workers=2,
    patience=0,
    close_mosaic=5,
    name=NAME,
    exist_ok=True,
    hsv_h=0, hsv_s=0, hsv_v=0,
    scale=0.3, mixup=0.0, flipud=0.5, fliplr=0.5,
)

if __name__ == '__main__':
    print("Training job complete.")
