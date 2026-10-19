#!/usr/bin/env python3
"""
4-Channel Early-Fusion YOLOv8-P2 Training Script for Multispectral Drone SAR Vision.
Supports:
  - 4-channel input (Visible RGB + Thermal LWIR).
  - High-resolution P2 architecture (4 detection heads: stride 4, 8, 16, 32).
  - Pretrained weight initialization: initializes the 4th channel using mean pretrained conv weights.
  - Multi-GPU (DDP), single-GPU, and CPU execution.
"""

import os
import sys
import argparse
import cv2
import torch
import numpy as np
from ultralytics import YOLO
import ultralytics.data.base as base

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_YAML = os.path.join(SCRIPT_DIR, "dataset_1cls_4ch.yaml")
DEFAULT_MODEL_YAML = os.path.join(SCRIPT_DIR, "yolov8n-p2-1cls-4ch.yaml")


def setup_ultralytics_imread(mode="4ch"):
    """
    Monkey-patches Ultralytics base.imread to preserve the 4th (thermal) channel.
    Channel ordering permuted to [Thermal, Blue, Green, Red] for the P2 model backbone.
    """
    def imread_custom(path, flags=cv2.IMREAD_COLOR):
        img = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_UNCHANGED)
        if mode == "thermal":
            # 3-channel thermal only
            return np.ascontiguousarray(img[:, :, [3, 3, 3]])
        # 4-channel early-fusion: [Thermal, Blue, Green, Red]
        return np.ascontiguousarray(img[:, :, [3, 0, 1, 2]])

    base.imread = imread_custom


def train_model(args):
    setup_ultralytics_imread(mode=args.mode)

    print("=" * 65)
    print(f"STARTING MULTISPECTRAL YOLOv8 TRAINING: [{args.name}]")
    print(f"Architecture YAML: {args.model}")
    print(f"Dataset YAML:      {args.data}")
    print(f"Channels:          {4 if args.mode == '4ch' else 3}")
    print(f"Image Resolution:  {args.imgsz}")
    print(f"Epochs:            {args.epochs}")
    print(f"Batch Size:        {args.batch}")
    print(f"Device:            {args.device}")
    print("=" * 65)

    if not os.path.exists(args.model):
        raise FileNotFoundError(f"Model architecture YAML not found at: {args.model}")
    if not os.path.exists(args.data):
        raise FileNotFoundError(f"Dataset YAML not found at: {args.data}")

    # Build model from P2 architecture specification and load COCO pretrained weights
    model = YOLO(args.model).load(args.pretrained)

    # Initialize 4th input channel (thermal) by averaging RGB pretrained weights
    if args.mode == "4ch":
        w3 = YOLO(args.pretrained).model.model[0].conv.weight.data
        with torch.no_grad():
            c = model.model.model[0].conv.weight
            c[:, :3] = w3
            c[:, 3:] = w3.mean(1, keepdim=True)
        print("Initialized 4th channel weights using pretrained RGB mean.")

    # Execute training loop
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        patience=args.patience,
        close_mosaic=5,
        name=args.name,
        exist_ok=True,
        hsv_h=0,
        hsv_s=0,
        hsv_v=0,
        scale=0.3,
        mixup=0.0,
        flipud=0.5,
        fliplr=0.5,
    )

    print(f"\nTraining complete. Run outputs saved to: runs/detect/{args.name}")


def main():
    parser = argparse.ArgumentParser(description="Train 4-Channel Early-Fusion YOLOv8-P2 Model")
    parser.add_argument("--data", type=str, default=DEFAULT_DATA_YAML,
                        help="Path to dataset configuration YAML")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL_YAML,
                        help="Path to YOLOv8-P2 architecture YAML")
    parser.add_argument("--pretrained", type=str, default="yolov8n.pt",
                        help="Base pretrained weights to initialize from (default: yolov8n.pt)")
    parser.add_argument("--epochs", type=int, default=40,
                        help="Total training epochs (default: 40)")
    parser.add_argument("--batch", type=int, default=32,
                        help="Batch size (default: 32)")
    parser.add_argument("--imgsz", type=int, default=1024,
                        help="Image resolution (default: 1024)")
    parser.add_argument("--device", type=str, default=("0" if torch.cuda.is_available() else "cpu"),
                        help="Computation device (e.g. '0', '0,1', or 'cpu')")
    parser.add_argument("--workers", type=int, default=2,
                        help="Dataloader workers (default: 2)")
    parser.add_argument("--patience", type=int, default=0,
                        help="Early stopping patience (default: 0 / disabled)")
    parser.add_argument("--mode", type=str, choices=["4ch", "thermal"], default="4ch",
                        help="Vision mode: '4ch' (RGB+Thermal) or 'thermal'")
    parser.add_argument("--name", type=str, default=None,
                        help="Custom experiment name (default: human_{mode}_{epochs}ep)")
    args = parser.parse_args()

    if args.name is None:
        args.name = f"human_{args.mode}_{args.epochs}ep"

    train_model(args)


if __name__ == "__main__":
    main()
