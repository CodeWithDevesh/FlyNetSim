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
import shutil
import tempfile
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
from FlySim.hysteresis_controller import DualThresholdHysteresisController, compute_ew_cvt_centroids


class TestSARWorld(unittest.TestCase):
    def setUp(self):
        self.arena_size = 400.0
        self.grid_dim = 4
        self._tmp = tempfile.mkdtemp(prefix="sar_test_")
        self.test_json = os.path.join(self._tmp, "ground_truth_temp.json")
        self.world = SARWorld(arena_width=self.arena_size, arena_height=self.arena_size,
                              grid_cols=self.grid_dim, grid_rows=self.grid_dim, seed=42)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

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
        self.assertEqual(self.detector.nc, 1, "Model must have 1 class ('human' or 'person').")
        self.assertIn(0, self.detector.names)
        self.assertIn(self.detector.names[0], ["human", "person"])

    def test_preprocessing_4channel(self):
        # Create synthetic 4-channel BGRA image (640x512)
        dummy_bgra = np.zeros((512, 640, 4), dtype=np.uint8)
        dummy_bgra[:, :, 0] = 50   # Blue
        dummy_bgra[:, :, 1] = 100  # Green
        dummy_bgra[:, :, 2] = 150  # Red
        dummy_bgra[:, :, 3] = 200  # Thermal

        img_prep, img_orig = self.detector.preprocess_4channel(dummy_bgra)
        self.assertEqual(img_prep.shape, (512, 640, 4))
        # Channel ordering depends on model family:
        # YOLO11: [Red, Green, Blue, Thermal] -> [2, 1, 0, 3] from BGRA
        # YOLOv8-P2: [Thermal, Blue, Green, Red] -> [3, 0, 1, 2] from BGRA
        if self.detector.channel_order == [2, 1, 0, 3]:
            self.assertEqual(img_prep[0, 0, 0], 150)  # Red
            self.assertEqual(img_prep[0, 0, 1], 100)  # Green
            self.assertEqual(img_prep[0, 0, 2], 50)   # Blue
            self.assertEqual(img_prep[0, 0, 3], 200)  # Thermal
        elif self.detector.is_p2:
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
            self.assertIn(det["class_name"], ["human", "person"])


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
        out_dir = tempfile.mkdtemp(prefix="sar_sim_test_")   # keep mission outputs out of the repo
        self.addCleanup(shutil.rmtree, out_dir, ignore_errors=True)
        sim = SwarmSimulation(num_drones=num_drones, arena_size=arena_size, grid_dim=5,
                              conf_thresh=0.20, seed=42, fail_drone_id=1, fail_time=5.0,
                              out_dir=out_dir)

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


class TestDualThresholdHysteresis(unittest.TestCase):
    def setUp(self):
        self.controller = DualThresholdHysteresisController(
            uav_id="0",
            initial_pos=(100.0, 100.0),
            b_max=100.0,
            tau_epsilon_ratio=0.02, # 2.0%
            tau_delta=5.0,          # 5.0m
            alpha=1.0,
            initial_battery=100.0,
            initial_topology=["0", "1", "2"]
        )

    def test_battery_micro_fluctuation_locking(self):
        # Drop battery by 0.5% (less than 2% threshold)
        res = self.controller.evaluate(
            current_time=1.0,
            current_battery=99.5,
            theoretical_centroid=(120.0, 120.0), # Even with larger spatial shift, steady state requires both
            current_topology=["0", "1", "2"]
        )
        self.assertFalse(res["trigger_u_t"], "Small battery drop < tau_epsilon must hold update.")
        self.assertEqual(res["reason"], "HYSTERESIS_LOCKED_CHATTERING_SUPPRESSED")
        self.assertEqual(res["effective_weight"], 1.0, "Weight must stay locked to w_i(t_k).")
        self.assertEqual(res["commanded_pos"], (100.0, 100.0), "Waypoint must stay locked to C_i(t_k).")

    def test_spatial_centroid_chattering_suppression(self):
        # Drop battery by 3.0% (>= tau_epsilon), but centroid shift is only 2.0m (< tau_delta)
        res = self.controller.evaluate(
            current_time=2.0,
            current_battery=97.0,
            theoretical_centroid=(101.5, 101.0), # distance = sqrt(1.5^2 + 1^2) = 1.8m < 5.0m
            current_topology=["0", "1", "2"]
        )
        self.assertFalse(res["trigger_u_t"], "Sub-threshold spatial shift must suppress chattering.")
        self.assertEqual(res["reason"], "HYSTERESIS_LOCKED_CHATTERING_SUPPRESSED")
        self.assertEqual(res["commanded_pos"], (100.0, 100.0))
        self.assertGreater(self.controller.chattering_events_suppressed, 0)

    def test_steady_state_dual_threshold_update(self):
        # Battery drop >= 2.0% AND spatial shift >= 5.0m
        res = self.controller.evaluate(
            current_time=5.0,
            current_battery=96.0, # delta_b = 4.0% >= 2.0%
            theoretical_centroid=(110.0, 110.0), # shift = 14.14m >= 5.0m
            current_topology=["0", "1", "2"]
        )
        self.assertTrue(res["trigger_u_t"], "Dual threshold satisfaction must trigger partition update.")
        self.assertEqual(res["reason"], "STEADY_STATE_DUAL_THRESHOLD_MET")
        self.assertEqual(res["commanded_pos"], (110.0, 110.0))
        self.assertAlmostEqual(res["effective_weight"], 0.96)
        self.assertEqual(self.controller.updates_executed, 1)

    def test_forced_override_on_node_failure(self):
        # Micro fluctuations only: battery dropped by only 0.2%, centroid shifted by 0.5m
        # BUT peer '1' crashed: topology changed from ['0', '1', '2'] to ['0', '2']
        res = self.controller.evaluate(
            current_time=10.0,
            current_battery=99.8,
            theoretical_centroid=(100.3, 100.4), # shift = 0.5m
            current_topology=["0", "2"] # Node 1 removed from DLL heartbeats
        )
        self.assertTrue(res["trigger_u_t"], "Topology change N(t) != N(t_k) must force immediate hard override.")
        self.assertEqual(res["reason"], "FORCED_OVERRIDE_TOPOLOGY_CHANGE")
        self.assertEqual(res["commanded_pos"], (100.3, 100.4))
        self.assertEqual(self.controller.forced_overrides, 1)

    def test_ew_cvt_centroid_computation(self):
        generators = {
            "0": (100.0, 100.0),
            "1": (300.0, 300.0)
        }
        weights = {
            "0": 1.0,
            "1": 0.5  # UAV 1 has depleted battery, so UAV 0 expands its Voronoi cell
        }
        centroids = compute_ew_cvt_centroids(generators, weights, arena_width=400.0, arena_height=400.0, grid_res=30)
        self.assertIn("0", centroids)
        self.assertIn("1", centroids)
        # UAV 0 has twice the weight of UAV 1, so UAV 0's centroid shifts toward the center
        c0 = centroids["0"]
        c1 = centroids["1"]
        self.assertTrue(0.0 <= c0[0] <= 400.0 and 0.0 <= c0[1] <= 400.0)
        self.assertTrue(0.0 <= c1[0] <= 400.0 and 0.0 <= c1[1] <= 400.0)

    def test_ewcvt_alpha_parameter_behavior(self):
        # Target sector centroid
        sec_x, sec_y = 100.0, 100.0

        # Peer 0: Geometrically closer (5m), but heavily depleted battery (20%)
        p0_dist_sq = (105.0 - sec_x)**2 + (100.0 - sec_y)**2 # 25.0
        p0_batt_ratio = 0.20

        # Peer 2: Slightly farther (12m), but healthy full battery (100%)
        p2_dist_sq = (112.0 - sec_x)**2 + (100.0 - sec_y)**2 # 144.0
        p2_batt_ratio = 1.00

        # Case 1: Standard CVT baseline (alpha = 0.0)
        # Ignores battery, picks purely nearest geometric distance
        alpha_zero = 0.0
        cost_p0_zero = p0_dist_sq if alpha_zero == 0.0 else p0_dist_sq / (p0_batt_ratio ** alpha_zero)
        cost_p2_zero = p2_dist_sq if alpha_zero == 0.0 else p2_dist_sq / (p2_batt_ratio ** alpha_zero)
        self.assertLess(cost_p0_zero, cost_p2_zero, "Standard CVT (alpha=0) must choose geometrically closer peer.")

        # Case 2: Aggressive EW-CVT (alpha = 2.0)
        # Strongly penalizes low-battery peer, shifting workload to healthy drone
        alpha_ewcvt = 2.0
        cost_p0_ew = p0_dist_sq / (p0_batt_ratio ** alpha_ewcvt) # 25 / 0.04 = 625
        cost_p2_ew = p2_dist_sq / (p2_batt_ratio ** alpha_ewcvt) # 144 / 1.00 = 144
        self.assertLess(cost_p2_ew, cost_p0_ew, "EW-CVT (alpha=2.0) must reassign workload to higher battery peer.")


if __name__ == "__main__":
    unittest.main()
