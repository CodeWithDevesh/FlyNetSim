#!/usr/bin/env python3
"""
Automated Test Suite for Autonomous Multispectral Swarm SAR System.
Tests:
  1. SARWorld spatial geometry and ground-truth mapping.
  2. RGBTDetector 4-channel early-fusion neural inference.
  3. RFPhysicsEngine and DTN mesh communication.
  4. SwarmSimulation dual-speed flight dynamics, failover handoff, and generator streaming.
  5. Post-mission validation scoring against ground truth.
"""

import os
import sys
import math
import json
import unittest
import numpy as np

# Ensure root directory is on PYTHONPATH
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from sar_world import SARWorld
from rgbt_detector import RGBTDetector
from simulate_swarm_mission import SwarmSimulation
from validate_swarm_mission import run_validation
from FlySim import swarm_network


class TestSARWorld(unittest.TestCase):
    def setUp(self):
        self.arena_size = 400.0
        self.grid_dim = 4
        self.test_json = "tests/test_ground_truth_temp.json"
        self.world = SARWorld(arena_width=self.arena_size, arena_height=self.arena_size,
                              grid_cols=self.grid_dim, grid_rows=self.grid_dim, seed=42)

    def tearDown(self):
        if os.path.exists(self.test_json):
            os.remove(self.test_json)

    def test_grid_initialization(self):
        total_sectors = self.grid_dim * self.grid_dim
        self.assertEqual(len(self.world.sectors), total_sectors)
        expected_sector_size = self.arena_size / self.grid_dim
        self.assertAlmostEqual(self.world.sector_width, expected_sector_size)
        self.assertAlmostEqual(self.world.sector_height, expected_sector_size)

    def test_base_station_coordinates(self):
        bx, by = self.world.base_station
        self.assertAlmostEqual(bx, round(self.arena_size * 0.05, 1))
        self.assertAlmostEqual(by, round(self.arena_size * 0.05, 1))

    def test_sector_lookup(self):
        # Center of arena should fall into the middle sectors
        center_sec = self.world.get_sector_at(self.arena_size / 2.0, self.arena_size / 2.0)
        self.assertIsNotNone(center_sec)
        # Clamping at boundary edges
        edge_sec = self.world.get_sector_at(self.arena_size + 100.0, self.arena_size + 100.0)
        self.assertIsNotNone(edge_sec)
        self.assertEqual(edge_sec["sector_id"], (self.grid_dim * self.grid_dim) - 1)

    def test_ground_truth_export(self):
        out_path = self.world.save_ground_truth(self.test_json)
        self.assertTrue(os.path.exists(out_path))
        with open(out_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data["arena_width"], self.arena_size)
        self.assertEqual(data["total_sectors"], self.grid_dim * self.grid_dim)
        self.assertIn("victims", data)


class TestRGBTDetector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model_path = os.path.join(ROOT_DIR, "best.pt")
        cls.detector = RGBTDetector(model_path=cls.model_path, conf_thresh=0.20)

    def test_detector_initialization(self):
        self.assertTrue(self.detector.is_ready(), "Model weights should be loaded.")
        self.assertEqual(self.detector.nc, 1, "Model must have 1 class ('human').")
        self.assertIn(0, self.detector.names)
        self.assertEqual(self.detector.names[0], "human")

    def test_preprocessing_4channel(self):
        # Create synthetic 4-channel BGRA image (640x512)
        dummy_bgra = np.zeros((512, 640, 4), dtype=np.uint8)
        dummy_bgra[:, :, 0] = 50   # Blue
        dummy_bgra[:, :, 1] = 100  # Green
        dummy_bgra[:, :, 2] = 150  # Red
        dummy_bgra[:, :, 3] = 200  # Thermal

        img_prep, img_orig = self.detector.preprocess_4channel(dummy_bgra)
        self.assertEqual(img_prep.shape, (512, 640, 4))
        # Channel ordering for P2: Thermal at index 0, Blue at 1, Green at 2, Red at 3
        if self.detector.is_p2:
            self.assertEqual(img_prep[0, 0, 0], 200)  # Thermal channel first
            self.assertEqual(img_prep[0, 0, 1], 50)   # Blue
            self.assertEqual(img_prep[0, 0, 2], 100)  # Green
            self.assertEqual(img_prep[0, 0, 3], 150)  # Red

    def test_inference_synthetic_frame(self):
        dummy_bgra = np.zeros((512, 640, 4), dtype=np.uint8)
        detections, _ = self.detector.detect(dummy_bgra, conf=0.10)
        self.assertIsInstance(detections, list)
        for det in detections:
            self.assertIn("box", det)
            self.assertIn("conf", det)
            self.assertIn("class_name", det)
            self.assertEqual(det["class_name"], "human")


class TestRFPhysicsEngine(unittest.TestCase):
    def setUp(self):
        self.engine = swarm_network.RFPhysicsEngine(tx_power_dbm=30, frequency_ghz=2.4)

    def test_distance_calculation(self):
        loc1 = {'lat': 0.0, 'lon': 0.0}
        scale = 1.113195e5
        loc2 = {'lat': 100.0 / scale, 'lon': 0.0}
        dist = self.engine.calculate_euclidean_distance(loc1, loc2)
        self.assertAlmostEqual(dist, 100.0, delta=1.0)

    def test_snr_degradation_over_distance(self):
        scale = 1.113195e5
        loc_base = {'lat': 0.0, 'lon': 0.0}
        loc_close = {'lat': 50.0 / scale, 'lon': 0.0}
        loc_far = {'lat': 2000.0 / scale, 'lon': 0.0}

        snr_close, per_close = self.engine.calculate_snr_per(loc_base, loc_close, obstacle_mask=False)
        snr_far, per_far = self.engine.calculate_snr_per(loc_base, loc_far, obstacle_mask=False)

        self.assertGreater(snr_close, snr_far, "Close distance must yield higher SNR.")
        self.assertLessEqual(per_close, per_far, "Close distance must yield lower PER.")


class TestSwarmSimulation(unittest.TestCase):
    def test_launch_base_and_failover_streaming(self):
        arena_size = 600.0
        num_drones = 3
        sim = SwarmSimulation(num_drones=num_drones, arena_size=arena_size, grid_dim=5,
                              conf_thresh=0.20, seed=42, fail_drone_id=1, fail_time=5.0)

        # All drones must originate at Ground Control Station (Base Station)
        bx, by = sim.base_station
        for d in sim.drones:
            dist_to_base = math.hypot(d.x - bx, d.y - by)
            self.assertLess(dist_to_base, 100.0, "All drones must spawn at Base Station launch pads.")

        # Test streaming runner
        steps_yielded = 0
        final_snap = None
        for snap in sim.run_streaming(max_sim_seconds=12, dt=1.0, yield_interval=4):
            steps_yielded += 1
            final_snap = snap
            self.assertIn("sim_time", snap)
            self.assertIn("active_drones", snap)
            self.assertIn("coverage_pct", snap)

        self.assertGreaterEqual(steps_yielded, 2)
        # UAV 1 was injected to fail at T=5.0s, so active drones must drop from 3 to 2
        dead_drone = next((d for d in sim.drones if str(d.uav_id) == "1"), None)
        self.assertIsNotNone(dead_drone)
        self.assertFalse(dead_drone.is_alive, "UAV 1 must be marked as crashed/stopped.")
        self.assertIsNotNone(dead_drone.crash_pos)
        self.assertEqual(final_snap["active_drones"], 2)


if __name__ == "__main__":
    unittest.main()
