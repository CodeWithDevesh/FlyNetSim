import cv2
from ultralytics import YOLO
import glob

img_path = glob.glob('/home/devesh/Downloads/YOLO_RGBT_4CH_Mini/images/val/*.png')[0]
img_4ch = cv2.imread(img_path, cv2.IMREAD_UNCHANGED)

model = YOLO('best.pt')
results = model.predict(source=img_4ch)
print("SUCCESS! Output shape:", results[0].orig_img.shape)
