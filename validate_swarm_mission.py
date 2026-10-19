#!/usr/bin/env python3
"""
Final Swarm Mission Validator & Ground-Truth Scoring Engine.
Validates the autonomous swarm's reported detections against actual ground-truth dataset annotations.
Computes:
  - Perception: True Positives (TP), False Positives (FP), False Negatives (FN), Precision, Recall, F1, RMSE
  - Network: Packet Delivery Ratio (PDR), SNR degradation, QoS 1 Store-and-Forward recovery
  - Swarm Mission: Area Coverage %, Time-to-First-Detection (TTFD), Consensus Ratio %
Generates publication-quality figures:
  - sar_mission_spatial_validation.png
  - sar_network_and_mission_performance.png
  - mission_validation_report.json
"""

import os
import json
import math
import csv
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches


def run_validation(world_json="ground_truth_world.json",
                   swarm_json="swarm_mission_output.json",
                   network_csv="metrics_network.csv",
                   mission_csv="metrics_mission.csv",
                   match_distance_thresh=None):

    print("\n" + "=" * 65)
    print("RUNNING FINAL SWARM MISSION VALIDATION AGAINST GROUND TRUTH")
    print("=" * 65)

    if not os.path.exists(world_json) or not os.path.exists(swarm_json):
        print(f"Error: Missing {world_json} or {swarm_json}. Please run simulate_swarm_mission.py first.")
        return

    with open(world_json, "r") as f:
        world_gt = json.load(f)

    with open(swarm_json, "r") as f:
        swarm_out = json.load(f)

    arena_w = world_gt["arena_width"]
    arena_h = world_gt["arena_height"]
    gt_victims = world_gt["victims"]
    reported_targets = swarm_out["reported_targets"]
    drones = swarm_out["drones"]

    if match_distance_thresh is None:
        sec_w = arena_w / world_gt.get("grid_cols", 5)
        match_distance_thresh = max(18.0, round(0.05 * sec_w, 1))
    print(f"Spatial Association Matching Threshold: {match_distance_thresh}m")

    # Sectors scanned by the swarm
    surveyed_sectors = set()
    for d in drones:
        surveyed_sectors.update(d["sectors_scanned"])

    # Filter GT victims in surveyed sectors (fair comparison)
    gt_in_surveyed = [v for v in gt_victims if v["sector_id"] in surveyed_sectors]

    # --- 1. SPATIAL ASSOCIATION (GROUND TRUTH VS SWARM REPORTS) ---
    tp_matches = []
    fn_missed = []
    matched_reported_indices = set()

    loc_errors = []

    for gt in gt_in_surveyed:
        gx, gy = gt["world_x"], gt["world_y"]
        best_dist = float("inf")
        best_rep_idx = None

        for idx, rep in enumerate(reported_targets):
            rx, ry = rep["world_x"], rep["world_y"]
            dist = math.hypot(gx - rx, gy - ry)
            if dist < best_dist:
                best_dist = dist
                best_rep_idx = idx

        if best_dist <= match_distance_thresh:
            tp_matches.append({
                "gt_id": gt["target_id"],
                "gt_pos": (gx, gy),
                "rep_pos": (reported_targets[best_rep_idx]["world_x"], reported_targets[best_rep_idx]["world_y"]),
                "error_m": round(best_dist, 2),
                "conf": reported_targets[best_rep_idx]["conf"],
                "detected_by": reported_targets[best_rep_idx]["detected_by"]
            })
            matched_reported_indices.add(best_rep_idx)
            loc_errors.append(best_dist)
        else:
            fn_missed.append(gt)

    # False Positives: reported targets that didn't match any ground truth victim
    fp_false_alarms = [
        rep for idx, rep in enumerate(reported_targets)
        if idx not in matched_reported_indices
    ]

    tp = len(tp_matches)
    fp = len(fp_false_alarms)
    fn = len(fn_missed)

    precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 0.0
    recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0
    f1 = round(2 * (precision * recall) / (precision + recall), 4) if (precision + recall) > 0 else 0.0
    mean_loc_error = round(float(np.mean(loc_errors)), 2) if loc_errors else 0.0
    rmse_loc_error = round(float(np.sqrt(np.mean(np.array(loc_errors)**2))), 2) if loc_errors else 0.0

    # --- 2. NETWORK & CONSENSUS METRICS ---
    net_stats = swarm_out.get("network_stats", {})
    sent = net_stats.get("sent", 0)
    delivered = net_stats.get("delivered", 0)
    dropped = net_stats.get("dropped", 0)
    pdr = round((delivered / sent) * 100.0, 2) if sent > 0 else 100.0

    # Calculate average consensus: what % of swarm drones hold each detected target?
    total_unique_reported = max(1, len(reported_targets))
    drone_knowledge = [min(1.0, (d["targets_discovered_count"] + d["consensus_targets_count"]) / total_unique_reported) for d in drones]
    avg_consensus_pct = round(float(np.mean(drone_knowledge) * 100.0), 1) if drone_knowledge else 0.0
    coverage_pct = round((len(surveyed_sectors) / world_gt["total_sectors"]) * 100.0, 1)

    # --- 3. PRINT TERMINAL VALIDATION REPORT ---
    print("\n" + "=" * 65)
    print("SWARM SAR MISSION VALIDATION REPORT")
    print("=" * 65)
    print(f"Arena Survey Coverage:              {coverage_pct}% ({len(surveyed_sectors)}/{world_gt['total_sectors']} sectors)")
    print(f"Time to First Detection (TTFD):     {swarm_out.get('ttfd_sec', 'N/A')} seconds")
    print(f"Total Ground Truth Targets:         {len(gt_in_surveyed)} (in surveyed area)")
    print(f"Swarm Reported Detections:          {len(reported_targets)}")
    print(f"   - True Positives (TP):           {tp}")
    print(f"   - False Positives (FP):          {fp} (false alarms)")
    print(f"   - False Negatives (FN):          {fn} (missed targets)")
    print(f"Perception Metrics:")
    print(f"   - Precision:                     {precision * 100:.2f}%")
    print(f"   - Recall:                        {recall * 100:.2f}%")
    print(f"   - F1-Score:                      {f1:.4f}")
    print(f"   - Mean Localization Error:       {mean_loc_error} meters")
    print(f"   - RMSE Localization Error:       {rmse_loc_error} meters")
    print(f"Communication & RF Mesh Metrics:")
    print(f"   - Packets Sent / Delivered:      {sent} / {delivered}")
    print(f"   - Packet Delivery Ratio (PDR):   {pdr}%")
    print(f"   - Swarm Consensus Spread:        {avg_consensus_pct}%")
    print("=" * 65)

    # Print failure info if present
    failed_uav_info = swarm_out.get("failed_uav_info")
    if failed_uav_info:
        print(f"UAV In-Flight Failure:            UAV {failed_uav_info['uav_id']} stopped at T={failed_uav_info['time']}s at ({failed_uav_info['crash_pos'][0]:.1f}m, {failed_uav_info['crash_pos'][1]:.1f}m)")
        print(f"   - Reallocated Sectors:         {failed_uav_info.get('abandoned_sectors', [])}")

    # --- 4. GENERATE PUBLICATION FIGURES ---
    _plot_spatial_validation_map(world_gt, drones, tp_matches, fn_missed, fp_false_alarms, arena_w, arena_h, failed_uav_info)
    _plot_network_and_mission(network_csv, mission_csv)

    # Save detailed JSON report
    report = {
        "summary": {
            "area_coverage_pct": coverage_pct,
            "ttfd_sec": swarm_out.get("ttfd_sec"),
            "ground_truth_targets_in_surveyed": len(gt_in_surveyed),
            "swarm_reported_targets": len(reported_targets),
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
            "mean_localization_error_m": mean_loc_error,
            "rmse_localization_error_m": rmse_loc_error,
            "pdr_pct": pdr,
            "swarm_consensus_pct": avg_consensus_pct
        },
        "failed_uav_info": failed_uav_info,
        "matches": tp_matches[:50],  # Sample of matches
        "false_alarms": fp_false_alarms[:20]
    }

    report_path = "mission_validation_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"Validation report saved to: {report_path}")
    print("Publication figures generated:")
    print("   1. sar_mission_spatial_validation.png")
    print("   2. sar_network_and_mission_performance.png\n")


def _plot_spatial_validation_map(world_gt, drones, tp_matches, fn_missed, fp_false_alarms, arena_w, arena_h, failed_uav_info=None):
    fig, ax = plt.subplots(figsize=(11, 11), dpi=300)
    
    # Draw sector grid lines
    grid_cols = world_gt["grid_cols"]
    grid_rows = world_gt["grid_rows"]
    sec_w = arena_w / grid_cols
    sec_h = arena_h / grid_rows

    for c in range(grid_cols + 1):
        ax.axvline(c * sec_w, color="#dddddd", linestyle="--", linewidth=0.8)
    for r in range(grid_rows + 1):
        ax.axhline(r * sec_h, color="#dddddd", linestyle="--", linewidth=0.8)

    # Label sectors
    for s in world_gt["sectors"]:
        cx, cy = s["center"]
        ax.text(cx, cy, f"S{s['sector_id']:02d}\n({s['victim_count']} GT)", color="#aaaaaa",
                fontsize=8, ha="center", va="center", alpha=0.6)

    # Plot Swarm Base Station / Launch Pad
    base_station = world_gt.get("base_station") or [arena_w * 0.05, arena_h * 0.05]
    bx, by = base_station
    ax.scatter([bx], [by], c="#f39c12", s=220, marker="s", edgecolors="black", linewidths=2.0,
               label="Swarm Base Station / Launch Pad", zorder=12)
    ax.text(bx, by - (arena_h * 0.028), "BASE STATION / GCS\n(Launch & Return)",
            color="#b7791f", fontweight="bold", fontsize=8.5, ha="center",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="#fef9e7", edgecolor="#f39c12", alpha=0.95), zorder=13)

    # Plot drone search trajectories (10 distinct high-contrast colors)
    palette = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
    ]
    for idx, d in enumerate(drones):
        traj = np.array(d["trajectory"])
        if len(traj) > 0:
            c = palette[idx % len(palette)]
            is_alive = d.get("is_alive", True)
            label = f"UAV {d['uav_id']} Flight Path" if is_alive else f"UAV {d['uav_id']} (Crashed)"
            ls = "-" if is_alive else "--"
            alpha = 0.85 if is_alive else 0.5
            ax.plot(traj[:, 0], traj[:, 1], color=c, linestyle=ls, linewidth=1.8,
                    alpha=alpha, label=label)
            ax.plot(traj[0, 0], traj[0, 1], marker="o", color=c, markersize=6)

    # Plot True Positives (Detected Victims)
    if tp_matches:
        tp_x = [m["rep_pos"][0] for m in tp_matches]
        tp_y = [m["rep_pos"][1] for m in tp_matches]
        ax.scatter(tp_x, tp_y, c="#2ecc71", s=55, marker="o", edgecolors="black", linewidths=0.8,
                   label=f"True Positive Detections ({len(tp_matches)})", zorder=5)

    # Plot Missed Victims (False Negatives)
    if fn_missed:
        fn_x = [v["world_x"] for v in fn_missed]
        fn_y = [v["world_y"] for v in fn_missed]
        ax.scatter(fn_x, fn_y, c="#e74c3c", s=45, marker="x", linewidths=1.5,
                   label=f"Missed Ground Truth ({len(fn_missed)})", zorder=4)

    # Plot False Alarms (False Positives)
    if fp_false_alarms:
        fp_x = [f["world_x"] for f in fp_false_alarms]
        fp_y = [f["world_y"] for f in fp_false_alarms]
        ax.scatter(fp_x, fp_y, c="#9b59b6", s=50, marker="^", edgecolors="black", linewidths=0.8,
                   label=f"False Alarms ({len(fp_false_alarms)})", zorder=5)

    # Plot Catastrophic In-Flight Crash Site if failure was simulated
    if failed_uav_info and "crash_pos" in failed_uav_info:
        cx, cy = failed_uav_info["crash_pos"]
        fail_id = failed_uav_info["uav_id"]
        fail_time = failed_uav_info.get("time", "")
        ax.scatter([cx], [cy], c="#e74c3c", s=250, marker="X", edgecolors="black", linewidths=2.2,
                   label=f"Crash Site: UAV {fail_id} (T={fail_time}s)", zorder=10)
        ax.text(cx, cy + (arena_h * 0.03), f"CRASH: UAV {fail_id}\n(T={fail_time}s)",
                color="#c0392b", fontweight="bold", fontsize=9, ha="center",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="#fff5f5", edgecolor="#e74c3c", alpha=0.95), zorder=11)

    ax.set_xlim(0, arena_w)
    ax.set_ylim(0, arena_h)
    ax.set_xlabel("World X Position (meters)", fontsize=11, fontweight="bold")
    ax.set_ylabel("World Y Position (meters)", fontsize=11, fontweight="bold")
    ax.set_title("Autonomous Swarm SAR Mission Spatial Validation\n(4-Channel Early-Fusion Perception vs. Ground Truth with Mid-Mission Failover)",
                 fontsize=12, fontweight="bold", pad=12)
    ax.legend(loc="upper right", framealpha=0.9, fontsize=8)
    ax.grid(False)
    plt.tight_layout()
    plt.savefig("sar_mission_spatial_validation.png")
    plt.close()


def _plot_network_and_mission(network_csv, mission_csv):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5), dpi=300)

    # 1. Mission Progress (Area Coverage & Victims Discovered)
    if os.path.exists(mission_csv):
        times, coverage, victims, consensus = [], [], [], []
        with open(mission_csv, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                times.append(float(row["sim_time"]))
                coverage.append(float(row["area_covered_pct"]))
                victims.append(int(row["unique_targets_found"]))
                consensus.append(float(row["avg_consensus_ratio"]) * 100.0)

        ax1.plot(times, coverage, color="#2980b9", linewidth=2.0, label="Arena Coverage (%)")
        ax1.plot(times, consensus, color="#27ae60", linestyle="--", linewidth=1.8, label="Swarm Consensus Spread (%)")
        ax1.set_xlabel("Mission Elapsed Time (seconds)", fontsize=10, fontweight="bold")
        ax1.set_ylabel("Percentage (%)", fontsize=10, fontweight="bold")
        ax1.set_ylim(0, 105)
        ax1.grid(True, linestyle=":", alpha=0.6)
        ax1.set_title("SAR Mission Exploration & Consensus Propagation", fontsize=11, fontweight="bold")

        ax1_twin = ax1.twinx()
        ax1_twin.plot(times, victims, color="#e67e22", linestyle="-.", linewidth=2.0, label="Victims Located")
        ax1_twin.set_ylabel("Unique Victims Found", fontsize=10, fontweight="bold", color="#e67e22")
        ax1_twin.tick_params(axis="y", labelcolor="#e67e22")

        # Combine legends
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax1_twin.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc="lower right", fontsize=8)

    # 2. RF Physics (Distance vs SNR & PER)
    if os.path.exists(network_csv):
        dist_list, snr_list, per_list = [], [], []
        with open(network_csv, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                dist_list.append(float(row["distance_m"]))
                snr_list.append(float(row["snr_db"]))
                per_list.append(float(row["per"]))

        if dist_list:
            sort_idx = np.argsort(dist_list)
            dist_sorted = np.array(dist_list)[sort_idx]
            snr_sorted = np.array(snr_list)[sort_idx]
            per_sorted = np.array(per_list)[sort_idx]

            ax2.scatter(dist_list, snr_list, c="#3498db", alpha=0.3, s=15, label="Observed SNR (dB)")
            ax2.set_xlabel("Inter-UAV Distance (meters)", fontsize=10, fontweight="bold")
            ax2.set_ylabel("Signal-to-Noise Ratio (SNR dB)", fontsize=10, fontweight="bold", color="#3498db")
            ax2.tick_params(axis="y", labelcolor="#3498db")
            ax2.grid(True, linestyle=":", alpha=0.6)
            ax2.set_title("FANET RF Physical Channel Degradation", fontsize=11, fontweight="bold")

            ax2_twin = ax2.twinx()
            ax2_twin.plot(dist_sorted, per_sorted, color="#c0392b", linewidth=2.0, label="Packet Error Rate (PER)")
            ax2_twin.set_ylabel("Packet Error Rate (PER)", fontsize=10, fontweight="bold", color="#c0392b")
            ax2_twin.tick_params(axis="y", labelcolor="#c0392b")
            ax2_twin.set_ylim(-0.05, 1.05)

    plt.tight_layout()
    plt.savefig("sar_network_and_mission_performance.png")
    plt.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Final Swarm SAR Mission Validator")
    parser.add_argument("--world", type=str, default="ground_truth_world.json", help="Ground truth world JSON (default: ground_truth_world.json)")
    parser.add_argument("--swarm", type=str, default="swarm_mission_output.json", help="Swarm mission output JSON (default: swarm_mission_output.json)")
    parser.add_argument("--thresh", type=float, default=18.0, help="Spatial matching radius tolerance in meters (default: 18.0)")
    args = parser.parse_args()

    run_validation(world_json=args.world, swarm_json=args.swarm, match_distance_thresh=args.thresh)
