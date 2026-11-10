# FlyNetSim Test Suite

This directory contains automated unit and integration tests, as well as standalone verification scripts.

## Automated Test Suite

Run the full automated test suite using Python's standard `unittest` framework:

```bash
# From repository root
python3 -m unittest discover -s tests

# Or run with discovery
python3 -m unittest discover -s tests
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

## One-off checks (not tests)

These development scripts now live in [`scripts/debug/`](../scripts/debug/). Run them from the repository root, e.g. `python scripts/debug/check_inference.py`:

- `check_dataloader.py`: validates custom 4-channel image loading in the Ultralytics data pipeline.
- `check_inference.py`: smoke test for 4-channel numpy array input.
- `check_inference_channels.py`: channel tensor interception before the model backbone.
- `check_demo_fix.py`: predicts on real validation frames and checks output dimensions.
- `check_demo_plot.py`: verifies OpenCV and Matplotlib rendering of boxes on 4-channel frames.
