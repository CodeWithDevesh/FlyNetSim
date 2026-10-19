# FlyNetSim Test Suite

This directory contains automated unit and integration tests, as well as standalone verification scripts.

## Automated Test Suite

Run the full automated test suite using Python's standard `unittest` framework:

```bash
# From repository root
python3 -m unittest tests/test_sar_system.py

# Or run with discovery
python3 -m unittest discover tests
```

### Tests Covered in `test_sar_system.py`:
1. **`TestSARWorld`**:
   - Grid partitioning and spatial coordinate generation.
   - Base station coordinates at $5\%$ of the arena boundary.
   - Sector lookup and boundary coordinate clamping.
   - Ground-truth export schema and victim mapping.
2. **`TestRGBTDetector`**:
   - Model loading and weight verification (`best.pt`).
   - 4-channel early-fusion tensor preprocessing and channel ordering ($[T, B, G, R]$ for P2).
   - Inference on synthetic multispectral frames with structured detection format.
3. **`TestRFPhysicsEngine`**:
   - Euclidean distance calculation in scaled coordinates.
   - Distance-dependent SNR degradation and packet error rate (PER) behavior.
4. **`TestSwarmSimulation`**:
   - Swarm spawn positions originating from Ground Control Station (Base Station).
   - Mid-flight motor failure injection and autonomous sector failover reassignment.
   - Streaming generator yielding intermediate simulation progress.

---

## Standalone Verification Scripts

These scripts provide targeted inspection during development:

- `test_dataloader.py`: Validates custom 4-channel image loading in Ultralytics data pipeline.
- `test_inference.py`: Smoke test for 4-channel numpy array input to YOLOv8.
- `test_inference2.py`: Channel tensor interception and verification before model backbone.
- `test_demo_fix.py`: Predicts on real validation frames and checks output dimensions.
- `test_demo_plot.py`: Verifies OpenCV and Matplotlib rendering of bounding boxes on 4-channel frames.
