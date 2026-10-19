from ultralytics import YOLO
import numpy as np

img = np.zeros((640, 640, 4), dtype=np.uint8)
img[:, :, 0] = 1 # B
img[:, :, 1] = 2 # G
img[:, :, 2] = 3 # R
img[:, :, 3] = 4 # A
model = YOLO('best.pt')

# We can intercept the tensor before it goes to the model
from ultralytics.engine.predictor import BasePredictor
old_pre = BasePredictor.preprocess
def new_pre(self, im):
    tensor = old_pre(self, im)
    print("TENSOR CHANNELS:", tensor[0, :, 0, 0])
    return tensor
BasePredictor.preprocess = new_pre

model.predict(img)
