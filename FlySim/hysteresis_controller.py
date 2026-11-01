#!/usr/bin/env python3
"""
Dual-Threshold Hysteresis Loop for Energy-Weighted Voronoi Flight Controllers.

Mitigates high-frequency oscillatory state transitions (chattering) induced by
minor sensor noise, communication latency, and micro-fluctuations in battery voltage.

Formulation:
  1. Battery Decay Hysteresis (Temporal & Energy Threshold):
     w_i(t) = (B_i(t) / B_max)^alpha  if B_i(t_k) - B_i(t) >= tau_epsilon
              w_i(t_k)                 otherwise

  2. Spatial Centroid Hysteresis (Kinetic Threshold):
     C_i(t) = C_i^*                    if ||C_i^* - C_i(t_k)|| >= tau_delta
              C_i(t_k)                 otherwise

  3. Forced-Override Condition (Node Failure / Topology Change):
     U_i(t) = ((B_i(t_k) - B_i(t) >= tau_epsilon) and (||C_i^* - C_i(t_k)|| >= tau_delta))
              or (N(t) != N(t_k))
"""

import math
from typing import Tuple, Sequence, Optional, Dict, Any, List


def compute_ew_cvt_centroids(
    generators: Dict[str, Tuple[float, float]],
    weights: Dict[str, float],
    arena_width: float,
    arena_height: float,
    grid_res: int = 40
) -> Dict[str, Tuple[float, float]]:
    """
    Computes theoretical Energy-Weighted Centroidal Voronoi Tessellation (EW-CVT)
    mass centroids C_i^* over a 2D bounding arena.

    The energy-weighted metric evaluates the power distance:
      d_w(p, x_i) = ||p - x_i||^2 / max(0.01, w_i)

    Args:
        generators: Dict of {uav_id: (x, y)} generator positions.
        weights: Dict of {uav_id: w_i} energy weights in (0, 1].
        arena_width: Width of the bounding arena in meters.
        arena_height: Height of the bounding arena in meters.
        grid_res: Grid sampling resolution along each axis.

    Returns:
        Dict of {uav_id: (cx, cy)} theoretical mass centroids C_i^*.
    """
    if not generators:
        return {}

    node_ids = list(generators.keys())
    pts_x = [generators[nid][0] for nid in node_ids]
    pts_y = [generators[nid][1] for nid in node_ids]
    w_vals = [max(0.01, float(weights.get(nid, 1.0))) for nid in node_ids]

    cell_x_sums = {nid: 0.0 for nid in node_ids}
    cell_y_sums = {nid: 0.0 for nid in node_ids}
    cell_counts = {nid: 0 for nid in node_ids}

    xs = [arena_width * (i + 0.5) / grid_res for i in range(grid_res)]
    ys = [arena_height * (j + 0.5) / grid_res for j in range(grid_res)]

    for px in xs:
        for py in ys:
            # Find nearest generator in power distance
            best_idx = 0
            best_dist = float("inf")
            for idx in range(len(node_ids)):
                dx = px - pts_x[idx]
                dy = py - pts_y[idx]
                dist_sq = dx * dx + dy * dy
                weighted_dist = dist_sq / w_vals[idx]
                if weighted_dist < best_dist:
                    best_dist = weighted_dist
                    best_idx = idx

            chosen_id = node_ids[best_idx]
            cell_x_sums[chosen_id] += px
            cell_y_sums[chosen_id] += py
            cell_counts[chosen_id] += 1

    centroids = {}
    for nid in node_ids:
        if cell_counts[nid] > 0:
            cx = cell_x_sums[nid] / cell_counts[nid]
            cy = cell_y_sums[nid] / cell_counts[nid]
            centroids[nid] = (round(cx, 2), round(cy, 2))
        else:
            # Fallback to generator location if cell has zero sample points
            centroids[nid] = generators[nid]

    return centroids


class DualThresholdHysteresisController:
    """
    Manages dual-threshold hysteresis locking for an individual UAV node.
    Governs energy generator weights, spatial centroid targets, and hard-overrides
    triggered by Data Link Lookup (DLL) network topology changes.
    """

    def __init__(
        self,
        uav_id: str,
        initial_pos: Tuple[float, float],
        b_max: float = 100.0,
        tau_epsilon_ratio: float = 0.02,
        tau_delta: float = 5.0,
        alpha: float = 1.0,
        initial_battery: Optional[float] = None,
        initial_topology: Optional[Sequence[str]] = None,
        uav_mass_kg: float = 1.5
    ):
        """
        Args:
            uav_id: Unique string identifier for the UAV.
            initial_pos: Initial (x, y) waypoint coordinates in meters.
            b_max: Maximum nominal battery capacity (e.g., 100.0% or Wh).
            tau_epsilon_ratio: Fraction of b_max required to unlock weight updates (default: 0.02 = 2%).
            tau_delta: Spatial centroid shift margin in meters (default: 5.0m).
            alpha: Exponential scaling factor for battery weight generator (default: 1.0).
            initial_battery: Starting battery level (default: b_max).
            initial_topology: Initial active network topology node sequence.
            uav_mass_kg: Nominal UAV mass in kilograms for kinetic energy calculations.
        """
        self.uav_id = str(uav_id)
        self.b_max = float(b_max)
        self.tau_epsilon = float(tau_epsilon_ratio * self.b_max)
        self.tau_delta = float(tau_delta)
        self.alpha = float(alpha)
        self.uav_mass_kg = float(uav_mass_kg)

        # Initial state at t = t_0
        self.t_k = 0.0
        self.b_tk = float(initial_battery if initial_battery is not None else self.b_max)
        self.w_tk = (self.b_tk / self.b_max) ** self.alpha
        self.c_tk = (float(initial_pos[0]), float(initial_pos[1]))
        self.n_tk = tuple(sorted(str(nid) for nid in (initial_topology or [self.uav_id])))

        # Current active commanded state
        self.current_weight = self.w_tk
        self.current_commanded_pos = self.c_tk

        # Performance & telemetry statistics
        self.total_evaluations = 0
        self.updates_executed = 0
        self.chattering_events_suppressed = 0
        self.battery_holds = 0
        self.spatial_holds = 0
        self.forced_overrides = 0
        self.cumulative_energy_saved_joules = 0.0

    def compute_theoretical_weight(self, current_battery: float) -> float:
        """Computes w_i^* = (B_i(t) / B_max)^alpha."""
        clamped_b = max(0.0, min(self.b_max, current_battery))
        return (clamped_b / self.b_max) ** self.alpha

    def evaluate(
        self,
        current_time: float,
        current_battery: float,
        theoretical_centroid: Tuple[float, float],
        current_topology: Sequence[str],
        current_speed: float = 32.0
    ) -> Dict[str, Any]:
        """
        Evaluates the dual-threshold hysteresis loop and forced override conditions.

        Master Trigger Function:
          U_i(t) = ((B_i(t_k) - B_i(t) >= tau_epsilon) and (||C_i^* - C_i(t_k)|| >= tau_delta))
                   or (N(t) != N(t_k))

        Args:
            current_time: Current simulation timestamp t in seconds.
            current_battery: Current measured battery level B_i(t).
            theoretical_centroid: Newly calculated theoretical centroid C_i^* = (x, y).
            current_topology: Current active node sequence N(t) from DLL layer heartbeats.
            current_speed: Current flight speed in m/s (for kinetic savings estimation).

        Returns:
            Dictionary containing commanded waypoint C_i(t), effective weight w_i(t),
            trigger decision U_i(t), update reason, and energy metrics.
        """
        self.total_evaluations += 1

        b_t = float(current_battery)
        c_star = (float(theoretical_centroid[0]), float(theoretical_centroid[1]))
        n_t = tuple(sorted(str(nid) for nid in current_topology))

        delta_b = self.b_tk - b_t
        spatial_shift = math.hypot(c_star[0] - self.c_tk[0], c_star[1] - self.c_tk[1])
        topology_changed = (n_t != self.n_tk)

        battery_threshold_met = (delta_b >= self.tau_epsilon)
        spatial_threshold_met = (spatial_shift >= self.tau_delta)

        # Trigger logic
        steady_state_trigger = (battery_threshold_met and spatial_threshold_met)
        u_t = steady_state_trigger or topology_changed

        if u_t:
            # Update approved: Commit new baseline t_k <- t
            self.t_k = float(current_time)
            self.b_tk = b_t
            self.current_weight = self.compute_theoretical_weight(b_t)
            self.w_tk = self.current_weight
            self.current_commanded_pos = c_star
            self.c_tk = c_star
            self.n_tk = n_t
            self.updates_executed += 1

            if topology_changed:
                self.forced_overrides += 1
                reason = "FORCED_OVERRIDE_TOPOLOGY_CHANGE"
            else:
                reason = "STEADY_STATE_DUAL_THRESHOLD_MET"
        else:
            # Hysteresis active: Maintain locked baseline state
            self.chattering_events_suppressed += 1

            if not battery_threshold_met:
                self.battery_holds += 1
            if not spatial_threshold_met:
                self.spatial_holds += 1

            # Estimate kinetic energy preserved by avoiding unnecessary yaw/roll heading adjustments
            # Kinetic turn penalty ~ 0.5 * m * (delta_v)^2 + angular acceleration effort
            energy_saved = 0.5 * self.uav_mass_kg * (max(1.0, current_speed * 0.15) ** 2)
            self.cumulative_energy_saved_joules += energy_saved
            reason = "HYSTERESIS_LOCKED_CHATTERING_SUPPRESSED"

        return {
            "uav_id": self.uav_id,
            "sim_time": current_time,
            "trigger_u_t": u_t,
            "commanded_pos": self.current_commanded_pos,
            "effective_weight": self.current_weight,
            "theoretical_centroid": c_star,
            "delta_b": delta_b,
            "tau_epsilon": self.tau_epsilon,
            "spatial_shift": spatial_shift,
            "tau_delta": self.tau_delta,
            "topology_changed": topology_changed,
            "reason": reason,
            "cumulative_energy_saved_joules": self.cumulative_energy_saved_joules
        }

    def get_status_summary(self) -> Dict[str, Any]:
        """Returns diagnostic metrics on chattering suppression and energy efficiency."""
        suppression_rate = (
            (self.chattering_events_suppressed / self.total_evaluations * 100.0)
            if self.total_evaluations > 0 else 0.0
        )
        return {
            "uav_id": self.uav_id,
            "total_evaluations": self.total_evaluations,
            "updates_executed": self.updates_executed,
            "chattering_events_suppressed": self.chattering_events_suppressed,
            "suppression_rate_pct": round(suppression_rate, 2),
            "forced_overrides": self.forced_overrides,
            "battery_holds": self.battery_holds,
            "spatial_holds": self.spatial_holds,
            "energy_saved_joules": round(self.cumulative_energy_saved_joules, 2)
        }
