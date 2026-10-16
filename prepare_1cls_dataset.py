#!/usr/bin/env python3
"""
Convert labels from original 4 classes (person, crowd, rider, uncertain)
to single class: 0: human (filtering out uncertain).
"""

import os
from pathlib import Path
import yaml

DROP_CLASS = 'uncertain'

def convert_labels(dataset_root, output_root):
    dataset_root = Path(dataset_root)
    output_root = Path(output_root)
    
    cfg_file = dataset_root / 'dataset.yaml'
    if not cfg_file.exists():
        print(f"Warning: {cfg_file} not found")
        names = ['person', 'crowd', 'rider', 'uncertain']
    else:
        with open(cfg_file) as f:
            cfg = yaml.safe_load(f)
        names = cfg['names']
        names = [names[k] for k in sorted(names)] if isinstance(names, dict) else list(names)
        
    drop_id = names.index(DROP_CLASS) if DROP_CLASS in names else -1
    print(f"Filtering dataset: drop class '{DROP_CLASS}' (id={drop_id})")

    for split in ('train', 'val'):
        src_lbl = dataset_root / 'labels' / split
        dst_lbl = output_root / 'labels' / split
        dst_img = output_root / 'images' / split
        src_img = dataset_root / 'images' / split

        dst_lbl.mkdir(parents=True, exist_ok=True)
        dst_img.mkdir(parents=True, exist_ok=True)

        if not src_lbl.exists():
            continue

        n_boxes = 0
        n_dropped = 0
        for lbl_path in src_lbl.glob('*.txt'):
            lines = lbl_path.read_text().splitlines()
            out_lines = []
            for line in lines:
                parts = line.split()
                if not parts:
                    continue
                cls_id = int(float(parts[0]))
                if cls_id == drop_id:
                    n_dropped += 1
                    continue
                # Map person (0), crowd (1), rider (2) all to 0 ('human')
                out_lines.append(' '.join(['0'] + parts[1:]))
                n_boxes += 1
            (dst_lbl / lbl_path.name).write_text('\n'.join(out_lines) + ('\n' if out_lines else ''))

        print(f"[{split}] Retained {n_boxes} 'human' boxes, removed {n_dropped} '{DROP_CLASS}' boxes.")

if __name__ == '__main__':
    src = '/home/devesh/Downloads/YOLO_RGBT_4CH_Mini'
    dst = '/home/devesh/Downloads/YOLO_RGBT_4CH_1cls'
    if os.path.exists(src):
        convert_labels(src, dst)
        print("Done preparing dataset.")
    else:
        print(f"Source dataset not found at {src}")
