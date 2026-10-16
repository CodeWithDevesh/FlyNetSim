import os
import glob
import json
import random
import numpy as np

class SARWorld:
    """
    In-Memory Spatial World Representation for Drone Swarm SAR Missions.
    Maps actual multispectral dataset images and bounding box annotations onto a 2D spatial coordinate grid.
    """

    def __init__(self, arena_width=400.0, arena_height=400.0, grid_cols=5, grid_rows=5,
                 images_dir="/home/devesh/Downloads/YOLO_RGBT_4CH_Mini/images/val",
                 labels_dir="/home/devesh/Downloads/YOLO_RGBT_4CH_Mini/labels/val",
                 seed=42):
        self.arena_width = arena_width
        self.arena_height = arena_height
        self.grid_cols = grid_cols
        self.grid_rows = grid_rows
        self.sector_width = arena_width / grid_cols
        self.sector_height = arena_height / grid_rows
        self.images_dir = images_dir
        self.labels_dir = labels_dir

        random.seed(seed)
        np.random.seed(seed)

        self.sectors = {}
        self.ground_truth_victims = []
        self.base_station = [round(arena_width * 0.05, 1), round(arena_height * 0.05, 1)]
        self._build_world()

    def _build_world(self):
        img_files = sorted(glob.glob(os.path.join(self.images_dir, "*.png")))
        if not img_files:
            raise FileNotFoundError(f"No 4-channel PNG images found in {self.images_dir}")

        random.shuffle(img_files)
        total_sectors = self.grid_cols * self.grid_rows
        
        # Pick images for sectors (loop if dataset has fewer than needed)
        assigned_images = [img_files[i % len(img_files)] for i in range(total_sectors)]

        sector_idx = 0
        for r in range(self.grid_rows):
            for c in range(self.grid_cols):
                xmin = c * self.sector_width
                xmax = xmin + self.sector_width
                ymin = r * self.sector_height
                ymax = ymin + self.sector_height
                center_x = (xmin + xmax) / 2.0
                center_y = (ymin + ymax) / 2.0

                img_path = assigned_images[sector_idx]
                base_name = os.path.basename(img_path).replace(".png", "")
                lbl_path = os.path.join(self.labels_dir, base_name + ".txt")

                victims_in_sector = []
                if os.path.exists(lbl_path):
                    with open(lbl_path, "r") as f:
                        lines = f.readlines()
                    for k, line in enumerate(lines):
                        parts = line.strip().split()
                        if not parts:
                            continue
                        cls_id = int(float(parts[0]))
                        # Filter uncertain (class 3 in original voc) if present
                        if cls_id == 3:
                            continue
                        
                        xc_norm, yc_norm, w_norm, h_norm = [float(v) for v in parts[1:5]]
                        
                        # Project normalized bounding box center to World (X, Y)
                        world_x = round(xmin + xc_norm * self.sector_width, 2)
                        world_y = round(ymin + yc_norm * self.sector_height, 2)
                        
                        victim = {
                            "target_id": f"GT_S{sector_idx:02d}_{k:02d}",
                            "sector_id": sector_idx,
                            "class_id": 0,
                            "class_name": "human",
                            "world_x": world_x,
                            "world_y": world_y,
                            "norm_bbox": [xc_norm, yc_norm, w_norm, h_norm],
                            "image_file": os.path.basename(img_path)
                        }
                        victims_in_sector.append(victim)
                        self.ground_truth_victims.append(victim)

                self.sectors[sector_idx] = {
                    "sector_id": sector_idx,
                    "col": c,
                    "row": r,
                    "bounds": [xmin, xmax, ymin, ymax],
                    "center": [center_x, center_y],
                    "image_path": img_path,
                    "victim_count": len(victims_in_sector),
                    "victims": victims_in_sector
                }
                sector_idx += 1

        print(f"[SARWorld] Generated world ({self.arena_width}m x {self.arena_height}m) with {total_sectors} sectors.")
        print(f"[SARWorld] Total ground truth human targets placed in world: {len(self.ground_truth_victims)}")

    def get_sector_at(self, x, y):
        """Finds the sector covering coordinates (x, y)"""
        c = int(np.clip(x // self.sector_width, 0, self.grid_cols - 1))
        r = int(np.clip(y // self.sector_height, 0, self.grid_rows - 1))
        sector_idx = r * self.grid_cols + c
        return self.sectors.get(sector_idx, None)

    def capture_frame(self, x, y, alt=25.0):
        """
        Simulates onboard camera capture at drone coordinate (x, y).
        Returns the corresponding 4-channel image and sector metadata.
        """
        sector = self.get_sector_at(x, y)
        if not sector:
            return None, None
        return sector["image_path"], sector

    def save_ground_truth(self, filepath="ground_truth_world.json"):
        """Exports the complete ground truth world state for validation scoring"""
        payload = {
            "arena_width": self.arena_width,
            "arena_height": self.arena_height,
            "grid_cols": self.grid_cols,
            "grid_rows": self.grid_rows,
            "base_station": self.base_station,
            "total_sectors": len(self.sectors),
            "total_victims": len(self.ground_truth_victims),
            "sectors": [
                {
                    "sector_id": s["sector_id"],
                    "bounds": s["bounds"],
                    "center": s["center"],
                    "image_file": os.path.basename(s["image_path"]),
                    "victim_count": s["victim_count"]
                }
                for s in self.sectors.values()
            ],
            "victims": self.ground_truth_victims
        }
        with open(filepath, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"[SARWorld] Ground truth world exported to: {filepath}")
        return filepath


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="In-Memory Spatial SAR World Generator")
    parser.add_argument("--arena", type=float, default=400.0, help="Arena width and height in meters (default: 400.0)")
    parser.add_argument("--grid", type=int, default=5, help="Number of rows and cols in sector grid (default: 5)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--out", type=str, default="ground_truth_world.json", help="Output JSON path (default: ground_truth_world.json)")
    args = parser.parse_args()

    world = SARWorld(arena_width=args.arena, arena_height=args.arena, grid_cols=args.grid, grid_rows=args.grid, seed=args.seed)
    world.save_ground_truth(args.out)
