import os, shutil, random

src = "/home/devesh/Downloads/YOLO_RGBT_4CH"
dst = "/home/devesh/Downloads/YOLO_RGBT_4CH_Mini"

os.makedirs(dst, exist_ok=True)
shutil.copy(os.path.join(src, "dataset.yaml"), os.path.join(dst, "dataset.yaml"))

for split, count in [("train", 800), ("val", 200)]:
    os.makedirs(os.path.join(dst, "images", split), exist_ok=True)
    os.makedirs(os.path.join(dst, "labels", split), exist_ok=True)
    
    images = os.listdir(os.path.join(src, "images", split))
    images.sort() # Ensure deterministic but we can shuffle
    random.seed(42)
    random.shuffle(images)
    
    selected = images[:count]
    
    for img in selected:
        basename = img.replace(".png", "")
        # Copy image
        shutil.copy(os.path.join(src, "images", split, img), os.path.join(dst, "images", split, img))
        # Copy label
        lbl_file = basename + ".txt"
        shutil.copy(os.path.join(src, "labels", split, lbl_file), os.path.join(dst, "labels", split, lbl_file))

print("Done copying 1000 images!")
