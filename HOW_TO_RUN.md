# FlyNetSim & Multispectral Drone Swarm: Complete User & Execution Guide

This document provides step-by-step instructions on how to run every component of the **Autonomous Multispectral UAV Swarm SAR System**, including:
1. **Interactive Web Demo** (Gradio frontend for real-time model inspection).
2. **In-Memory Spatial World Generator** (Maps dataset images and ground-truth targets).
3. **Decentralized Swarm Mission Simulator** (Multi-drone autonomous search with RF physics and EdgeBroker P2P mesh).
4. **Mission Validator & Publication Graph Generator** (Scores swarm output against ground truth and renders 300 DPI figures).
5. **Autopilot SITL Swarm Integration** (ArduPilot + DroneKit flight loop).
6. **Dataset & Training Pipeline** (VOC conversion, label remapping, and YOLOv8n-P2 training).

---

## 1. Quick Environment Setup

All dependencies (PyTorch, Ultralytics YOLOv8, OpenCV, Gradio, Matplotlib, ZeroMQ) are pre-installed in the local virtual environment.

Always activate the virtual environment before executing commands:

```bash
cd /home/devesh/Projects/FlyNetSim
source FlySim/venv/bin/activate
```

---

## 2. Interactive Web Demo (Gradio Frontend)

Use this interface to demonstrate the 4-channel Early-Fusion neural vision system (Visible RGB + Thermal IR).

### How to Run:
```bash
python demo.py
```

### Accessing the Web Interface:
* Open your browser and navigate to: **http://localhost:7860**
* If accessing remotely, forward the port or set `share=True` in `demo.py`.

### Multi-Tab Dashboard Features:
* **Tab 1: 🛰️ Live Multispectral Camera & AI Vision**:
  * *Sensor Display Modes*: 3-panel panoramic view (**Visible RGB | Thermal LWIR Heatmap | Fused AI Output**).
  * *Confidence Slider*: Real-time threshold adjustments ($\tau_{\text{conf}} \in [0.05, 0.90]$).
  * *Scan Next Sector*: Randomly tests 4-channel frames against the trained YOLOv8n-P2 model.
* **Tab 2: 🗺️ Post-Mission Spatial Map & Victim Matches**:
  * *KPI Banner*: Live summary cards for Area Coverage (%), Mission Recall (%), Mean Localization Error (m), Network PDR (%), and TTFD.
  * *2D Spatial Validation Map*: High-resolution rendering showing sectors, UAV flight tracks, true targets, detections, and missed victims.
  * *Interactive Proximity Match Table*: Filterable table comparing true coordinates vs detected coordinates and error distances in meters.
* **Tab 3: 📡 FANET RF Mesh & Propagation Dynamics**:
  * *Network KPI Cards*: Packets sent, delivered, PDR %, and swarm consensus spread %.
  * *RF Physics Curves*: Mission exploration progress over time alongside distance vs SNR/PER waterfall curves.
  * *P2P Dissemination Table*: Interactive table displaying the recent 100 packet transmissions, SNR, and delivery status.
* **Tab 4: 🔬 Mission Simulator & Parameter Sweep**:
  * Form to trigger a new swarm simulation directly from the web browser (sliders for swarm size, arena size, confidence threshold, and mission duration).
  * Click *"Launch Swarm Mission"* to automatically re-simulate, re-validate against ground truth, and refresh all KPI cards and plots in real time.

---

## 3. In-Memory SAR World Generator (`sar_world.py`)

Constructs a simulated 2D disaster area in memory, placing multispectral dataset frames into spatial sectors and projecting true victim bounding boxes into global world coordinates $(X, Y)$.

### How to Run:
```bash
python sar_world.py
```

### Configurable CLI Arguments:
```bash
python sar_world.py --arena 400.0 --grid 5 --seed 42 --out ground_truth_world.json
```
* `--arena`: Width and height of the search area in meters (default: `400.0`).
* `--grid`: Number of sector rows and columns (e.g., `5` produces $5 \times 5 = 25$ sectors).
* `--seed`: Random seed for reproducible image-to-sector assignments.
* `--out`: Target JSON export path (default: `ground_truth_world.json`).

### Output:
* Generates **`ground_truth_world.json`**, containing sector boundaries and true victim locations used by the validator.

---

## 4. Autonomous Swarm Mission Simulator (`simulate_swarm_mission.py`)

Simulates a swarm of autonomous drones sweeping the disaster arena. As each drone navigates its assigned route:
1. It captures multispectral frames from the sector beneath it.
2. It executes 4-channel early-fusion inference using `best.pt`.
3. It broadcasts discovered victim alerts over a peer-to-peer ZeroMQ mesh network.
4. The `EdgeBroker` applies realistic RF physics (Free Space Path Loss at 5 GHz, Log-Distance Shadow Fading with $\sigma = 7.5\text{ dB}$, and dynamic SNR-to-PER conversion).
5. Dropped packets are queued in QoS 1 Store-and-Forward buffers and flushed when drones re-enter RF range.

### How to Run:
```bash
python simulate_swarm_mission.py
```

### Configurable CLI Arguments:
```bash
python simulate_swarm_mission.py --drones 3 --arena 400.0 --grid 5 --conf 0.20 --duration 180 --step 1.0
```
* `--drones`: Swarm size (e.g., `3`, `5`, or `8` UAVs).
* `--arena`: Arena width/height in meters (default: `400.0`).
* `--grid`: Number of sector grid rows/cols (default: `5`).
* `--conf`: Detection confidence threshold for alerts (default: `0.20`).
* `--duration`: Total simulated mission time in seconds (default: `180`).
* `--step`: Simulation time step size in seconds (default: `1.0`).
* `--model`: Path to model weights (default: `best.pt`).

### Generated Logs & Data Files:
* **`swarm_mission_output.json`**: Complete flight trajectories, per-drone discovery counts, and swarm consensus maps.
* **`metrics_vision.csv`**: Record of every neural detection (timestamp, UAV ID, sector, confidence, world coordinates, latency).
* **`metrics_network.csv`**: Record of every P2P transmission (timestamp, source, destination, distance, SNR, PER, delivered/buffered status).
* **`metrics_mission.csv`**: Time series of mission progression (area coverage %, unique victims found, consensus spread %, minimum inter-UAV distance).

---

## 5. Ground-Truth Mission Validator & Plotting (`validate_swarm_mission.py`)

Compares the swarm's reported detections against actual ground-truth dataset annotations using spatial proximity matching ($R \le 18\text{m}$).

### How to Run:
```bash
python validate_swarm_mission.py
```

### Configurable CLI Arguments:
```bash
python validate_swarm_mission.py --world ground_truth_world.json --swarm swarm_mission_output.json --thresh 18.0
```
* `--world`: Ground-truth world JSON file.
* `--swarm`: Swarm output JSON file.
* `--thresh`: Spatial matching tolerance radius in meters (default: `18.0`).

### Console Output:
Displays a formatted terminal dashboard with:
* **Area Survey Coverage (%)**
* **Time-to-First-Detection (TTFD)**
* **True Positives (TP), False Positives (FP), False Negatives (FN)**
* **Mission Precision, Recall, and F1-Score**
* **Mean & RMSE Localization Error (meters)**
* **Packet Delivery Ratio (PDR %)**
* **Swarm Consensus Spread (%)**

### Generated Publication Assets:
1. **`sar_mission_spatial_validation.png`**:
   * High-resolution 2D map displaying sector grids, UAV flight paths, Ground Truth Victims, Detected Victims (TP), Missed Targets (FN), and False Alarms (FP).
2. **`sar_network_and_mission_performance.png`**:
   * *Left Panel*: Area Coverage Rate (%) & Swarm Consensus (%) vs. Mission Elapsed Time.
   * *Right Panel*: Inter-UAV Distance (m) vs. Observed SNR (dB) vs. Dynamic Packet Error Rate (PER).
3. **`mission_validation_report.json`**:
   * Complete quantitative metrics report in JSON format for automated paper tables.

---

## 6. Single-Command End-to-End Experiment Pipeline

To execute a full simulation and immediately generate the validation report and plots in one command:

```bash
python simulate_swarm_mission.py && python validate_swarm_mission.py
```

To run a parameter sweep (e.g. testing with 5 drones at a higher confidence threshold):

```bash
python simulate_swarm_mission.py --drones 5 --conf 0.25 --duration 200 && python validate_swarm_mission.py
```

---

## 7. ArduPilot SITL / DroneKit Autonomous Flight Loop (`FlySim/uav_pubsub.py`)

If you are running the full Software-In-The-Loop (SITL) autopilot simulation:

1. Launch the ArduPilot SITL vehicle instances (e.g. using `FlyNetSim.py` or `fly_init.sh`).
2. Each drone instance initializes `RGBTDetector` and its `EdgeBroker`.
3. In `UAV.brain_loop()`, the drone automatically:
   * Arms and takes off to its assigned altitude ($10\text{m} - 25\text{m}$).
   * Disperses to avoid close peers ($d < 10\text{m}$).
   * Captures multispectral frames and runs inference.
   * Disseminates `target_alert` packets over ZMQ port `6000 + ID` to all neighboring drones.

---

## 8. Dataset Preparation & Model Training Pipeline

If you want to re-train or fine-tune the 4-channel YOLOv8 model:

### Step 8.1: Convert VOC Dataset to 4-Channel RGBA PNGs
Merges Visible RGB JPGs and Thermal Infrared Grayscale JPGs into 4-channel PNGs:
```bash
python convert_4channel.py
```

### Step 8.2: Filter & Remap Classes to Single Class (`0: human`)
Strips `uncertain` labels and unifies `person`, `crowd`, and `rider` into class `0`:
```bash
python prepare_1cls_dataset.py
```

### Step 8.3: Train YOLOv8n-P2 4-Channel Model
Trains the 29-layer P2 high-resolution architecture:
```bash
python train_1cls.py
```
*(Or upload [`yolov8n-p2-1cls-4ch.yaml`](file:///home/devesh/Projects/FlyNetSim/yolov8n-p2-1cls-4ch.yaml) and [`dataset_1cls_4ch.yaml`](file:///home/devesh/Projects/FlyNetSim/dataset_1cls_4ch.yaml) to Kaggle / Google Colab for GPU training).*

---

## 9. File & Repository Reference Map

| File / Directory | Description |
| :--- | :--- |
| [`demo.py`](file:///home/devesh/Projects/FlyNetSim/demo.py) | Interactive Gradio Web GUI for multispectral model inspection (`http://localhost:7860`). |
| [`sar_world.py`](file:///home/devesh/Projects/FlyNetSim/sar_world.py) | In-memory spatial world generator mapping dataset images and labels onto 2D sectors. |
| [`simulate_swarm_mission.py`](file:///home/devesh/Projects/FlyNetSim/simulate_swarm_mission.py) | Multi-UAV decentralized simulation engine with vision inference, RF physics, and QoS 1 buffering. |
| [`validate_swarm_mission.py`](file:///home/devesh/Projects/FlyNetSim/validate_swarm_mission.py) | Ground-truth validator computing TP/FP/FN, precision, recall, RMSE, PDR, and rendering plots. |
| [`rgbt_detector.py`](file:///home/devesh/Projects/FlyNetSim/rgbt_detector.py) | Modular 4-channel early-fusion YOLOv8 inference wrapper with multispectral rendering. |
| [`best.pt`](file:///home/devesh/Projects/FlyNetSim/best.pt) | Trained 4-channel YOLOv8n-P2 model weights. |
| [`yolov8n-p2-1cls-4ch.yaml`](file:///home/devesh/Projects/FlyNetSim/yolov8n-p2-1cls-4ch.yaml) | 4-channel YOLOv8-P2 model architecture specification (4 detection scales: P2, P3, P4, P5). |
| [`dataset_1cls_4ch.yaml`](file:///home/devesh/Projects/FlyNetSim/dataset_1cls_4ch.yaml) | Dataset YAML pointing to images/train and images/val with class `0: human`. |
| [`FlySim/swarm_network.py`](file:///home/devesh/Projects/FlyNetSim/FlySim/swarm_network.py) | Decentralized `EdgeBroker` with DMLT routing, QoS 1 Store-and-Forward queues, and `RFPhysicsEngine`. |
| [`FlySim/uav_pubsub.py`](file:///home/devesh/Projects/FlyNetSim/FlySim/uav_pubsub.py) | ArduPilot SITL / DroneKit autonomous autopilot flight loop with vision and swarm communication. |
| [`PAPER_METRICS_AND_EXPERIMENTS.md`](file:///home/devesh/Projects/FlyNetSim/PAPER_METRICS_AND_EXPERIMENTS.md) | Academic paper specification: mathematical formulas, variables, and publication figure blueprints. |
