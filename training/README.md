# Multispectral YOLOv8 Training Pipeline

This directory contains the dataset preparation scripts, model architecture definitions, and training pipelines for the **4-channel Early-Fusion YOLOv8-P2 multispectral drone vision system**.

---

## Directory Contents

| File | Description |
| :--- | :--- |
| [`prepare_dataset.py`](prepare_dataset.py) | Unified dataset converter: merges Visible RGB + Thermal LWIR into 4-channel PNGs, parses VOC XML, filters 'uncertain', and remaps classes to single-class `0: human`. |
| [`train.py`](train.py) | Python CLI training script for local multi-GPU / single-GPU / CPU execution with 4-channel pretrained weight initialization. |
| [`train_1cls.py`](train_1cls.py) | Backward-compatible alias for `train.py`. |
| [`train_yolov8_rgbt.ipynb`](train_yolov8_rgbt.ipynb) | Complete Kaggle/Google Colab GPU training notebook with full dual-Tesla-T4 training logs and validation cell outputs. |
| [`yolov8n-p2-1cls-4ch.yaml`](yolov8n-p2-1cls-4ch.yaml) | 29-layer YOLOv8-P2 model architecture specification (4 detection scales: stride 4, 8, 16, 32). |
| [`dataset_1cls_4ch.yaml`](dataset_1cls_4ch.yaml) | Dataset YAML configuration defining image split paths and class mapping (`0: human`). |

---

## 1. Dataset Preparation

The raw dataset (`RGBTDronePerson`) contains paired Visible RGB JPGs, Thermal Grayscale JPGs, and Pascal VOC XML annotations.

Run the unified converter to create the full 4-channel dataset:

```bash
python training/prepare_dataset.py \
  --src /home/devesh/Downloads/RGBTDronePerson \
  --dst /home/devesh/Downloads/YOLO_RGBT_4CH \
  --splits train val
```

### What this script does:
1. **4-Channel Early Fusion**:
   - Reads `visible/{name}.jpg` (RGB).
   - Reads `thermal/{name}.jpg` (Grayscale LWIR).
   - Merges them into a 4-channel RGBA PNG (`[R, G, B, Thermal]`).
2. **Annotation Parsing & Class Remapping**:
   - Parses `annotation/{name}.xml`.
   - Strips ambiguous annotations (`uncertain`).
   - Remaps all valid person classes (`person`, `crowd`, `rider`) to unified class `0: human`.
   - Normalizes coordinates into standard YOLO format `(cls, x_center, y_center, width, height)`.
3. **Configuration Generation**:
   - Automatically writes `dataset_1cls_4ch.yaml` in the destination folder.

---

## 2. Model Architecture: YOLOv8n-P2

Standard YOLOv8 models use 3 detection scales ($P3/8, P4/16, P5/32$). However, small humans viewed from aerial altitudes ($25\text{--}50\text{m}$ AGL) occupy as few as $8 \times 8$ to $16 \times 16$ pixels, which can be lost after repeated downsampling.

The **P2 architecture** adds a high-resolution detection head ($P2/4$, stride 4, $160 \times 128$ at $640\text{px}$ input):
- **Backbone**: Modified first layer accepting 4 input channels.
- **Feature Pyramid Network**: Additional lateral connection from Backbone Layer 2 ($P2$) into the detection head.
- **Detection Output**: 4 scales predicting bounding boxes at strides 4, 8, 16, and 32.

---

## 3. Training the Model

### Local Execution (CLI):
```bash
# Train for 40 epochs on GPU 0
python training/train.py \
  --data training/dataset_1cls_4ch.yaml \
  --model training/yolov8n-p2-1cls-4ch.yaml \
  --epochs 40 \
  --batch 32 \
  --imgsz 1024 \
  --device 0
```

### Cloud / GPU Training (Kaggle or Google Colab):
1. Upload [`train_yolov8_rgbt.ipynb`](train_yolov8_rgbt.ipynb) to Kaggle or Colab.
2. Select a GPU accelerator (e.g., dual Tesla T4 or A100).
3. Mount the 4-channel dataset.
4. Execute the notebook. When training completes, download `best.pt` to the project root directory.

---

## 4. Pretrained Weight Transfer for 4-Channel Input

Because standard COCO pretrained checkpoints (`yolov8n.pt`) have 3-channel input weights of shape `[64, 3, 3, 3]`, `train.py` initializes the 4th channel using the channel-wise mean of the pretrained weights:

```python
w3 = YOLO('yolov8n.pt').model.model[0].conv.weight.data
with torch.no_grad():
    c = model.model.model[0].conv.weight
    c[:, :3] = w3
    c[:, 3:] = w3.mean(1, keepdim=True)
```
This enables the network to leverage pretrained feature extractors immediately without training from scratch.
