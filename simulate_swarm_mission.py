#!/usr/bin/env python3
"""
Autonomous Multi-UAV Swarm SAR Simulation Engine.
Runs decentralized drone agents over an in-memory multispectral world, executing:
  - Trajectory navigation & sector search
  - 4-Channel Early-Fusion YOLOv8 neural inference
  - P2P Swarm communication via EdgeBroker with RF path loss & shadow fading
  - Store-and-forward QoS 1 buffering under RF link degradation
  - Target consensus mapping & multi-layer metrics logging
"""

import os
import sys
import time
import json
import math
import random
import csv
import numpy as np
from collections import defaultdict

# Add FlySim and root to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "FlySim")))

from sar_world import SARWorld
from rgbt_detector import RGBTDetector
import swarm_network


class SimulatedUAV:
    def __init__(self, uav_id, start_x, start_y, altitude, transit_speed, search_speed, assigned_sectors, physics_engine):
        self.uav_id = str(uav_id)
        self.home_x = float(start_x)
        self.home_y = float(start_y)
        self.x = float(start_x)
        self.y = float(start_y)
        self.altitude = float(altitude)
        self.transit_speed = float(transit_speed)
        self.search_speed = float(search_speed)
        self.speed = float(transit_speed)
        self.assigned_sectors = list(assigned_sectors)  # List of sector IDs to survey
        self.current_waypoint_idx = 0
        self.waypoints = []
        self.state = "TRANSIT"  # "TRANSIT", "SEARCHING", "RETURNING", "LANDED", "CRASHED"
        
        # RF & EdgeBroker
        self.broker = swarm_network.EdgeBroker(self.uav_id, physics_engine)
        self.discovered_targets = {}  # Local target registry: {target_id: target_dict}
        self.consensus_registry = {}  # Targets learned from swarm peers: {target_id: {from: ..., data: ...}}
        
        self.trajectory_history = [(round(self.x, 2), round(self.y, 2))]
        self.total_distance_flown = 0.0
        self.scanned_sectors = set()
        self.is_alive = True
        self.crash_pos = None

    def set_waypoints(self, waypoints):
        self.waypoints = waypoints
        self.current_waypoint_idx = 0

    def get_location_dict(self):
        # Scale meters to mock coordinates so physics_engine.calculate_euclidean_distance works directly in meters
        scale = 1.113195e5
        return {'lat': self.y / scale, 'lon': self.x / scale}

    def update_position(self, dt):
        """Moves the UAV toward the current target waypoint and transitions flight states"""
        if not self.is_alive:
            self.state = "CRASHED"
            return True  # Crashed drone ceases movement

        if not self.waypoints or self.current_waypoint_idx >= len(self.waypoints):
            self.state = "LANDED"
            return True  # Completed assigned route and returned to base

        # Are we heading back to base? (Last waypoint is home base)
        if self.current_waypoint_idx == len(self.waypoints) - 1:
            self.state = "RETURNING"
            self.speed = self.transit_speed
        elif self.state == "TRANSIT":
            self.speed = self.transit_speed
        else:
            self.speed = self.search_speed

        target_x, target_y = self.waypoints[self.current_waypoint_idx]
        dx = target_x - self.x
        dy = target_y - self.y
        dist = math.hypot(dx, dy)

        step = self.speed * dt
        if dist <= step or dist < 2.0:
            self.x = target_x
            self.y = target_y
            self.current_waypoint_idx += 1
            # Once we reach our first search sector, transition from high-speed TRANSIT to SEARCHING
            if self.current_waypoint_idx >= 1 and self.current_waypoint_idx < len(self.waypoints) - 1:
                self.state = "SEARCHING"
                self.speed = self.search_speed
        else:
            self.x += (dx / dist) * step
            self.y += (dy / dist) * step
            self.total_distance_flown += step

        self.trajectory_history.append((round(self.x, 2), round(self.y, 2)))
        return False


class SwarmSimulation:
    def __init__(self, num_drones=3, arena_size=400.0, grid_dim=5,
                 model_path="best.pt", conf_thresh=0.20,
                 sim_speed_multiplier=5.0, seed=42,
                 fail_drone_id=None, fail_time=None,
                 base_x=None, base_y=None):
        
        random.seed(seed)
        self.arena_size = arena_size
        self.grid_dim = grid_dim
        self.num_drones = num_drones
        self.conf_thresh = conf_thresh
        self.sim_speed_multiplier = sim_speed_multiplier

        # Unified Ground Control Station (GCS) / Base Station Staging Area (Default: South-West Corner at 5% of arena)
        bx = float(base_x) if base_x is not None else round(arena_size * 0.05, 1)
        by = float(base_y) if base_y is not None else round(arena_size * 0.05, 1)
        self.base_station = [bx, by]

        self.fail_drone_id = int(fail_drone_id) if fail_drone_id is not None and str(fail_drone_id) != "None" else None
        self.fail_time = float(fail_time) if fail_time is not None else None
        self.failure_triggered = False
        self.failed_uav_info = None

        print("\n" + "=" * 65)
        print("INITIALIZING AUTONOMOUS SWARM SAR SIMULATION")
        print(f"Swarm Size: {num_drones} UAVs | Arena: {arena_size}m x {arena_size}m ({grid_dim}x{grid_dim} sectors)")
        print(f"Base Station Launch Pad: X={self.base_station[0]}m, Y={self.base_station[1]}m")
        print(f"Detector Weights: {model_path} (Conf Threshold: {conf_thresh})")
        if self.fail_drone_id is not None:
            print(f"Injected Failure: UAV {self.fail_drone_id} will fail at T={self.fail_time}s")
        print("=" * 65)

        # 1. Initialize In-Memory World
        self.world = SARWorld(arena_width=arena_size, arena_height=arena_size,
                              grid_cols=grid_dim, grid_rows=grid_dim, seed=seed)
        self.world.base_station = self.base_station
        self.world.save_ground_truth("ground_truth_world.json")

        # 2. Initialize Multispectral Vision Detector
        self.detector = RGBTDetector(model_path=model_path, conf_thresh=conf_thresh, device="cpu")

        # 3. Initialize RF Physics Engine (Adaptive for Wide-Area Operations)
        if arena_size >= 2000.0:
            # Multi-kilometer tactical UAV radio (2.4GHz C2 mesh / 2W transmit power)
            self.physics_engine = swarm_network.RFPhysicsEngine(tx_power_dbm=33, frequency_ghz=2.4)
        else:
            self.physics_engine = swarm_network.RFPhysicsEngine(tx_power_dbm=30, frequency_ghz=5)

        # 4. Partition World Sectors across Swarm
        self.drones = self._spawn_drones()

        # 5. Output Data Logs
        self.vision_log_file = "metrics_vision.csv"
        self.network_log_file = "metrics_network.csv"
        self.mission_log_file = "metrics_mission.csv"
        self._init_csv_logs()

        self.sim_time = 0.0
        self.msg_counter = 0
        self.scan_cooldown = {d.uav_id: 0.0 for d in self.drones}
        self.ttfd = None
        self.first_victim_id = None
        self.obstacle_mask = True
        self.all_reported_targets = []
        self.network_stats = {"sent": 0, "delivered": 0, "dropped": 0, "buffered": 0}

    def _init_csv_logs(self):
        with open(self.vision_log_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["sim_time", "uav_id", "sector_id", "image_file", "targets_found", "class_name", "conf", "world_x", "world_y", "latency_ms"])

        with open(self.network_log_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["sim_time", "src_uav", "dst_uav", "topic", "msg_id", "distance_m", "snr_db", "per", "delivered", "buffered"])

        with open(self.mission_log_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["sim_time", "area_covered_pct", "unique_targets_found", "total_alert_broadcasts", "avg_consensus_ratio", "min_peer_dist_m"])

    def _spawn_drones(self):
        drones = []
        grid_dim = self.grid_dim
        arena_size = self.arena_size
        base_x, base_y = self.base_station

        # 1. Geographic Centroid Partitioning (Contiguous Zones - Eliminates Trajectory Crisscrossing)
        if self.num_drones == 1:
            anchors = np.array([[arena_size / 2.0, arena_size / 2.0]])
        elif self.num_drones <= 4:
            offset = arena_size * 0.25
            anchors = np.array([
                [offset, offset],
                [arena_size - offset, offset],
                [offset, arena_size - offset],
                [arena_size - offset, arena_size - offset]
            ])[:self.num_drones]
        else:
            center = arena_size / 2.0
            radius = arena_size * 0.35
            angles = np.linspace(0, 2 * np.pi, self.num_drones, endpoint=False)
            anchors = np.array([[center + radius * np.cos(a), center + radius * np.sin(a)] for a in angles])

        # Assign each sector to the geographically nearest drone anchor
        sectors_per_drone = defaultdict(list)
        for s_id, sec in self.world.sectors.items():
            cx, cy = sec["center"]
            dists = [np.hypot(cx - ax, cy - ay) for ax, ay in anchors]
            best_uav = int(np.argmin(dists))
            sectors_per_drone[best_uav].append(s_id)

        # Ensure every drone has at least one sector
        all_assigned = set()
        for sec_list in sectors_per_drone.values():
            all_assigned.update(sec_list)
        unassigned = [s for s in range(grid_dim * grid_dim) if s not in all_assigned]
        for s in unassigned:
            min_uav = min(range(self.num_drones), key=lambda u: len(sectors_per_drone[u]))
            sectors_per_drone[min_uav].append(s)

        # High-speed transit dash to assigned sectors (up to 50 m/s for wide arenas)
        transit_speed = min(50.0, 18.0 * max(1.0, arena_size / 600.0))
        # Optimal optical sensor search cruise speed (up to 32 m/s)
        search_speed = min(32.0, 12.0 * max(1.0, arena_size / 800.0))

        for uav_idx in range(self.num_drones):
            assigned = sectors_per_drone[uav_idx]
            if not assigned:
                assigned = [uav_idx % (grid_dim * grid_dim)]

            # All drones originate from the unified Ground Control Station (GCS) launch pad
            # Compact staggered grid (12m separation) on launch pad to model distinct launch positions
            pad_cols = 5
            start_x = base_x + (uav_idx % pad_cols) * 12.0
            start_y = base_y + (uav_idx // pad_cols) * 12.0

            drone = SimulatedUAV(uav_id=uav_idx, start_x=start_x, start_y=start_y,
                                 altitude=25.0, transit_speed=transit_speed, search_speed=search_speed,
                                 assigned_sectors=assigned, physics_engine=self.physics_engine)

            # Order waypoints using greedy nearest-neighbor from the Base Station outward
            remaining = list(assigned)
            curr_x, curr_y = start_x, start_y
            waypoints = []
            while remaining:
                best_s = min(remaining, key=lambda s: np.hypot(curr_x - self.world.sectors[s]["center"][0],
                                                               curr_y - self.world.sectors[s]["center"][1]))
                remaining.remove(best_s)
                sec_center = self.world.sectors[best_s]["center"]
                waypoints.append((sec_center[0], sec_center[1]))
                curr_x, curr_y = sec_center

            # Return-to-Base (RTL) back to the drone's individual launch pad at Base Station
            waypoints.append((start_x, start_y))
            drone.set_waypoints(waypoints)

            # Set up P2P DMLT subscriptions with peers
            for peer_idx in range(self.num_drones):
                if peer_idx != uav_idx:
                    drone.broker.update_neighbor_subscription(str(peer_idx), set(["telemetry", "target_alert"]))

            drones.append(drone)

        return drones

    def step(self, dt=1.0):
        self.sim_time += dt
        all_done = True

        # 0. Check for simulated drone failure mid-mission
        if self.fail_drone_id is not None and not self.failure_triggered and self.sim_time >= self.fail_time:
            self.failure_triggered = True
            dead_drone = next((d for d in self.drones if str(d.uav_id) == str(self.fail_drone_id)), None)
            if dead_drone and dead_drone.is_alive:
                dead_drone.is_alive = False
                dead_drone.crash_pos = (round(dead_drone.x, 2), round(dead_drone.y, 2))
                abandoned = [s for s in dead_drone.assigned_sectors if s not in dead_drone.scanned_sectors]
                self.failed_uav_info = {
                    "uav_id": dead_drone.uav_id,
                    "crash_pos": dead_drone.crash_pos,
                    "time": round(self.sim_time, 2),
                    "abandoned_sectors": abandoned
                }
                print("\n" + "=" * 55)
                print(f"[FAILURE EVENT] Motor failure on UAV {dead_drone.uav_id} at T={self.sim_time:.1f}s")
                print(f"Crash location: ({dead_drone.crash_pos[0]:.1f}m, {dead_drone.crash_pos[1]:.1f}m)")
                print(f"Reassigning remaining sectors: {abandoned}")

                # Autonomous Swarm Failover: Reallocate abandoned sectors to nearest active peers
                active_peers = [d for d in self.drones if d.is_alive]
                if abandoned and active_peers:
                    for s_id in abandoned:
                        sec_center = self.world.sectors[s_id]["center"]
                        nearest_peer = min(active_peers, key=lambda p: math.hypot(p.x - sec_center[0], p.y - sec_center[1]))
                        nearest_peer.assigned_sectors.append(s_id)
                        # Insert new sector waypoint before the final return-to-base waypoint
                        if len(nearest_peer.waypoints) > 1:
                            nearest_peer.waypoints.insert(-1, (sec_center[0], sec_center[1]))
                        else:
                            nearest_peer.waypoints.append((sec_center[0], sec_center[1]))
                        # Ensure peer continues navigation if it had reached end of previous route
                        if nearest_peer.current_waypoint_idx >= len(nearest_peer.waypoints) - 1:
                            nearest_peer.current_waypoint_idx = max(0, len(nearest_peer.waypoints) - 2)
                            nearest_peer.state = "SEARCHING"
                        print(f"Sector {s_id} reassigned to UAV {nearest_peer.uav_id}")
                print("=" * 55 + "\n")

        # 1. Update UAV spatial positions
        swarm_locations = {d.uav_id: d.get_location_dict() for d in self.drones if d.is_alive}

        for drone in self.drones:
            if not drone.is_alive:
                continue

            done = drone.update_position(dt)
            if not done:
                all_done = False

            # 2. Check current sector & execute vision scan
            sec = self.world.get_sector_at(drone.x, drone.y)
            if sec is not None:
                # Switch to SEARCHING mode when drone arrives in its assigned patrol territory
                if sec["sector_id"] in drone.assigned_sectors:
                    drone.state = "SEARCHING"

                # Only scan if drone is in SEARCHING state (prevents scanning during high-speed transit from base)
                if drone.state == "SEARCHING":
                    drone.scanned_sectors.add(sec["sector_id"])

                    # Run camera detector at 2-second intervals per drone
                    if self.sim_time >= self.scan_cooldown[drone.uav_id]:
                        self.scan_cooldown[drone.uav_id] = self.sim_time + 2.0
                        img_path = sec["image_path"]

                        t0 = time.time()
                        detections, _ = self.detector.detect(img_path, conf=self.conf_thresh)
                        latency_ms = (time.time() - t0) * 1000

                        if detections:
                            for det in detections:
                                # First detection in entire mission? Record TTFD
                                if self.ttfd is None:
                                    self.ttfd = round(self.sim_time, 2)
                                    print(f"[TTFD] First target at {self.ttfd}s by UAV {drone.uav_id}")

                                # Project normalized bbox center to world coordinates
                                x1, y1, x2, y2 = det["box"]
                                img_w, img_h = 640.0, 512.0
                                xc_norm = ((x1 + x2) / 2.0) / img_w
                                yc_norm = ((y1 + y2) / 2.0) / img_h

                                xmin, xmax, ymin, ymax = sec["bounds"]
                                det_world_x = round(xmin + xc_norm * (xmax - xmin), 2)
                                det_world_y = round(ymin + yc_norm * (ymax - ymin), 2)

                                target_key = f"TGT_{sec['sector_id']}_{round(det_world_x, 1)}_{round(det_world_y, 1)}"

                                # Log vision metric
                                with open(self.vision_log_file, "a", newline="") as f:
                                    writer = csv.writer(f)
                                    writer.writerow([round(self.sim_time, 2), drone.uav_id, sec["sector_id"],
                                                     os.path.basename(img_path), len(detections), det["class_name"],
                                                     det["conf"], det_world_x, det_world_y, round(latency_ms, 2)])

                                # 3. P2P Swarm Network Publication (if newly found target)
                                if target_key not in drone.discovered_targets:
                                    drone.discovered_targets[target_key] = {
                                        "target_key": target_key,
                                        "class_name": det["class_name"],
                                        "conf": det["conf"],
                                        "world_x": det_world_x,
                                        "world_y": det_world_y,
                                        "sector_id": sec["sector_id"],
                                        "detected_by": drone.uav_id,
                                        "time": round(self.sim_time, 2)
                                    }
                                    self.all_reported_targets.append(drone.discovered_targets[target_key])

                                    # Broadcast alert via EdgeBroker
                                    msg_id = f"ALERT_U{drone.uav_id}_{self.msg_counter}"
                                    self.msg_counter += 1
                                    payload = f"{target_key}:{det['class_name']}:{det['conf']}:{det_world_x}:{det_world_y}"

                                    active_peers = [p for p in self.drones if p.uav_id != drone.uav_id and p.is_alive]
                                    self.network_stats["sent"] += len(active_peers)

                                    # Simulate RF transmission to every active peer
                                    for peer in active_peers:
                                        my_loc = drone.get_location_dict()
                                        peer_loc = peer.get_location_dict()
                                        dist_m = self.physics_engine.calculate_euclidean_distance(my_loc, peer_loc)
                                        snr, per = self.physics_engine.calculate_snr_per(my_loc, peer_loc, self.obstacle_mask)

                                        # Direct RF transmission roll
                                        delivered = (random.random() >= per)

                                        # Multi-Hop Mesh Relay: if direct delivery fails over long distances, route via intermediate active UAV
                                        if not delivered and len(active_peers) > 1:
                                            for relay in active_peers:
                                                if relay.uav_id in (drone.uav_id, peer.uav_id) or not relay.is_alive:
                                                    continue
                                                relay_loc = relay.get_location_dict()
                                                d_src_relay = self.physics_engine.calculate_euclidean_distance(my_loc, relay_loc)
                                                d_relay_dst = self.physics_engine.calculate_euclidean_distance(relay_loc, peer_loc)
                                                if d_src_relay < dist_m and d_relay_dst < dist_m:
                                                    _, per1 = self.physics_engine.calculate_snr_per(my_loc, relay_loc, self.obstacle_mask)
                                                    _, per2 = self.physics_engine.calculate_snr_per(relay_loc, peer_loc, self.obstacle_mask)
                                                    if (random.random() >= per1) and (random.random() >= per2):
                                                        delivered = True
                                                        break

                                        buffered = not delivered

                                        if delivered:
                                            self.network_stats["delivered"] += 1
                                            peer.consensus_registry[target_key] = drone.discovered_targets[target_key]
                                        else:
                                            self.network_stats["dropped"] += 1
                                            self.network_stats["buffered"] += 1
                                            drone.broker.qos1_buffers[peer.uav_id].append({
                                                "topic": "target_alert",
                                                "payload": payload,
                                                "message_id": msg_id,
                                                "timestamp": self.sim_time
                                            })

                                        with open(self.network_log_file, "a", newline="") as f:
                                            writer = csv.writer(f)
                                            writer.writerow([round(self.sim_time, 2), drone.uav_id, peer.uav_id,
                                                             "target_alert", msg_id, round(dist_m, 2), round(snr, 2),
                                                             round(per, 3), int(delivered), int(buffered)])

        # 4. Periodic QoS 1 Buffer Flushing
        for drone in self.drones:
            if not drone.is_alive:
                continue
            flushed = drone.broker.flush_buffers(drone.get_location_dict(), swarm_locations, self.obstacle_mask)
            for peer_id in flushed:
                peer = next((d for d in self.drones if d.uav_id == peer_id and d.is_alive), None)
                if peer:
                    for t_key, t_val in drone.discovered_targets.items():
                        peer.consensus_registry[t_key] = t_val

        # 5. Mission Metrics Logging
        total_sectors = self.grid_dim * self.grid_dim
        all_scanned = set().union(*[d.scanned_sectors for d in self.drones])
        coverage_pct = round((len(all_scanned) / total_sectors) * 100.0, 1)

        active_drones = [d for d in self.drones if d.is_alive]
        all_unique_targets = set().union(*[set(d.discovered_targets.keys()) for d in self.drones])
        if all_unique_targets and active_drones:
            consensus_scores = []
            for t in all_unique_targets:
                count_knowing = sum(1 for d in active_drones if (t in d.discovered_targets or t in d.consensus_registry))
                consensus_scores.append(count_knowing / len(active_drones))
            avg_consensus = round(float(np.mean(consensus_scores)), 3)
        else:
            avg_consensus = 0.0

        min_dist = float("inf")
        for i in range(len(active_drones)):
            for j in range(i + 1, len(active_drones)):
                d = math.hypot(active_drones[i].x - active_drones[j].x, active_drones[i].y - active_drones[j].y)
                if d < min_dist:
                    min_dist = d
        if min_dist == float("inf"):
            min_dist = 0.0

        with open(self.mission_log_file, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([round(self.sim_time, 2), coverage_pct, len(all_unique_targets),
                             self.msg_counter, avg_consensus, round(min_dist, 2)])

        return {
            "sim_time": self.sim_time,
            "coverage_pct": coverage_pct,
            "targets_count": len(all_unique_targets),
            "targets": list(self.all_reported_targets),
            "avg_consensus": avg_consensus,
            "active_drones": len(active_drones),
            "drones": self.drones,
            "base_station": self.base_station,
            "arena_size": self.arena_size,
            "failed_uav_info": self.failed_uav_info,
            "all_done": all_done
        }

    def run_streaming(self, max_sim_seconds=300, dt=1.0, yield_interval=8):
        print(f"\nSTARTING SWARM SEARCH MISSION (Simulated Time: {max_sim_seconds}s, step: {dt}s)...")
        last_yield_time = 0.0
        while self.sim_time < max_sim_seconds:
            snap = self.step(dt)
            if (self.sim_time - last_yield_time) >= yield_interval or snap["all_done"]:
                last_yield_time = self.sim_time
                yield snap
            if snap["all_done"]:
                print(f"\nAll drones completed their search patterns at T={self.sim_time:.1f}s!")
                break
        self._export_mission_output()
        # Final completed snapshot
        total_sectors = self.grid_dim * self.grid_dim
        all_scanned = set().union(*[d.scanned_sectors for d in self.drones])
        coverage_pct = round((len(all_scanned) / total_sectors) * 100.0, 1)
        yield {
            "sim_time": self.sim_time,
            "coverage_pct": coverage_pct,
            "targets_count": len(self.all_reported_targets),
            "targets": list(self.all_reported_targets),
            "avg_consensus": 1.0,
            "active_drones": len([d for d in self.drones if d.is_alive]),
            "drones": self.drones,
            "base_station": self.base_station,
            "arena_size": self.arena_size,
            "failed_uav_info": self.failed_uav_info,
            "all_done": True
        }

    def run(self, max_sim_seconds=300, dt=1.0):
        for snap in self.run_streaming(max_sim_seconds=max_sim_seconds, dt=dt, yield_interval=20):
            print(f"[T={snap['sim_time']:.0f}s] Area Coverage: {snap['coverage_pct']}% | Targets: {snap['targets_count']} | Consensus: {snap['avg_consensus']*100:.1f}%")

    def _export_mission_output(self):
        output = {
            "mission_duration_sec": round(self.sim_time, 2),
            "ttfd_sec": self.ttfd,
            "swarm_size": self.num_drones,
            "arena_size": self.arena_size,
            "base_station": self.base_station,
            "failed_uav_info": self.failed_uav_info,
            "network_stats": self.network_stats,
            "drones": [
                {
                    "uav_id": d.uav_id,
                    "is_alive": d.is_alive,
                    "crash_pos": d.crash_pos,
                    "total_distance_m": round(d.total_distance_flown, 2),
                    "sectors_scanned": list(d.scanned_sectors),
                    "targets_discovered_count": len(d.discovered_targets),
                    "consensus_targets_count": len(d.consensus_registry),
                    "trajectory": d.trajectory_history[::5] # Subsample trajectory for compact storage
                }
                for d in self.drones
            ],
            "reported_targets": self.all_reported_targets
        }

        with open("swarm_mission_output.json", "w") as f:
            json.dump(output, f, indent=2)

        print("\n" + "=" * 65)
        print("MISSION COMPLETED & EXPORTED")
        print(f"Summary saved to: swarm_mission_output.json")
        print(f"Vision log:       {self.vision_log_file}")
        print(f"Network log:      {self.network_log_file}")
        print(f"Mission log:      {self.mission_log_file}")
        print("=" * 65)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Autonomous Swarm SAR Mission Simulator")
    parser.add_argument("--drones", type=int, default=3, help="Number of drones in the swarm (default: 3)")
    parser.add_argument("--arena", type=float, default=400.0, help="Arena width/height in meters (default: 400.0)")
    parser.add_argument("--grid", type=int, default=5, help="Number of sector rows/cols (default: 5)")
    parser.add_argument("--model", type=str, default="best.pt", help="Path to YOLO model weights (default: best.pt)")
    parser.add_argument("--conf", type=float, default=0.20, help="Detection confidence threshold (default: 0.20)")
    parser.add_argument("--duration", type=int, default=180, help="Maximum mission duration in seconds (default: 180)")
    parser.add_argument("--step", type=float, default=1.0, help="Simulation step size in seconds (default: 1.0)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility (default: 42)")
    parser.add_argument("--fail-drone", type=int, default=None, help="UAV ID to simulate mid-mission failure (default: None)")
    parser.add_argument("--fail-time", type=float, default=45.0, help="Simulation time in seconds when drone failure occurs (default: 45.0)")
    parser.add_argument("--base-x", type=float, default=None, help="Base Station X coordinate in meters (default: 5 percent of arena)")
    parser.add_argument("--base-y", type=float, default=None, help="Base Station Y coordinate in meters (default: 5 percent of arena)")
    args = parser.parse_args()

    sim = SwarmSimulation(num_drones=args.drones, arena_size=args.arena, grid_dim=args.grid,
                          model_path=args.model, conf_thresh=args.conf, seed=args.seed,
                          fail_drone_id=args.fail_drone, fail_time=args.fail_time,
                          base_x=args.base_x, base_y=args.base_y)
    sim.run(max_sim_seconds=args.duration, dt=args.step)
