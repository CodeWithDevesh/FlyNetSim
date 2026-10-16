import os
import glob
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

# Paths
DATASET_PATH = "/home/devesh/Downloads/RGBTDronePerson"
OUTPUT_PATH = "/home/devesh/Downloads/YOLO_RGBT"

# YOLO Class mapping
CLASSES = {"person": 0, "crowd": 1, "rider": 2, "uncertain": 3}

def convert_bbox(size, box):
    # size: (width, height), box: (xmin, xmax, ymin, ymax)
    dw = 1. / size[0]
    dh = 1. / size[1]
    x = (box[0] + box[1]) / 2.0
    y = (box[2] + box[3]) / 2.0
    w = box[1] - box[0]
    h = box[3] - box[2]
    return (x * dw, y * dh, w * dw, h * dh)

def convert_split(split="train"):
    print(f"Converting {split} set...")
    xml_dir = os.path.join(DATASET_PATH, split, "annotation")
    img_dir = os.path.join(DATASET_PATH, split, "visible") # Training on visible images
    
    out_img_dir = os.path.join(OUTPUT_PATH, "images", split)
    out_lbl_dir = os.path.join(OUTPUT_PATH, "labels", split)
    os.makedirs(out_img_dir, exist_ok=True)
    os.makedirs(out_lbl_dir, exist_ok=True)
    
    xml_files = glob.glob(os.path.join(xml_dir, "*.xml"))
    for xml_file in xml_files:
        basename = os.path.basename(xml_file).replace(".xml", "")
        img_file = os.path.join(img_dir, basename + ".jpg") # assuming .jpg
        if not os.path.exists(img_file):
            continue
            
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        size = root.find("size")
        w = int(size.find("width").text)
        h = int(size.find("height").text)
        
        yolo_labels = []
        for obj in root.iter("object"):
            cls_name = obj.find("name").text
            if cls_name not in CLASSES:
                continue
            cls_id = CLASSES[cls_name]
            xmlbox = obj.find("bndbox")
            b = (float(xmlbox.find("xmin").text), float(xmlbox.find("xmax").text),
                 float(xmlbox.find("ymin").text), float(xmlbox.find("ymax").text))
            bb = convert_bbox((w, h), b)
            yolo_labels.append(f"{cls_id} {bb[0]:.6f} {bb[1]:.6f} {bb[2]:.6f} {bb[3]:.6f}")
            
        # Copy image
        shutil.copy(img_file, os.path.join(out_img_dir, basename + ".jpg"))
        
        # Write labels
        with open(os.path.join(out_lbl_dir, basename + ".txt"), "w") as f:
            f.write("\n".join(yolo_labels))

if __name__ == "__main__":
    convert_split("train")
    convert_split("val")
    
    # Create dataset.yaml
    yaml_content = f"""path: /kaggle/input/yolo-rgbt-drone  # Adjust this path based on Kaggle dataset mounting
train: images/train
val: images/val

names:
  0: person
  1: crowd
  2: rider
  3: uncertain
"""
    with open(os.path.join(OUTPUT_PATH, "dataset.yaml"), "w") as f:
        f.write(yaml_content)
    
    print(f"Conversion complete! Dataset saved to {OUTPUT_PATH}")
