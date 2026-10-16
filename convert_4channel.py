import os
import glob
from PIL import Image
import xml.etree.ElementTree as ET

DATASET_PATH = "/home/devesh/Downloads/RGBTDronePerson"
OUTPUT_PATH = "/home/devesh/Downloads/YOLO_RGBT_4CH"
CLASSES = {"person": 0, "crowd": 1, "rider": 2, "uncertain": 3}

def convert_bbox(size, box):
    dw = 1. / size[0]
    dh = 1. / size[1]
    x = (box[0] + box[1]) / 2.0
    y = (box[2] + box[3]) / 2.0
    w = box[1] - box[0]
    h = box[3] - box[2]
    return (x * dw, y * dh, w * dw, h * dh)

def process_split(split):
    print(f"Processing 4-Channel {split} set...")
    os.makedirs(os.path.join(OUTPUT_PATH, "images", split), exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_PATH, "labels", split), exist_ok=True)
    
    xml_files = glob.glob(os.path.join(DATASET_PATH, split, "annotation", "*.xml"))
    for xml_file in xml_files:
        basename = os.path.basename(xml_file).replace(".xml", "")
        vis_file = os.path.join(DATASET_PATH, split, "visible", basename + ".jpg")
        thm_file = os.path.join(DATASET_PATH, split, "thermal", basename + ".jpg")
        
        if not (os.path.exists(vis_file) and os.path.exists(thm_file)):
            continue
            
        # Parse XML labels
        tree = ET.parse(xml_file)
        root = tree.getroot()
        size = root.find("size")
        w, h = int(size.find("width").text), int(size.find("height").text)
        
        yolo_labels = []
        for obj in root.iter("object"):
            cls_name = obj.find("name").text
            if cls_name not in CLASSES: continue
            b = (float(obj.find("bndbox/xmin").text), float(obj.find("bndbox/xmax").text),
                 float(obj.find("bndbox/ymin").text), float(obj.find("bndbox/ymax").text))
            bb = convert_bbox((w, h), b)
            yolo_labels.append(f"{CLASSES[cls_name]} {bb[0]:.6f} {bb[1]:.6f} {bb[2]:.6f} {bb[3]:.6f}")
            
        with open(os.path.join(OUTPUT_PATH, "labels", split, basename + ".txt"), "w") as f:
            f.write("\n".join(yolo_labels))
            
        # Create 4-Channel PNG (R, G, B, Thermal)
        img_vis = Image.open(vis_file).convert("RGB")
        img_thm = Image.open(thm_file).convert("L") # Grayscale
        
        r, g, b = img_vis.split()
        img_4ch = Image.merge("RGBA", (r, g, b, img_thm))
        img_4ch.save(os.path.join(OUTPUT_PATH, "images", split, basename + ".png"))

if __name__ == "__main__":
    process_split("train")
    process_split("val")
    
    with open(os.path.join(OUTPUT_PATH, "dataset.yaml"), "w") as f:
        f.write("path: /kaggle/input/yolo-rgbt-4ch\ntrain: images/train\nval: images/val\nnames:\n  0: person\n  1: crowd\n  2: rider\n  3: uncertain\n")
    print("Done! Dataset saved to", OUTPUT_PATH)
