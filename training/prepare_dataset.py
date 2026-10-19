#!/usr/bin/env python3
"""
Unified Dataset Preparation Pipeline for Multispectral RGBT Drone Imagery.

Performs:
  1. 4-Channel RGBA Image Fusion:
     Merges Visible (RGB) JPG and Thermal Long-Wave Infrared (LWIR) Grayscale JPG
     into a single 4-channel PNG (R, G, B, Thermal).
  2. VOC Annotation Conversion & Single-Class Target Filtering:
     Parses Pascal VOC XML bounding box annotations, normalizes coordinates to YOLO format,
     filters out ambiguous 'uncertain' annotations, and remaps all valid human classes
     ('person', 'crowd', 'rider') to a unified single class: 0 ('human').
  3. YOLO Dataset Configuration Export:
     Generates the corresponding dataset.yaml configuration.
"""

import os
import glob
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from PIL import Image
import yaml

# Source dataset class definition
ORIGINAL_CLASSES = {"person": 0, "crowd": 1, "rider": 2, "uncertain": 3}
TARGET_CLASS_NAME = "human"


def convert_bbox(size, box):
    """
    Convert VOC bounding box (xmin, xmax, ymin, ymax)
    to normalized YOLO format (x_center, y_center, width, height).
    """
    dw = 1.0 / size[0]
    dh = 1.0 / size[1]
    x = (box[0] + box[1]) / 2.0
    y = (box[2] + box[3]) / 2.0
    w = box[1] - box[0]
    h = box[3] - box[2]
    return (x * dw, y * dh, w * dw, h * dh)


def process_split(src_dir, dst_dir, split="train", drop_uncertain=True):
    """
    Processes one dataset split (train or val):
      - Pairs visible and thermal frames into 4-channel RGBA PNGs.
      - Converts annotations to 1-class YOLO labels.
    """
    print(f"\nProcessing '{split}' split...")
    xml_dir = os.path.join(src_dir, split, "annotation")
    vis_dir = os.path.join(src_dir, split, "visible")
    thm_dir = os.path.join(src_dir, split, "thermal")

    out_img_dir = os.path.join(dst_dir, "images", split)
    out_lbl_dir = os.path.join(dst_dir, "labels", split)
    os.makedirs(out_img_dir, exist_ok=True)
    os.makedirs(out_lbl_dir, exist_ok=True)

    xml_files = sorted(glob.glob(os.path.join(xml_dir, "*.xml")))
    if not xml_files:
        print(f"Warning: No XML annotations found in {xml_dir}")
        return 0, 0

    total_images = 0
    total_boxes = 0
    dropped_uncertain = 0

    for xml_file in xml_files:
        basename = os.path.basename(xml_file).replace(".xml", "")
        vis_file = os.path.join(vis_dir, basename + ".jpg")
        thm_file = os.path.join(thm_dir, basename + ".jpg")

        if not (os.path.exists(vis_file) and os.path.exists(thm_file)):
            continue

        # Parse VOC XML
        tree = ET.parse(xml_file)
        root = tree.getroot()
        size = root.find("size")
        w, h = int(size.find("width").text), int(size.find("height").text)

        yolo_labels = []
        for obj in root.iter("object"):
            cls_name = obj.find("name").text
            if cls_name not in ORIGINAL_CLASSES:
                continue

            # Filter out uncertain labels if requested
            if drop_uncertain and cls_name == "uncertain":
                dropped_uncertain += 1
                continue

            xmlbox = obj.find("bndbox")
            b = (float(xmlbox.find("xmin").text), float(xmlbox.find("xmax").text),
                 float(xmlbox.find("ymin").text), float(xmlbox.find("ymax").text))
            bb = convert_bbox((w, h), b)

            # Single-class remapping: All target objects mapped to 0 ('human')
            yolo_labels.append(f"0 {bb[0]:.6f} {bb[1]:.6f} {bb[2]:.6f} {bb[3]:.6f}")
            total_boxes += 1

        # Save YOLO annotation file
        lbl_out_path = os.path.join(out_lbl_dir, basename + ".txt")
        with open(lbl_out_path, "w") as f:
            f.write("\n".join(yolo_labels) + ("\n" if yolo_labels else ""))

        # Merge Visible (RGB) and Thermal (L) into 4-Channel RGBA PNG
        img_vis = Image.open(vis_file).convert("RGB")
        img_thm = Image.open(thm_file).convert("L")

        # Ensure spatial resolution matches
        if img_vis.size != img_thm.size:
            img_thm = img_thm.resize(img_vis.size, Image.BILINEAR)

        r, g, b = img_vis.split()
        img_4ch = Image.merge("RGBA", (r, g, b, img_thm))
        img_4ch.save(os.path.join(out_img_dir, basename + ".png"))

        total_images += 1

    print(f"[{split}] Converted {total_images} frames | {total_boxes} '{TARGET_CLASS_NAME}' boxes (dropped {dropped_uncertain} uncertain).")
    return total_images, total_boxes


def build_dataset_yaml(dst_dir, output_yaml_path=None):
    """Exports dataset YAML configuration for YOLO training"""
    yaml_path = output_yaml_path or os.path.join(dst_dir, "dataset_1cls_4ch.yaml")
    config = {
        "path": os.path.abspath(dst_dir),
        "train": "images/train",
        "val": "images/val",
        "channels": 4,
        "names": {
            0: TARGET_CLASS_NAME
        }
    }
    with open(yaml_path, "w") as f:
        yaml.safe_dump(config, f, sort_keys=False)
    print(f"Dataset YAML written to: {yaml_path}")
    return yaml_path


def main():
    parser = argparse.ArgumentParser(description="Prepare 4-Channel Single-Class YOLO Dataset from Raw RGBT Drone Data")
    parser.add_argument("--src", type=str, default="/home/devesh/Downloads/RGBTDronePerson",
                        help="Path to raw RGBTDronePerson dataset containing train/val splits")
    parser.add_argument("--dst", type=str, default="/home/devesh/Downloads/YOLO_RGBT_4CH",
                        help="Target output directory for 4-channel PNGs and YOLO txt labels")
    parser.add_argument("--splits", nargs="+", default=["train", "val"],
                        help="Splits to process (default: train val)")
    parser.add_argument("--no-drop-uncertain", action="store_true",
                        help="Retain 'uncertain' bounding boxes as human")
    parser.add_argument("--yaml-out", type=str, default=None,
                        help="Custom path to save generated dataset.yaml")
    args = parser.parse_args()

    if not os.path.exists(args.src):
        print(f"Error: Source dataset directory not found at: {args.src}")
        return

    print("=" * 65)
    print("PREPARING 4-CHANNEL MULTISPECTRAL DATASET")
    print(f"Source: {args.src}")
    print(f"Destination: {args.dst}")
    print(f"Target Class: 0 ('{TARGET_CLASS_NAME}')")
    print("=" * 65)

    for split in args.splits:
        process_split(args.src, args.dst, split=split, drop_uncertain=not args.no_drop_uncertain)

    build_dataset_yaml(args.dst, args.yaml_out)
    print("\nDataset preparation complete.")


if __name__ == "__main__":
    main()
