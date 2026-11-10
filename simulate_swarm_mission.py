#!/usr/bin/env python3
"""
Autonomous Multi-UAV Swarm SAR Simulation Engine.

Three contributions are modelled and can each be switched off for ablation:

  1. Perception   - 4-channel RGB+Thermal early-fusion YOLO detector (rgbt_detector.py)
  2. Networking   - FANET mesh with RF physics, QoS-1 store-and-forward (DTN) buffers,
                    store-carry-forward relaying and a Ground Control Station (GCS) sink
  3. Swarm control- Energy-Weighted Centroidal Voronoi Tessellation (EW-CVT) territory
                    partitioning, gated by a dual-threshold hysteresis controller, with
                    autonomous failover when a UAV is lost

Control loop (per replan tick):
    measured battery -> fresh weights w*_i = (B_i/Bmax)^alpha
                     -> theoretical EW-CVT centroid C*_i of each UAV's cell
                     -> hysteresis controller decides whether (g_i, w_i) are *committed*
                     -> sectors that are still unscanned are re-assigned by power distance
                        d(s, i) = ||c_s - g_i||^2 / w_i   using committed g_i, w_i only
Without hysteresis every tick commits, so battery-sensor noise moves the partition borders
and sectors flip owners ("churn"); UAVs then re-route and waste energy.
"""

import os
import sys
import time
import json
import math
import random
import csv
import pickle
import numpy as np
from collections import defaultdict

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "FlySim")))

from sar_world import SARWorld
from rgbt_detector import RGBTDetector
import swarm_network
from hysteresis_controller import DualThresholdHysteresisController, compute_ew_cvt_centroids
from swarm_agent import SwarmAgent

BATTERY_RESERVE_PCT = 15.0     # RTL reserve used by the safety-margin metric
GCS_ID = "GCS"
CVT_GRID_RES = 100             # sampling resolution of the EW-CVT centroid integral

# ---------------------------------------------------------------------------
# Detection cache: every sector shows one static frame, so detections are deterministic.
# Caching them makes ablation sweeps (hundreds of missions) tractable on CPU.
# ---------------------------------------------------------------------------
_DET_CACHE = {}


def load_detection_cache(path):
    global _DET_CACHE
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            _DET_CACHE.update(pickle.load(f))
    return len(_DET_CACHE)


def save_detection_cache(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(_DET_CACHE, f)


class SimulatedUAV:
    def __init__(self, uav_id, start_x, start_y, altitude, transit_speed, search_speed, assigned_sectors,
                 physics_engine, initial_topology=None, ewcvt_alpha=1.0, initial_battery=100.0,
                 tau_epsilon_ratio=0.02, tau_delta=5.0):
        self.uav_id = str(uav_id)
        self.home_x = float(start_x)
        self.home_y = float(start_y)
        self.x = float(start_x)
        self.y = float(start_y)
        self.altitude = float(altitude)
        self.transit_speed = float(transit_speed)
        self.search_speed = float(search_speed)
        self.speed = float(transit_speed)
        self.assigned_sectors = list(assigned_sectors)   # scanned + pending sector ids
        self.pending = list(assigned_sectors)            # sectors still to survey
        self.current_waypoint_idx = 0
        self.waypoints = []
        self.state = "TRANSIT"   # TRANSIT, SEARCHING, RETURNING, LANDED, CRASHED
        self.ewcvt_alpha = float(ewcvt_alpha)
        self.tau_epsilon_ratio = tau_epsilon_ratio
        self.tau_delta = tau_delta
        self.rtl = False                 # low-battery abort: return to base, take no new sectors
        self.reached_first_sector = False
        self.arrived_at_sector = False   # set when a sector-centre waypoint is reached

        self.battery_max = 100.0
        self.battery = float(initial_battery)
        self.initial_battery = float(initial_battery)
        self.b_meas = self.battery
        self.gen = (self.x, self.y)      # committed EW-CVT generator g_i
        self.weight = (self.battery / self.battery_max) ** self.ewcvt_alpha
        self.route_changes = 0
        self.nohyst_commits = 0
        self.hysteresis = None
        self.reset_hysteresis(self.gen, initial_topology)

        self.broker = swarm_network.EdgeBroker(self.uav_id, physics_engine)
        self.discovered_targets = {}
        self.consensus_registry = {}

        self.trajectory_history = [(round(self.x, 2), round(self.y, 2))]
        self.total_distance_flown = 0.0
        self.scanned_sectors = set()
        self.is_alive = True
        self.crash_pos = None
        self.agent = None                # SwarmAgent (decentralized planner only)
        self.relaunches = 0
        self.landed_since = None
        self.fwd_known = defaultdict(set)    # alert key -> ids this UAV knows already hold it

    def reset_hysteresis(self, gen0, topology):
        """(Re)build the dual-threshold controller around the committed generator g_i(t_0)."""
        self.gen = (float(gen0[0]), float(gen0[1]))
        self.weight = (max(0.0, self.battery) / self.battery_max) ** self.ewcvt_alpha
        self.hysteresis = DualThresholdHysteresisController(
            uav_id=self.uav_id, initial_pos=self.gen, b_max=self.battery_max,
            tau_epsilon_ratio=self.tau_epsilon_ratio, tau_delta=self.tau_delta,
            alpha=self.ewcvt_alpha, initial_battery=self.battery, initial_topology=topology)

    def set_waypoints(self, waypoints):
        self.waypoints = waypoints
        self.current_waypoint_idx = 0

    def get_location_dict(self):
        scale = 1.113195e5
        return {'lat': self.y / scale, 'lon': self.x / scale}

    def update_position(self, dt, current_time=0.0, active_topology=None):
        """Physical flight toward the current waypoint. Returns True when the UAV is finished."""
        if not self.is_alive:
            self.state = "CRASHED"
            return True
        if not self.waypoints or self.current_waypoint_idx >= len(self.waypoints):
            self.state = "LANDED"
            return True

        last_idx = len(self.waypoints) - 1
        if self.current_waypoint_idx == last_idx:
            self.state = "RETURNING"
            self.speed = self.transit_speed
        elif not self.reached_first_sector:
            self.state = "TRANSIT"
            self.speed = self.transit_speed
        else:
            self.state = "SEARCHING"
            self.speed = self.search_speed

        # Kinetic battery drain (faster in high-speed transit)
        drain_rate = 0.07 if self.speed > 40.0 else 0.04
        self.battery = max(0.0, min(self.battery_max, self.battery - drain_rate * dt))

        tx, ty = self.waypoints[self.current_waypoint_idx]
        dist = math.hypot(tx - self.x, ty - self.y)
        step = self.speed * dt
        if dist <= step:
            self.x, self.y = tx, ty
            self.total_distance_flown += dist
            if self.current_waypoint_idx < last_idx:
                self.arrived_at_sector = True
                self.reached_first_sector = True
            self.current_waypoint_idx += 1
        else:
            self.x += (tx - self.x) / dist * step
            self.y += (ty - self.y) / dist * step
            self.total_distance_flown += step

        self.trajectory_history.append((round(self.x, 2), round(self.y, 2)))
        return False


class SwarmSimulation:
    def __init__(self, num_drones=3, arena_size=400.0, grid_dim=5,
                 model_path="best.pt", conf_thresh=0.20,
                 sim_speed_multiplier=5.0, seed=42,
                 fail_drone_id=None, fail_time=None,
                 base_x=None, base_y=None, ewcvt_alpha=1.0,
                 # ---- ablation switches -------------------------------------------------
                 hysteresis_enabled=True,      # dual-threshold gate on partition commits
                 failover_enabled=True,        # re-assign a lost UAV's sectors to survivors
                 dynamic_repartition=True,     # periodic EW-CVT replanning during the mission
                 dtn_enabled=True,             # QoS-1 store-and-forward buffering
                 multihop_enabled=False,       # old instant relay via a UAV geometrically between the endpoints
                 forwarding_enabled=True,      # store-carry-forward: UAVs relay alerts they hold when they meet a recipient
                 buffer_cap=None,              # max buffered alert copies per UAV (None = unlimited)
                 # ---- scenario knobs ----------------------------------------------------
                 initial_battery_range=(100.0, 100.0),   # per-UAV start charge ~ U(lo, hi) [%]
                 battery_noise_std=0.0,        # std-dev of battery *measurement* noise [% points]
                 replan_interval=5.0,          # seconds between EW-CVT replans
                 tau_epsilon_ratio=0.02, tau_delta=5.0,
                 # ---- planner -----------------------------------------------------------
                 planner="decentralized",       # 'decentralized' (per-UAV views) or 'centralized' (oracle baseline)
                 beacon_interval=5.0,          # seconds between state beacons (decentralized)
                 lease_slack=60.0,             # seconds past a claim's ETA before its owner is suspected lost
                 out_dir=".", write_logs=True, verbose=True, detector=None):

        random.seed(seed)
        self.seed = seed
        self.rng = random.Random(seed + 1337)
        self.arena_size = arena_size
        self.grid_dim = grid_dim
        self.num_drones = num_drones
        self.conf_thresh = conf_thresh
        self.model_path = model_path
        self.sim_speed_multiplier = sim_speed_multiplier
        self.ewcvt_alpha = float(ewcvt_alpha)
        self.hysteresis_enabled = hysteresis_enabled
        self.failover_enabled = failover_enabled
        self.dynamic_repartition = dynamic_repartition
        self.dtn_enabled = dtn_enabled
        self.multihop_enabled = multihop_enabled
        self.forwarding_enabled = forwarding_enabled and dtn_enabled
        self.buffer_cap = buffer_cap
        self.initial_battery_range = initial_battery_range
        self.battery_noise_std = float(battery_noise_std)
        self.replan_interval = float(replan_interval)
        self.tau_epsilon_ratio = tau_epsilon_ratio
        self.tau_delta = tau_delta
        assert planner in ("decentralized", "centralized")
        self.planner = planner
        self.dec = planner == "decentralized"
        self.beacon_interval = float(beacon_interval)
        self.lease_slack = float(lease_slack)
        self.settle_time = 2.0 * float(beacon_interval)
        self.out_dir = out_dir
        self.write_logs = write_logs
        self.verbose = verbose
        self._detector = detector
        if write_logs or out_dir != ".":
            os.makedirs(out_dir, exist_ok=True)

        bx = float(base_x) if base_x is not None else round(arena_size * 0.05, 1)
        by = float(base_y) if base_y is not None else round(arena_size * 0.05, 1)
        self.base_station = [bx, by]
        self.gcs_loc = {'lat': by / 1.113195e5, 'lon': bx / 1.113195e5}

        self.fail_drone_id = int(fail_drone_id) if fail_drone_id is not None and str(fail_drone_id) != "None" else None
        self.fail_time = float(fail_time) if fail_time is not None else None
        self.failure_triggered = False
        self.failed_uav_info = None

        if verbose:
            print("\n" + "=" * 65)
            print("INITIALIZING AUTONOMOUS SWARM SAR SIMULATION")
            print(f"Swarm Size: {num_drones} UAVs | Arena: {arena_size}m x {arena_size}m ({grid_dim}x{grid_dim} sectors)")
            print(f"Base Station Launch Pad: X={self.base_station[0]}m, Y={self.base_station[1]}m")
            print(f"Detector Weights: {model_path} (Conf Threshold: {conf_thresh})")
            mode_str = "Standard Unweighted CVT (alpha=0.0)" if self.ewcvt_alpha == 0.0 else f"Energy-Weighted CVT (alpha={self.ewcvt_alpha})"
            print(f"Partitioning Metric: {mode_str}")
            print(f"Planner: {planner}" + (f" (beacon {beacon_interval}s, lease slack {lease_slack}s)" if self.dec else " (oracle baseline)"))
            print(f"Switches: hysteresis={hysteresis_enabled} failover={failover_enabled} dynamic={dynamic_repartition} "
                  f"dtn={dtn_enabled} forwarding={self.forwarding_enabled} multihop={multihop_enabled}")
            if self.fail_drone_id is not None:
                print(f"Injected Failure: UAV {self.fail_drone_id} will fail at T={self.fail_time}s")
            print("=" * 65)

        # 1. World
        self.world = SARWorld(arena_width=arena_size, arena_height=arena_size,
                              grid_cols=grid_dim, grid_rows=grid_dim, seed=seed)
        self.world.base_station = self.base_station
        self.ground_truth_path = os.path.join(out_dir, "ground_truth_world.json")
        if write_logs:
            self.world.save_ground_truth(self.ground_truth_path)

        # 2. RF physics
        if arena_size >= 2000.0:
            self.physics_engine = swarm_network.RFPhysicsEngine(tx_power_dbm=33, frequency_ghz=2.4)
        else:
            self.physics_engine = swarm_network.RFPhysicsEngine(tx_power_dbm=30, frequency_ghz=5)

        # 3. Swarm state
        self.owner = {}        # sector_id -> uav_id (current owner of every unscanned sector)
        self.stats_control = {"replan_ticks": 0, "sector_flips": 0, "failover_reassigned": 0,
                              "route_changes": 0, "commits": 0, "rtl_aborts": 0, "energy_crashes": 0}
        self.drones = self._spawn_drones()
        self.suspect_log = []
        self.dup_scans = 0
        self.last_fly_time = 0.0
        self.first_adopt_t = None
        self.ctl_msgs = {"sent": 0, "delivered": 0}

        # 4. Logs
        self.vision_log_file = os.path.join(out_dir, "metrics_vision.csv")
        self.network_log_file = os.path.join(out_dir, "metrics_network.csv")
        self.mission_log_file = os.path.join(out_dir, "metrics_mission.csv")
        if write_logs:
            self._init_csv_logs()

        self.sim_time = 0.0
        self._next_replan = self.replan_interval
        self._next_beacon = self.beacon_interval
        self.msg_counter = 0
        self.ttfd = None
        self.first_victim_id = None
        self.obstacle_mask = True
        self.all_reported_targets = []
        self._reported_target_keys = set()
        self.gcs_known = {}         # target_key -> sim time the GCS (operator) first learned of it
        self.sector_scan_time = {}  # sector_id -> first scan time
        self.last_consensus = 0.0
        self.timeseries = []
        self.makespan = None
        self.network_stats = {"sent": 0, "delivered": 0, "dropped": 0, "buffered": 0,
                              "delivered_late": 0, "lost": 0, "gcs_sent": 0, "gcs_delivered": 0,
                              "forwarded": 0, "dropped_buffer": 0}
        if self.dec:
            self._init_agents()

    # ------------------------------------------------------------------ detector
    @property
    def detector(self):
        if self._detector is None:
            self._detector = RGBTDetector(model_path=self.model_path, conf_thresh=self.conf_thresh, device="cpu")
        return self._detector

    def _detect(self, img_path):
        key = (os.path.basename(self.model_path), img_path, round(float(self.conf_thresh), 4))
        hit = _DET_CACHE.get(key)
        if hit is None:
            t0 = time.time()
            dets, frame = self.detector.detect(img_path, conf=self.conf_thresh)
            hit = {"dets": dets, "h": int(frame.shape[0]), "w": int(frame.shape[1]),
                   "lat": (time.time() - t0) * 1000}
            _DET_CACHE[key] = hit
        return hit

    # ------------------------------------------------------------------ logs
    def _init_csv_logs(self):
        with open(self.vision_log_file, "w", newline="") as f:
            csv.writer(f).writerow(["sim_time", "uav_id", "sector_id", "image_file", "targets_found", "class_name", "conf", "world_x", "world_y", "latency_ms"])
        with open(self.network_log_file, "w", newline="") as f:
            csv.writer(f).writerow(["sim_time", "src_uav", "dst_uav", "topic", "msg_id", "distance_m", "snr_db", "per", "delivered", "buffered"])
        with open(self.mission_log_file, "w", newline="") as f:
            csv.writer(f).writerow(["sim_time", "area_covered_pct", "unique_targets_found", "total_alert_broadcasts", "avg_consensus_ratio", "min_peer_dist_m"])

    def _log(self, path, row):
        if self.write_logs:
            with open(path, "a", newline="") as f:
                csv.writer(f).writerow(row)

    # ------------------------------------------------------------------ partitioning
    def _anchors(self):
        n, a = self.num_drones, self.arena_size
        if n == 1:
            return np.array([[a / 2.0, a / 2.0]])
        if n <= 4:
            off = a * 0.25
            return np.array([[off, off], [a - off, off], [off, a - off], [a - off, a - off]])[:n]
        c, r = a / 2.0, a * 0.35
        ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
        return np.array([[c + r * np.cos(t), c + r * np.sin(t)] for t in ang])

    def _assign_by_power_distance(self, sector_ids, gens, weights):
        """owner[s] = argmin_i ||c_s - g_i||^2 / max(0.01, w_i)."""
        out = {}
        for s in sector_ids:
            cx, cy = self.world.sectors[s]["center"]
            best, best_id = float("inf"), None
            for uid, (gx, gy) in gens.items():
                d = ((cx - gx) ** 2 + (cy - gy) ** 2) / max(0.01, weights[uid])
                if d < best:
                    best, best_id = d, uid
            out[s] = best_id
        return out

    def _build_route(self, drone):
        """Greedy nearest-neighbour tour over the UAV's pending sectors, then return to its pad."""
        remaining = list(drone.pending)
        cx, cy = drone.x, drone.y
        wps = []
        while remaining:
            s = min(remaining, key=lambda k: math.hypot(cx - self.world.sectors[k]["center"][0],
                                                        cy - self.world.sectors[k]["center"][1]))
            remaining.remove(s)
            cx, cy = self.world.sectors[s]["center"]
            wps.append((cx, cy))
        wps.append((drone.home_x, drone.home_y))
        drone.set_waypoints(wps)

    def _spawn_drones(self):
        n, a = self.num_drones, self.arena_size
        base_x, base_y = self.base_station
        lo, hi = self.initial_battery_range
        batteries = [self.rng.uniform(lo, hi) if hi > lo else float(lo) for _ in range(n)]

        # Initial EW-CVT: Lloyd iterations from the anchor generators with launch-time weights.
        ids = [str(i) for i in range(n)]
        w0 = {ids[i]: (batteries[i] / 100.0) ** self.ewcvt_alpha for i in range(n)}
        gens = {ids[i]: (float(x), float(y)) for i, (x, y) in enumerate(self._anchors())}
        for _ in range(15):
            gens = compute_ew_cvt_centroids(gens, w0, a, a, grid_res=CVT_GRID_RES)
        owner = self._assign_by_power_distance(list(self.world.sectors.keys()), gens, w0)
        self.owner = dict(owner)
        sectors_per = defaultdict(list)
        for s, uid in owner.items():
            sectors_per[uid].append(s)

        transit_speed = min(50.0, 18.0 * max(1.0, a / 600.0))
        search_speed = min(32.0, 12.0 * max(1.0, a / 800.0))

        drones = []
        for i in range(n):
            start_x = base_x + (i % 5) * 12.0
            start_y = base_y + (i // 5) * 12.0
            d = SimulatedUAV(uav_id=i, start_x=start_x, start_y=start_y, altitude=25.0,
                             transit_speed=transit_speed, search_speed=search_speed,
                             assigned_sectors=sectors_per[ids[i]], physics_engine=self.physics_engine,
                             initial_topology=ids, ewcvt_alpha=self.ewcvt_alpha,
                             initial_battery=batteries[i], tau_epsilon_ratio=self.tau_epsilon_ratio,
                             tau_delta=self.tau_delta)
            d.reset_hysteresis(gens[ids[i]], ids)     # baseline = converged EW-CVT generator
            d.weight = w0[ids[i]]
            self._build_route(d)
            for j in range(n):
                if j != i:
                    d.broker.update_neighbor_subscription(str(j), set(["telemetry", "target_alert"]))
            drones.append(d)
        return drones

    def _replan(self, reason="periodic"):
        """One EW-CVT control tick (see module docstring)."""
        alive = [d for d in self.drones if d.is_alive and not d.rtl]
        flying = [d for d in alive if d.state != "LANDED"]
        if not flying:
            return
        self.stats_control["replan_ticks"] += 1
        alive_ids = tuple(sorted(d.uav_id for d in alive))

        for d in flying:
            d.b_meas = max(0.0, min(100.0, d.battery + self.rng.gauss(0.0, self.battery_noise_std)))
        fresh_w = {d.uav_id: (d.b_meas / d.battery_max) ** self.ewcvt_alpha for d in flying}
        gens = {d.uav_id: d.gen for d in flying}
        c_star = compute_ew_cvt_centroids(gens, fresh_w, self.arena_size, self.arena_size, grid_res=CVT_GRID_RES)

        for d in flying:
            if self.hysteresis_enabled:
                res = d.hysteresis.evaluate(self.sim_time, d.b_meas, c_star[d.uav_id], alive_ids, d.speed)
                if res["trigger_u_t"]:
                    self.stats_control["commits"] += 1
                d.gen = tuple(res["commanded_pos"])
                d.weight = res["effective_weight"]
            else:
                d.gen = tuple(c_star[d.uav_id])
                d.weight = fresh_w[d.uav_id]
                self.stats_control["commits"] += 1

        scanned = set().union(*[x.scanned_sectors for x in self.drones])
        dead_ids = {d.uav_id for d in self.drones if (not d.is_alive) or d.rtl}
        pool = [s for s in self.world.sectors if s not in scanned]
        if not self.failover_enabled:
            pool = [s for s in pool if self.owner.get(s) not in dead_ids]   # lost sectors stay lost
        new_owner = self._assign_by_power_distance(pool, {d.uav_id: d.gen for d in flying},
                                                   {d.uav_id: d.weight for d in flying})
        for s in pool:
            old, new = self.owner.get(s), new_owner[s]
            if old != new:
                if old in dead_ids:
                    self.stats_control["failover_reassigned"] += 1
                elif old is not None:
                    self.stats_control["sector_flips"] += 1
        self.owner.update(new_owner)

        for d in flying:
            pend = [s for s in pool if new_owner[s] == d.uav_id]
            if set(pend) != set(d.pending):
                d.pending = pend
                d.assigned_sectors = sorted(set(d.scanned_sectors) | set(pend))
                d.route_changes += 1
                self.stats_control["route_changes"] += 1
                self._build_route(d)

    # ------------------------------------------------------------------ decentralized planner
    def _etas(self, d):
        """Planned arrival time of each pending sector along the UAV's current route."""
        t, x, y, out = self.sim_time, d.x, d.y, {}
        for k in range(d.current_waypoint_idx, len(d.waypoints) - 1):
            wx, wy = d.waypoints[k]
            sp = d.transit_speed if (k == d.current_waypoint_idx and not d.reached_first_sector) else d.search_speed
            t += math.hypot(wx - x, wy - y) / sp
            x, y = wx, wy
            sec = self.world.get_sector_at(wx, wy)
            if sec is not None:
                out[sec["sector_id"]] = round(t, 1)
        return out

    def _return_eta(self, d):
        """When the current route should bring the UAV back to its pad."""
        if d.current_waypoint_idx >= len(d.waypoints):
            return None
        t, x, y = self.sim_time, d.x, d.y
        for k in range(d.current_waypoint_idx, len(d.waypoints)):
            wx, wy = d.waypoints[k]
            last = k == len(d.waypoints) - 1
            sp = d.transit_speed if (last or (k == d.current_waypoint_idx and not d.reached_first_sector)) else d.search_speed
            t += math.hypot(wx - x, wy - y) / sp
            x, y = wx, wy
        return round(t, 1)

    def _refresh_claims(self, d):
        """Rebuild the UAV's own claim list with fresh ETAs for the sectors it will still visit."""
        etas = self._etas(d)
        d.agent.mine = {s: etas.get(s) for s in d.pending}

    def _init_agents(self):
        ids = [d.uav_id for d in self.drones]
        centers = {s: tuple(v["center"]) for s, v in self.world.sectors.items()}
        for d in self.drones:
            d.agent = SwarmAgent(d.uav_id, ids, centers, failover=self.failover_enabled)
        for d in self.drones:
            self._refresh_claims(d)
        # Pre-flight sync on the pad: all UAVs are co-located at launch, so they start with the
        # same view (the shared initial partition and everyone's launch claims).
        for d in self.drones:
            for o in self.drones:
                if o is d:
                    continue
                d.agent.peers[o.uav_id].update(x=o.x, y=o.y, gen=o.gen, w=o.weight, state="TRANSIT",
                                               ret=self._return_eta(o), heard=0.0)
                d.agent.peer_claims[o.uav_id] = dict(o.agent.mine)

    def _agent_state(self, d):
        return "RTL" if d.rtl else d.state

    def _exchange_beacons(self):
        """Every UAV broadcasts its beacon; each copy survives the RF link with probability 1-PER."""
        live = [d for d in self.drones if d.is_alive]
        beacons = {}
        for d in live:
            if not d.rtl and d.state != "LANDED":
                self._refresh_claims(d)
            beacons[d.uav_id] = d.agent.beacon(d.x, d.y, d.gen, d.weight, self._agent_state(d), self._return_eta(d))
        pe = self.physics_engine
        for src in live:
            for dst in live:
                if dst is src:
                    continue
                self.ctl_msgs["sent"] += 1
                _, per = pe.calculate_snr_per(src.get_location_dict(), dst.get_location_dict(), self.obstacle_mask)
                if random.random() >= per:
                    self.ctl_msgs["delivered"] += 1
                    dst.agent.receive(beacons[src.uav_id], self.sim_time)

    def _replan_decentralized(self):
        """Each UAV plans from its own view only: expire leases, EW-CVT over the peers it believes
        are active, hysteresis gate, then claim sectors (yield to better claims, steal when idle)."""
        self.stats_control["replan_ticks"] += 1
        for d in self.drones:
            if not d.is_alive or d.rtl:
                continue
            ag = d.agent
            for j in ag.expire(self.sim_time, self.lease_slack):
                truly = not next(x for x in self.drones if x.uav_id == j).is_alive
                self.suspect_log.append({"t": round(self.sim_time, 1), "observer": d.uav_id,
                                         "suspect": j, "truly_dead": truly})
            landed = d.state == "LANDED"
            if landed and (d.battery <= BATTERY_RESERVE_PCT + 5.0 or
                           self.sim_time - d.landed_since < self.settle_time):
                continue          # on the pad: listen for peers' beacons before deciding to relaunch
            peers = ag.active_peers(include_landed=landed)
            alive_ids = tuple(sorted([d.uav_id] + peers))
            d.b_meas = max(0.0, min(100.0, d.battery + self.rng.gauss(0.0, self.battery_noise_std)))
            if self.dynamic_repartition:
                gens = {d.uav_id: d.gen}
                weights = {d.uav_id: (d.b_meas / d.battery_max) ** self.ewcvt_alpha}
                for j in peers:
                    gens[j], weights[j] = ag.peers[j]["gen"], ag.peers[j]["w"]
                c_star = compute_ew_cvt_centroids(gens, weights, self.arena_size, self.arena_size,
                                                  grid_res=CVT_GRID_RES)[d.uav_id]
                if self.hysteresis_enabled:
                    res = d.hysteresis.evaluate(self.sim_time, d.b_meas, c_star, alive_ids, d.speed)
                    if res["trigger_u_t"]:
                        self.stats_control["commits"] += 1
                    d.gen, d.weight = tuple(res["commanded_pos"]), res["effective_weight"]
                else:
                    d.gen, d.weight = tuple(c_star), weights[d.uav_id]
                    self.stats_control["commits"] += 1
            before = dict(ag.stats)
            etas = self._etas(d)
            if d.pending and etas:
                end_pos, end_eta = d.waypoints[len(d.waypoints) - 2], max(v for v in etas.values())
            else:
                end_pos, end_eta = (d.x, d.y), self.sim_time
            speed = d.search_speed
            was = set(ag.mine)
            new = ag.assign((d.x, d.y), d.gen, d.weight, speed, end_pos, end_eta, at_base=landed)
            if self.failed_uav_info and self.first_adopt_t is None and \
                    (set(new) - was) & set(self.failed_uav_info["abandoned_sectors"]):
                self.first_adopt_t = round(self.sim_time, 1)
            self.stats_control["sector_flips"] += ag.stats["yields"] - before["yields"]
            self.stats_control["failover_reassigned"] += ag.stats["adopted"] - before["adopted"]
            if landed and not new:
                continue
            if set(new) != set(d.pending):
                d.pending = list(new)
                d.assigned_sectors = sorted(set(d.scanned_sectors) | set(d.pending))
                d.route_changes += 1
                self.stats_control["route_changes"] += 1
                self._build_route(d)
                if landed:
                    d.reached_first_sector = False
                    d.relaunches += 1
            self._refresh_claims(d)

    # ------------------------------------------------------------------ networking
    def _try_deliver(self, src, dst_id, dst_loc):
        """One radio attempt src -> dst (optionally via the old instant geometric relay)."""
        pe = self.physics_engine
        my_loc = src.get_location_dict()
        dist_m = pe.calculate_euclidean_distance(my_loc, dst_loc)
        snr, per = pe.calculate_snr_per(my_loc, dst_loc, self.obstacle_mask)
        delivered = (random.random() >= per)
        if not delivered and self.multihop_enabled:
            for relay in self.drones:
                if not relay.is_alive or relay.uav_id in (src.uav_id, dst_id):
                    continue
                rl = relay.get_location_dict()
                d1 = pe.calculate_euclidean_distance(my_loc, rl)
                d2 = pe.calculate_euclidean_distance(rl, dst_loc)
                if d1 < dist_m and d2 < dist_m:
                    _, p1 = pe.calculate_snr_per(my_loc, rl, self.obstacle_mask)
                    _, p2 = pe.calculate_snr_per(rl, dst_loc, self.obstacle_mask)
                    if (random.random() >= p1) and (random.random() >= p2):
                        delivered = True
                        break
        peer = next((d for d in self.drones if d.uav_id == dst_id), None)
        if peer is not None and not peer.is_alive:
            delivered = False                      # a dead UAV receives nothing (the sender cannot know)
        return delivered, dist_m, snr, per

    @staticmethod
    def _holds(d, key):
        return key in d.discovered_targets or key in d.consensus_registry

    def _queue_copy(self, drone, rid, key, rec, msg_id):
        """Put one alert copy for `rid` into this UAV's store-and-forward buffer (bounded)."""
        drone.broker.qos1_buffers[rid].append({
            "topic": "target_alert", "message_id": msg_id, "timestamp": self.sim_time,
            "payload": f"{key}:{rec['class_name']}:{rec['conf']}:{rec['world_x']}:{rec['world_y']}"})
        if self.buffer_cap is not None:
            while sum(len(b) for b in drone.broker.qos1_buffers.values()) > self.buffer_cap:
                oldest = min((b for b in drone.broker.qos1_buffers.values() if b), key=lambda b: b[0]["timestamp"])
                oldest.popleft()
                self.network_stats["dropped_buffer"] += 1

    def _all_recipients(self, me):
        return [d.uav_id for d in self.drones if d.uav_id != me.uav_id] + [GCS_ID]

    def _receive_alert(self, src, rid, key, rec):
        """`rid` has just received alert `key` from `src` (directly or from src's buffer)."""
        src.fwd_known[key].add(rid)
        if rid == GCS_ID:
            self.gcs_known.setdefault(key, self.sim_time)
            return
        peer = next((d for d in self.drones if d.uav_id == rid), None)
        if peer is None or not peer.is_alive or self._holds(peer, key):
            return
        peer.consensus_registry[key] = rec
        peer.fwd_known[key] |= {src.uav_id, peer.uav_id} | src.fwd_known[key]
        if src.uav_id != rec["detected_by"]:
            self.network_stats["forwarded"] += 1
        if self.forwarding_enabled:
            # store-carry-forward: the receiver now carries the alert for everyone not known to hold it
            for r in self._all_recipients(peer):
                if r not in peer.fwd_known[key]:
                    self._queue_copy(peer, r, key, rec, f"FWD_{key}_{peer.uav_id}")

    def _broadcast_alert(self, drone, target_key, det, wx, wy):
        msg_id = f"ALERT_U{drone.uav_id}_{self.msg_counter}"
        self.msg_counter += 1
        record = drone.discovered_targets[target_key]
        drone.fwd_known[target_key].add(drone.uav_id)
        for rid in self._all_recipients(drone):
            is_gcs = rid == GCS_ID
            rloc = self.gcs_loc if is_gcs else next(d for d in self.drones if d.uav_id == rid).get_location_dict()
            self.network_stats["gcs_sent" if is_gcs else "sent"] += 1
            delivered, dist_m, snr, per = self._try_deliver(drone, rid, rloc)
            buffered = (not delivered) and self.dtn_enabled
            if delivered:
                self.network_stats["gcs_delivered" if is_gcs else "delivered"] += 1
                self._receive_alert(drone, rid, target_key, record)
            else:
                if not is_gcs:
                    self.network_stats["dropped"] += 1
                if buffered:
                    if not is_gcs:
                        self.network_stats["buffered"] += 1
                    self._queue_copy(drone, rid, target_key, record, msg_id)
                else:
                    self.network_stats["lost"] += 1
            self._log(self.network_log_file, [round(self.sim_time, 2), drone.uav_id, rid, "target_alert", msg_id,
                                              round(dist_m, 2), round(snr, 2), round(per, 3), int(delivered), int(buffered)])

    def _flush_buffers(self, swarm_locations):
        """When the link to a recipient is good, hand over every buffered copy it does not already hold."""
        locs = dict(swarm_locations)
        locs[GCS_ID] = self.gcs_loc
        for drone in self.drones:
            if not drone.is_alive:
                continue
            flushed = drone.broker.flush_buffers_detailed(drone.get_location_dict(), locs, self.obstacle_mask)
            for nid, msgs in flushed.items():
                for m in msgs:
                    key = m["payload"].split(":")[0]
                    rec = drone.discovered_targets.get(key) or drone.consensus_registry.get(key)
                    if rec is None:
                        continue
                    if nid == GCS_ID:
                        if key in self.gcs_known:
                            continue                        # already told (by another UAV)
                    else:
                        peer = next((d for d in self.drones if d.uav_id == nid), None)
                        if peer is None or not peer.is_alive or self._holds(peer, key):
                            drone.fwd_known[key].add(nid)
                            continue
                    self.network_stats["delivered_late"] += 1
                    self._receive_alert(drone, nid, key, rec)

    # ------------------------------------------------------------------ vision
    def _scan_sector(self, drone, sec):
        sid = sec["sector_id"]
        if sid in self.sector_scan_time:
            self.dup_scans += 1
        drone.scanned_sectors.add(sid)
        if drone.agent is not None:
            drone.agent.mark_scanned(sid)
        if sid in drone.pending:
            drone.pending.remove(sid)
        self.sector_scan_time.setdefault(sid, self.sim_time)

        hit = self._detect(sec["image_path"])
        detections, img_w, img_h = hit["dets"], float(hit["w"]), float(hit["h"])
        xmin, xmax, ymin, ymax = sec["bounds"]
        for det in detections:
            if self.ttfd is None:
                self.ttfd = round(self.sim_time, 2)
                if self.verbose:
                    print(f"[TTFD] First target at {self.ttfd}s by UAV {drone.uav_id}")
            x1, y1, x2, y2 = det["box"]
            wx = round(xmin + (((x1 + x2) / 2.0) / img_w) * (xmax - xmin), 2)
            wy = round(ymin + (((y1 + y2) / 2.0) / img_h) * (ymax - ymin), 2)
            key = f"TGT_{sid}_{round(wx, 1)}_{round(wy, 1)}"
            self._log(self.vision_log_file, [round(self.sim_time, 2), drone.uav_id, sid,
                                             os.path.basename(sec["image_path"]), len(detections), det["class_name"],
                                             det["conf"], wx, wy, round(hit["lat"], 2)])
            if key not in drone.discovered_targets:
                drone.discovered_targets[key] = {
                    "target_key": key, "class_name": det["class_name"], "conf": det["conf"],
                    "world_x": wx, "world_y": wy, "sector_id": sid,
                    "detected_by": drone.uav_id, "time": round(self.sim_time, 2)}
                # Swarm-wide dedup: several UAVs can discover the same victim; the mission-level
                # report lists each unique target once.
                if key not in self._reported_target_keys:
                    self._reported_target_keys.add(key)
                    self.all_reported_targets.append(drone.discovered_targets[key])
                self._broadcast_alert(drone, key, det, wx, wy)

    # ------------------------------------------------------------------ main loop
    def _kill(self, dead, injected=True):
        """UAV loss (injected motor failure, or battery depletion)."""
        dead.is_alive = False
        dead.state = "CRASHED"
        dead.crash_pos = (round(dead.x, 2), round(dead.y, 2))
        abandoned = list(dead.pending)
        if injected:
            self.failed_uav_info = {"uav_id": dead.uav_id, "crash_pos": dead.crash_pos,
                                    "time": round(self.sim_time, 2), "abandoned_sectors": abandoned}
        else:
            self.stats_control["energy_crashes"] += 1
        if self.verbose:
            print("\n" + "=" * 55)
            print(f"[{'FAILURE EVENT' if injected else 'BATTERY DEPLETED'}] UAV {dead.uav_id} lost at T={self.sim_time:.1f}s")
            print(f"Crash location: ({dead.crash_pos[0]:.1f}m, {dead.crash_pos[1]:.1f}m)")
            print(f"Abandoned sectors: {abandoned} | failover={'ON' if self.failover_enabled else 'OFF'}")
            print("=" * 55 + "\n")
        dead.pending = []
        if self.failover_enabled and not self.dec:
            self._replan("failover")     # topology change => controllers take a forced override

    def _trigger_failure(self):
        self.failure_triggered = True
        dead = next((d for d in self.drones if str(d.uav_id) == str(self.fail_drone_id)), None)
        if dead and dead.is_alive:
            self._kill(dead, injected=True)

    def _check_energy(self, drone):
        """Reserve rule: at <=15% a UAV aborts and returns to base; at 0% it is lost."""
        if drone.battery <= 0.0:
            self._kill(drone, injected=False)
            return
        if not drone.rtl and drone.state != "LANDED" and drone.battery <= BATTERY_RESERVE_PCT:
            drone.rtl = True
            self.stats_control["rtl_aborts"] += 1
            drone.pending = []
            self._build_route(drone)     # route = [home]
            if drone.agent is not None:
                drone.agent.mine = {}
            if self.failover_enabled and not self.dec:
                self._replan("low_battery")

    def step(self, dt=1.0):
        self.sim_time += dt
        all_done = True

        if self.fail_drone_id is not None and not self.failure_triggered and self.sim_time >= self.fail_time:
            self._trigger_failure()

        if self.dec:
            if self.sim_time >= self._next_beacon:
                self._next_beacon += self.beacon_interval
                self._exchange_beacons()
            if self.sim_time >= self._next_replan:
                self._next_replan += self.replan_interval
                self._replan_decentralized()
        elif self.dynamic_repartition and self.sim_time >= self._next_replan:
            self._next_replan += self.replan_interval
            self._replan("periodic")

        swarm_locations = {d.uav_id: d.get_location_dict() for d in self.drones if d.is_alive}
        for drone in self.drones:
            if not drone.is_alive:
                continue
            self._check_energy(drone)
            if not drone.is_alive:
                continue
            if not drone.update_position(dt, current_time=self.sim_time):
                all_done = False
                self.last_fly_time = self.sim_time
            if drone.state == "LANDED":
                if drone.landed_since is None:
                    drone.landed_since = self.sim_time
            else:
                drone.landed_since = None
            if drone.arrived_at_sector:
                drone.arrived_at_sector = False
                sec = self.world.get_sector_at(drone.x, drone.y)
                if sec is not None:
                    self._scan_sector(drone, sec)

        self._flush_buffers(swarm_locations)

        total_sectors = self.grid_dim * self.grid_dim
        all_scanned = set().union(*[d.scanned_sectors for d in self.drones])
        coverage_pct = round((len(all_scanned) / total_sectors) * 100.0, 1)

        active = [d for d in self.drones if d.is_alive]
        uniq = set().union(*[set(d.discovered_targets.keys()) for d in self.drones])
        if uniq and active:
            scores = [sum(1 for d in active if (t in d.discovered_targets or t in d.consensus_registry)) / len(active)
                      for t in uniq]
            avg_consensus = round(float(np.mean(scores)), 3)
        else:
            avg_consensus = 0.0
        self.last_consensus = avg_consensus

        min_dist = float("inf")
        for i in range(len(active)):
            for j in range(i + 1, len(active)):
                min_dist = min(min_dist, math.hypot(active[i].x - active[j].x, active[i].y - active[j].y))
        if min_dist == float("inf"):
            min_dist = 0.0

        self._log(self.mission_log_file, [round(self.sim_time, 2), coverage_pct, len(uniq),
                                          self.msg_counter, avg_consensus, round(min_dist, 2)])
        self.timeseries.append({"t": self.sim_time, "coverage": coverage_pct, "targets": len(uniq),
                                "gcs_known": len(self.gcs_known), "consensus": avg_consensus})
        if self.dec and all_done and coverage_pct < 100.0 and \
                (self.sim_time - self.last_fly_time) < (self.lease_slack + 30.0) and \
                any(d.is_alive and not d.rtl and d.battery > BATTERY_RESERVE_PCT + 5.0 for d in self.drones):
            all_done = False          # leftover sectors: wait for leases to expire and UAVs to take them
        if all_done and self.makespan is None:
            self.makespan = self.last_fly_time + 1.0 if self.dec else self.sim_time

        return {
            "sim_time": self.sim_time, "coverage_pct": coverage_pct, "targets_count": len(uniq),
            "targets": list(self.all_reported_targets), "avg_consensus": avg_consensus,
            "active_drones": len(active), "drones": self.drones, "base_station": self.base_station,
            "arena_size": self.arena_size, "failed_uav_info": self.failed_uav_info, "all_done": all_done
        }

    def run_streaming(self, max_sim_seconds=300, dt=1.0, yield_interval=8):
        if self.verbose:
            print(f"\nSTARTING SWARM SEARCH MISSION (Simulated Time: {max_sim_seconds}s, step: {dt}s)...")
        last_yield_time = 0.0
        while self.sim_time < max_sim_seconds:
            snap = self.step(dt)
            if (self.sim_time - last_yield_time) >= yield_interval or snap["all_done"]:
                last_yield_time = self.sim_time
                yield snap
            if snap["all_done"]:
                if self.verbose:
                    print(f"\nAll drones completed their search patterns at T={self.sim_time:.1f}s!")
                break
        if self.write_logs:
            self._export_mission_output()
        total_sectors = self.grid_dim * self.grid_dim
        all_scanned = set().union(*[d.scanned_sectors for d in self.drones])
        yield {
            "sim_time": self.sim_time,
            "coverage_pct": round((len(all_scanned) / total_sectors) * 100.0, 1),
            "targets_count": len(self.all_reported_targets),
            "targets": list(self.all_reported_targets),
            "avg_consensus": self.last_consensus,
            "active_drones": len([d for d in self.drones if d.is_alive]),
            "drones": self.drones, "base_station": self.base_station, "arena_size": self.arena_size,
            "failed_uav_info": self.failed_uav_info, "all_done": True
        }

    def run(self, max_sim_seconds=300, dt=1.0):
        for snap in self.run_streaming(max_sim_seconds=max_sim_seconds, dt=dt, yield_interval=20):
            print(f"[T={snap['sim_time']:.0f}s] Area Coverage: {snap['coverage_pct']}% | Targets: {snap['targets_count']} | Consensus: {snap['avg_consensus']*100:.1f}%")

    # ------------------------------------------------------------------ metrics
    def _energy_summary(self):
        active = [d for d in self.drones if d.is_alive]
        if not active:
            return {}
        b = [float(d.battery) for d in active]
        n = len(b)
        sb, sb2 = sum(b), sum(x * x for x in b)
        return {
            "alpha": self.ewcvt_alpha,
            "mode": "Standard CVT (Unweighted)" if self.ewcvt_alpha == 0.0 else f"Energy-Weighted CVT (alpha={self.ewcvt_alpha})",
            "jains_energy_fairness_index": round((sb ** 2) / (n * sb2), 4) if sb2 > 0 else 1.0,
            "battery_spread_delta_pct": round(max(b) - min(b), 2),
            "battery_std_pct": round(float(np.std(b)), 2),
            "battery_variance_pct2": round(float(np.var(b)), 2),
            "min_remaining_battery_pct": round(min(b), 2),
            "max_remaining_battery_pct": round(max(b), 2),
            "mean_remaining_battery_pct": round(float(np.mean(b)), 2),
            "fleet_endurance_safety_margin_pct": round(min(b) - BATTERY_RESERVE_PCT, 2),
            "active_uav_count": n,
        }

    def _detect_delay(self):
        """Seconds from the injected failure until some UAV first suspected the failed one."""
        if not self.failed_uav_info:
            return None
        ts = [e["t"] for e in self.suspect_log if e["suspect"] == self.failed_uav_info["uav_id"] and e["truly_dead"]]
        return round(min(ts) - self.failed_uav_info["time"], 1) if ts else None

    def collect_metrics(self, match_radius_m=15.0):
        """Single flat dict of every measured quantity (used by the ablation harness)."""
        W = self.world
        gt = list(W.ground_truth_victims)
        reports = list(self.all_reported_targets)
        scanned = set().union(*[d.scanned_sectors for d in self.drones])

        def match(rep_list, gt_list):
            pairs = []
            for gi, g in enumerate(gt_list):
                for ri, r in enumerate(rep_list):
                    d = math.hypot(g["world_x"] - r["world_x"], g["world_y"] - r["world_y"])
                    if d <= match_radius_m:
                        pairs.append((d, gi, ri))
            pairs.sort()
            ug, ur, errs = set(), set(), []
            for d, gi, ri in pairs:
                if gi in ug or ri in ur:
                    continue
                ug.add(gi); ur.add(ri); errs.append(d)
            return len(errs), errs

        gt_surveyed = [g for g in gt if g["sector_id"] in scanned]
        tp, errs = match(reports, gt)
        fp = len(reports) - tp
        op_reports = [r for r in reports if r["target_key"] in self.gcs_known]
        op_tp, _ = match(op_reports, gt)

        lat = [self.gcs_known[r["target_key"]] - r["time"] for r in op_reports]
        ts = self.timeseries

        def t_reach(field, thr):
            for row in ts:
                if row[field] >= thr:
                    return row["t"]
            return None

        active = [d for d in self.drones if d.is_alive]
        init_b = {d.uav_id: d.initial_battery for d in self.drones}
        used = [init_b[d.uav_id] - d.battery for d in active]
        en = self._energy_summary()
        viol = sum(1 for d in active if d.battery < BATTERY_RESERVE_PCT)
        n_total = len(gt)
        sent_p, deliv_p = self.network_stats["sent"], self.network_stats["delivered"]
        gs, gd = self.network_stats["gcs_sent"], self.network_stats["gcs_delivered"]
        hys_updates = sum(d.hysteresis.updates_executed for d in self.drones)
        forced = sum(d.hysteresis.forced_overrides for d in self.drones)
        n_alerts = len(reports)
        return {
            # --- mission ---
            "coverage_pct": round(len(scanned) / (self.grid_dim ** 2) * 100.0, 2),
            "makespan_s": self.makespan if self.makespan is not None else self.sim_time,
            "completed": self.makespan is not None,
            "t_cov50_s": t_reach("coverage", 50.0), "t_cov90_s": t_reach("coverage", 90.0),
            "t_cov100_s": t_reach("coverage", 100.0),
            "ttfd_s": self.ttfd,
            "total_distance_km": round(sum(d.total_distance_flown for d in self.drones) / 1000.0, 2),
            "sectors_lost": self.grid_dim ** 2 - len(scanned),
            # --- detection (end-to-end) ---
            "gt_total": n_total, "reports": n_alerts, "tp": tp, "fp": fp,
            "precision": round(tp / n_alerts, 4) if n_alerts else 0.0,
            "recall_arena": round(tp / n_total, 4) if n_total else 0.0,
            "recall_surveyed": round(tp / len(gt_surveyed), 4) if gt_surveyed else 0.0,
            "f1_arena": round(2 * (tp / n_alerts) * (tp / n_total) / ((tp / n_alerts) + (tp / n_total)), 4)
                        if tp and n_alerts and n_total else 0.0,
            "loc_err_mean_m": round(float(np.mean(errs)), 3) if errs else None,
            "loc_err_rmse_m": round(float(np.sqrt(np.mean(np.square(errs)))), 3) if errs else None,
            # --- operator (GCS) view ---
            "operator_recall": round(op_tp / n_total, 4) if n_total else 0.0,
            "operator_known_frac": round(len(op_reports) / n_alerts, 4) if n_alerts else 0.0,
            "alert_latency_mean_s": round(float(np.mean(lat)), 1) if lat else None,
            "alert_latency_max_s": round(float(np.max(lat)), 1) if lat else None,
            # --- network ---
            "pdr_first_attempt": round(deliv_p / sent_p, 4) if sent_p else None,
            "gcs_pdr_first_attempt": round(gd / gs, 4) if gs else None,
            "consensus_final": self.last_consensus,
            "msgs_sent": sent_p + gs, "msgs_lost_forever": self.network_stats["lost"],
            "msgs_delivered_late": self.network_stats["delivered_late"],
            "alerts_forwarded": self.network_stats["forwarded"], "buffer_drops": self.network_stats["dropped_buffer"],
            # --- energy ---
            "batt_min_pct": en.get("min_remaining_battery_pct"),
            "batt_mean_pct": en.get("mean_remaining_battery_pct"),
            "batt_spread_pct": en.get("battery_spread_delta_pct"),
            "jain_fairness": en.get("jains_energy_fairness_index"),
            "reserve_violations": viol,
            "energy_used_mean_pct": round(float(np.mean(used)), 2) if used else None,
            "energy_used_max_pct": round(float(np.max(used)), 2) if used else None,
            # --- control stability ---
            "replan_ticks": self.stats_control["replan_ticks"],
            "partition_commits": self.stats_control["commits"],
            "sector_flips": self.stats_control["sector_flips"],
            "route_changes": self.stats_control["route_changes"],
            "failover_reassigned": self.stats_control["failover_reassigned"],
            "hysteresis_updates": hys_updates, "forced_overrides": forced,
            "uavs_lost": len(self.drones) - len(active),
            "rtl_aborts": self.stats_control["rtl_aborts"], "energy_crashes": self.stats_control["energy_crashes"],
            # --- decentralized planner ---
            "duplicate_scans": self.dup_scans,
            "suspicions": len(self.suspect_log),
            "false_suspicions": sum(1 for e in self.suspect_log if not e["truly_dead"]),
            "failure_detect_delay_s": self._detect_delay(),
            "failover_latency_s": (round(self.first_adopt_t - self.failed_uav_info["time"], 1)
                                   if self.first_adopt_t is not None and self.failed_uav_info else None),
            "ctl_msgs_sent": self.ctl_msgs["sent"], "ctl_msgs_delivered": self.ctl_msgs["delivered"],
            "relaunches": sum(d.relaunches for d in self.drones),
        }

    def _export_mission_output(self):
        ewcvt_summary = self._energy_summary()
        output = {
            "mission_duration_sec": round(self.sim_time, 2),
            "ttfd_sec": self.ttfd,
            "swarm_size": self.num_drones,
            "arena_size": self.arena_size,
            "ewcvt_alpha": self.ewcvt_alpha,
            "ewcvt_summary": ewcvt_summary,
            "base_station": self.base_station,
            "failed_uav_info": self.failed_uav_info,
            "network_stats": self.network_stats,
            "control_stats": self.stats_control,
            "drones": [
                {
                    "uav_id": d.uav_id, "is_alive": d.is_alive, "crash_pos": d.crash_pos,
                    "initial_battery_pct": round(d.initial_battery, 2),
                    "remaining_battery_pct": round(d.battery, 2),
                    "total_distance_m": round(d.total_distance_flown, 2),
                    "sectors_scanned": list(d.scanned_sectors),
                    "targets_discovered_count": len(d.discovered_targets),
                    "consensus_targets_count": len(d.consensus_registry),
                    "hysteresis_metrics": d.hysteresis.get_status_summary(),
                    "trajectory": d.trajectory_history[::5]
                }
                for d in self.drones
            ],
            "hysteresis_summary": {
                "total_chattering_events_suppressed": sum(d.hysteresis.chattering_events_suppressed for d in self.drones),
                "total_forced_overrides": sum(d.hysteresis.forced_overrides for d in self.drones),
                "total_energy_saved_joules": round(sum(d.hysteresis.cumulative_energy_saved_joules for d in self.drones), 2)
            },
            "reported_targets": self.all_reported_targets
        }
        with open(os.path.join(self.out_dir, "swarm_mission_output.json"), "w") as f:
            json.dump(output, f, indent=2)

        if self.verbose:
            print("\n" + "=" * 65)
            print("MISSION COMPLETED & EXPORTED")
            print(f"Summary saved to: {os.path.join(self.out_dir, 'swarm_mission_output.json')}")
            if ewcvt_summary:
                print("=" * 65)
                print("EW-CVT ENERGY BALANCE & WORKLOAD EQUILIBRIUM")
                print("=" * 65)
                print(f"EW-CVT Metric:                  {ewcvt_summary['mode']}")
                print(f"Jain's Energy Fairness Index:   {ewcvt_summary['jains_energy_fairness_index']:.4f} / 1.0000")
                print(f"Fleet Battery Spread (Delta):   {ewcvt_summary['battery_spread_delta_pct']}% (Min: {ewcvt_summary['min_remaining_battery_pct']}%, Max: {ewcvt_summary['max_remaining_battery_pct']}%)")
                print(f"Fleet Battery Std Dev (sigma):  {ewcvt_summary['battery_std_pct']}%")
                print(f"Fleet Endurance Safety Margin:  +{ewcvt_summary['fleet_endurance_safety_margin_pct']}% (above 15% RTL reserve)")
            print("=" * 65)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Autonomous Swarm SAR Mission Simulator")
    parser.add_argument("--drones", type=int, default=3)
    parser.add_argument("--arena", type=float, default=400.0)
    parser.add_argument("--grid", type=int, default=5)
    parser.add_argument("--model", type=str, default="best.pt")
    parser.add_argument("--conf", type=float, default=0.20)
    parser.add_argument("--duration", type=int, default=180)
    parser.add_argument("--step", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fail-drone", type=int, default=None)
    parser.add_argument("--fail-time", type=float, default=45.0)
    parser.add_argument("--base-x", type=float, default=None)
    parser.add_argument("--base-y", type=float, default=None)
    parser.add_argument("--alpha", "--ewcvt-alpha", type=float, default=1.0, dest="ewcvt_alpha",
                        help="EW-CVT energy exponent (0.0 = standard CVT)")
    parser.add_argument("--no-hysteresis", action="store_true", help="ablate the dual-threshold hysteresis gate")
    parser.add_argument("--no-failover", action="store_true", help="ablate autonomous sector failover")
    parser.add_argument("--static", action="store_true", help="ablate dynamic EW-CVT replanning")
    parser.add_argument("--no-dtn", action="store_true", help="ablate store-and-forward buffering")
    parser.add_argument("--no-forwarding", action="store_true", help="ablate store-carry-forward relaying of received alerts")
    parser.add_argument("--multihop", action="store_true", help="enable the old instant geometric relay")
    parser.add_argument("--buffer-cap", type=int, default=None, help="max buffered alert copies per UAV")
    parser.add_argument("--batt-min", type=float, default=100.0, help="lowest initial battery %% (UAVs start U(min,100))")
    parser.add_argument("--batt-noise", type=float, default=0.0, help="battery measurement noise std-dev (%% points)")
    parser.add_argument("--planner", choices=["decentralized", "centralized"], default="decentralized",
                        help="decentralized: per-UAV views and claims; centralized: oracle baseline")
    parser.add_argument("--beacon-interval", type=float, default=5.0, help="seconds between state beacons")
    parser.add_argument("--lease-slack", type=float, default=60.0, help="seconds past a claim ETA before suspecting its owner")
    parser.add_argument("--out-dir", type=str, default=".")
    args = parser.parse_args()

    sim = SwarmSimulation(num_drones=args.drones, arena_size=args.arena, grid_dim=args.grid,
                          model_path=args.model, conf_thresh=args.conf, seed=args.seed,
                          fail_drone_id=args.fail_drone, fail_time=args.fail_time,
                          base_x=args.base_x, base_y=args.base_y, ewcvt_alpha=args.ewcvt_alpha,
                          hysteresis_enabled=not args.no_hysteresis, failover_enabled=not args.no_failover,
                          dynamic_repartition=not args.static, dtn_enabled=not args.no_dtn,
                          multihop_enabled=args.multihop, forwarding_enabled=not args.no_forwarding, buffer_cap=args.buffer_cap,
                          initial_battery_range=(args.batt_min, 100.0), battery_noise_std=args.batt_noise,
                          planner=args.planner, beacon_interval=args.beacon_interval,
                          lease_slack=args.lease_slack, out_dir=args.out_dir)
    sim.run(max_sim_seconds=args.duration, dt=args.step)
