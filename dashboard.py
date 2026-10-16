import os
import glob
import random
import time
import json
import cv2
import numpy as np
import pandas as pd
from PIL import Image
import gradio as gr

from rgbt_detector import RGBTDetector
from sar_world import SARWorld
from simulate_swarm_mission import SwarmSimulation
from validate_swarm_mission import run_validation

# Initialize Detector
MODEL_PATH = "best.pt"
detector = RGBTDetector(model_path=MODEL_PATH, conf_thresh=0.20)

VAL_IMAGES_DIR = "/home/devesh/Downloads/YOLO_RGBT_4CH_Mini/images/val"
val_images = glob.glob(os.path.join(VAL_IMAGES_DIR, "*.png")) if os.path.exists(VAL_IMAGES_DIR) else []


# =====================================================================
# DATA LOADING & REFRESH LOGIC
# =====================================================================
def get_files_max_mtime():
    files = [
        "mission_validation_report.json",
        "sar_mission_spatial_validation.png",
        "sar_network_and_mission_performance.png",
        "metrics_network.csv",
        "metrics_mission.csv"
    ]
    mtimes = [os.path.getmtime(f) for f in files if os.path.exists(f)]
    return max(mtimes) if mtimes else 0.0


def load_validation_summary_html():
    report_file = "mission_validation_report.json"
    if not os.path.exists(report_file):
        return "<p style='color: #888;'>No validation data found. Run a simulation first.</p>"

    mtime = os.path.getmtime(report_file)
    time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))

    with open(report_file, "r") as f:
        rep = json.load(f)
    s = rep.get("summary", {})

    coverage = s.get("area_coverage_pct", 0)
    ttfd = s.get("ttfd_sec", 0)
    gt_total = s.get("ground_truth_targets_in_surveyed", 0)
    tp = s.get("true_positives", 0)
    fn = s.get("false_negatives", 0)
    fp = s.get("false_positives", 0)
    recall = s.get("recall", 0) * 100
    precision = s.get("precision", 0) * 100
    f1 = s.get("f1_score", 0)
    mean_err = s.get("mean_localization_error_m", 0)
    rmse = s.get("rmse_localization_error_m", 0)
    pdr = s.get("pdr_pct", 0)
    consensus = s.get("swarm_consensus_pct", 0)

    html = f"""
    <div style="margin-bottom: 8px; font-size: 0.9em; color: #888; display: flex; justify-content: space-between; align-items: center;">
        <span><strong>Live Mission Sync:</strong> Report generated at <code style="color: #4CAF50;">{time_str}</code></span>
        <span style="background: #2e7d32; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 0.8em;">AUTO-SYNC ACTIVE</span>
    </div>
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 20px;">
        <div style="background: #1e1e24; padding: 14px; border-radius: 8px; border-left: 4px solid #4CAF50; box-shadow: 0 2px 5px rgba(0,0,0,0.3);">
            <div style="color: #aaa; font-size: 0.85em; text-transform: uppercase;">Area Coverage</div>
            <div style="font-size: 1.8em; font-weight: bold; color: #4CAF50;">{coverage}%</div>
            <div style="color: #777; font-size: 0.8em;">Full Arena Swept</div>
        </div>
        <div style="background: #1e1e24; padding: 14px; border-radius: 8px; border-left: 4px solid #2196F3; box-shadow: 0 2px 5px rgba(0,0,0,0.3);">
            <div style="color: #aaa; font-size: 0.85em; text-transform: uppercase;">Mission Recall</div>
            <div style="font-size: 1.8em; font-weight: bold; color: #2196F3;">{recall:.1f}%</div>
            <div style="color: #777; font-size: 0.8em;">{tp} TP / {gt_total} GT Victims</div>
        </div>
        <div style="background: #1e1e24; padding: 14px; border-radius: 8px; border-left: 4px solid #FF9800; box-shadow: 0 2px 5px rgba(0,0,0,0.3);">
            <div style="color: #aaa; font-size: 0.85em; text-transform: uppercase;">Mean Loc Error</div>
            <div style="font-size: 1.8em; font-weight: bold; color: #FF9800;">{mean_err} m</div>
            <div style="color: #777; font-size: 0.8em;">RMSE: {rmse}m Precision</div>
        </div>
        <div style="background: #1e1e24; padding: 14px; border-radius: 8px; border-left: 4px solid #9C27B0; box-shadow: 0 2px 5px rgba(0,0,0,0.3);">
            <div style="color: #aaa; font-size: 0.85em; text-transform: uppercase;">Network PDR</div>
            <div style="font-size: 1.8em; font-weight: bold; color: #9C27B0;">{pdr:.1f}%</div>
            <div style="color: #777; font-size: 0.8em;">QoS 1 Mesh Delivery</div>
        </div>
        <div style="background: #1e1e24; padding: 14px; border-radius: 8px; border-left: 4px solid #00BCD4; box-shadow: 0 2px 5px rgba(0,0,0,0.3);">
            <div style="color: #aaa; font-size: 0.85em; text-transform: uppercase;">Swarm Consensus</div>
            <div style="font-size: 1.8em; font-weight: bold; color: #00BCD4;">{consensus:.1f}%</div>
            <div style="color: #777; font-size: 0.8em;">Shared Map Sync</div>
        </div>
        <div style="background: #1e1e24; padding: 14px; border-radius: 8px; border-left: 4px solid #E91E63; box-shadow: 0 2px 5px rgba(0,0,0,0.3);">
            <div style="color: #aaa; font-size: 0.85em; text-transform: uppercase;">Time to 1st Target</div>
            <div style="font-size: 1.8em; font-weight: bold; color: #E91E63;">{ttfd} s</div>
            <div style="color: #777; font-size: 0.8em;">Rapid TTFD Detection</div>
        </div>
    </div>
    """
    return html


def load_matches_dataframe():
    report_file = "mission_validation_report.json"
    if not os.path.exists(report_file):
        return pd.DataFrame(columns=["Target ID", "GT Pos (X, Y)", "Detected Pos (X, Y)", "Error (m)", "Confidence", "Detected By", "Status"])

    with open(report_file, "r") as f:
        rep = json.load(f)
    matches = rep.get("matches", [])
    
    rows = []
    for m in matches:
        rows.append({
            "Target ID": m["gt_id"],
            "GT Pos (X, Y)": f"({m['gt_pos'][0]:.1f}, {m['gt_pos'][1]:.1f})",
            "Detected Pos (X, Y)": f"({m['rep_pos'][0]:.1f}, {m['rep_pos'][1]:.1f})",
            "Error (m)": m["error_m"],
            "Confidence": f"{m['conf']:.2f}",
            "Detected By": f"UAV {m['detected_by']}",
            "Status": "✅ True Positive"
        })
    return pd.DataFrame(rows)


def load_network_dataframe():
    csv_file = "metrics_network.csv"
    if not os.path.exists(csv_file):
        return pd.DataFrame()
    df = pd.read_csv(csv_file)
    df_recent = df.tail(100).copy()
    df_recent["Status"] = df_recent["delivered"].apply(lambda x: "✅ Delivered" if x == 1 else "⚠️ Buffered (PER Drop)")
    df_recent = df_recent[["sim_time", "src_uav", "dst_uav", "distance_m", "snr_db", "per", "Status"]]
    df_recent.columns = ["Time (s)", "Source", "Destination", "Distance (m)", "SNR (dB)", "PER", "RF Status"]
    return df_recent


def load_images_clean():
    img_map = Image.open("sar_mission_spatial_validation.png") if os.path.exists("sar_mission_spatial_validation.png") else None
    img_perf = Image.open("sar_network_and_mission_performance.png") if os.path.exists("sar_network_and_mission_performance.png") else None
    return img_map, img_perf


def check_and_auto_refresh(last_mtime):
    current_mtime = get_files_max_mtime()
    if current_mtime > last_mtime or last_mtime == 0.0:
        kpi_html = load_validation_summary_html()
        img_map, img_perf = load_images_clean()
        df_matches = load_matches_dataframe()
        df_net = load_network_dataframe()
        time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_mtime)) if current_mtime else "None"
        sync_msg = f"🟢 Live Auto-Sync Active • Data as of {time_str}"
        return kpi_html, kpi_html, img_map, img_perf, df_matches, df_net, sync_msg, current_mtime
    else:
        return gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(), last_mtime


def force_manual_refresh():
    return check_and_auto_refresh(0.0)


# =====================================================================
# VISION SCANNING CALLBACK
# =====================================================================
def run_vision_inference(view_mode, conf_thresh):
    if not detector.is_ready():
        return None, "⚠️ Error: 'best.pt' weights not found in project root."
    if not val_images:
        return None, "⚠️ Error: No validation images found in dataset directory."

    img_source = random.choice(val_images)
    img_name = os.path.basename(img_source)

    try:
        t0 = time.time()
        detections, img_bgra = detector.detect(img_source, conf=conf_thresh)
        elapsed_ms = (time.time() - t0) * 1000

        mode_key = "multispectral" if "Panoramic" in view_mode else ("thermal" if "Thermal" in view_mode else "rgb")
        annotated_img = detector.render_annotated(img_bgra, detections, mode=mode_key)

        arch_str = "YOLOv8-P2 (Stride 4)" if detector.is_p2 else "YOLOv8-Standard"
        cls_summary = ", ".join([f"{d['class_name']}({d['conf']:.2f})" for d in detections]) if detections else "None"

        status = (
            f"✅ Frame: {img_name} | Arch: {arch_str} | Latency: {elapsed_ms:.1f}ms\n"
            f"🎯 Targets Detected: {len(detections)} | Detections: [{cls_summary}]\n"
            f"📡 Active Class ({detector.nc}): {list(detector.names.values())}"
        )
        return annotated_img, status
    except Exception as e:
        return None, f"❌ Inference Error: {str(e)}"


def run_live_simulation(num_drones, arena_size, conf_thresh, duration):
    try:
        sim = SwarmSimulation(num_drones=int(num_drones), arena_size=float(arena_size),
                              grid_dim=5, model_path="best.pt", conf_thresh=float(conf_thresh), seed=42)
        sim.run(max_sim_seconds=int(duration), dt=1.0)
        run_validation()

        kpi_html = load_validation_summary_html()
        img_map, img_perf = load_images_clean()
        df_matches = load_matches_dataframe()
        df_net = load_network_dataframe()
        mtime = get_files_max_mtime()
        time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))
        sync_msg = f"🟢 Live Auto-Sync Active • Data as of {time_str}"
        status_msg = f"✅ New mission completed & validated! Swarm: {num_drones} UAVs, Arena: {arena_size}m, τ: {conf_thresh}"
        return kpi_html, kpi_html, img_map, img_perf, df_matches, df_net, sync_msg, mtime, status_msg
    except Exception as e:
        return gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(), 0.0, f"❌ Simulation error: {str(e)}"


# =====================================================================
# GRADIO APPLICATION
# =====================================================================
custom_css = """
.container { max-width: 1400px; margin: auto; padding-top: 10px; }
.output-image { border-radius: 8px; border: 2px solid #333; }
.stat-box { font-family: monospace; font-size: 0.9em; }
"""

arch_badge = "YOLOv8n-P2 Multispectral (Stride 4)" if detector.is_p2 else "YOLOv8 4-Channel"

with gr.Blocks(theme=gr.themes.Monochrome(), css=custom_css, title="FlyNetSim Swarm SAR Control Station") as demo:
    # State tracking file modification times for zero-flicker auto-refresh
    state_mtime = gr.State(value=0.0)

    # Auto-Refresh Timer: checks every 2 seconds if a simulation finished
    timer = gr.Timer(value=2.0)

    with gr.Column(elem_classes="container"):
        gr.Markdown(
            f"""
            <div style="text-align: center; padding-bottom: 5px;">
                <h1 style="font-size: 2.5em; margin-bottom: 2px;">🚁 Autonomous UAV Swarm SAR Control Station & Dashboard</h1>
                <h3 style="font-weight: normal; color: #888; margin-top: 0;">
                    4-Channel Early-Fusion (Visible RGB + Thermal Infrared) &bull; 
                    <span style="color: #4CAF50; font-weight: bold;">{arch_badge}</span> &bull; 
                    Decentralized FANET Mesh
                </h3>
            </div>
            """
        )

        with gr.Row():
            sync_indicator = gr.Markdown("🟢 Initializing Live Data Sync...")
            btn_force_refresh = gr.Button("🔄 Refresh Latest Mission Data Now", variant="secondary", size="sm")

        with gr.Tabs():
            # -------------------------------------------------------------
            # TAB 1: LIVE MULTISPECTRAL CAMERA & AI VISION
            # -------------------------------------------------------------
            with gr.TabItem("🛰️ Live Multispectral Camera & AI Vision"):
                gr.Markdown("Test individual 4-channel image frames using the Early-Fusion YOLOv8-P2 model.")
                with gr.Row():
                    output_cam_img = gr.Image(
                        label="Multispectral Camera Feed",
                        elem_classes="output-image",
                        height=540,
                        show_label=False
                    )

                with gr.Row():
                    with gr.Column(scale=2):
                        btn_scan = gr.Button("🔍 Scan Next Sector (Random Drone Sample)", variant="primary", size="lg")
                        view_mode = gr.Radio(
                            choices=["Multispectral Panoramic (RGB | Thermal | Fused)", "Visible Channel (RGB)", "Thermal Infrared (LWIR)"],
                            value="Multispectral Panoramic (RGB | Thermal | Fused)",
                            label="Display Mode"
                        )
                        conf_slider = gr.Slider(minimum=0.05, maximum=0.90, value=0.20, step=0.05, label="Detection Confidence Threshold (τ)")

                    with gr.Column(scale=2):
                        cam_status = gr.Textbox(
                            label="Sensor Telemetry",
                            lines=4,
                            interactive=False,
                            elem_classes="stat-box",
                            placeholder="System ready. Click 'Scan Next Sector' to run inference..."
                        )

                btn_scan.click(
                    fn=run_vision_inference,
                    inputs=[view_mode, conf_slider],
                    outputs=[output_cam_img, cam_status]
                )

            # -------------------------------------------------------------
            # TAB 2: POST-MISSION SPATIAL VALIDATION MAP
            # -------------------------------------------------------------
            with gr.TabItem("🗺️ Post-Mission Spatial Map & Victim Matches"):
                gr.Markdown("### Swarm Spatial Exploration & Victim Verification against Ground Truth")
                kpi_banner_1 = gr.HTML(value="Loading...")

                with gr.Row():
                    spatial_map_img = gr.Image(
                        label="2D Arena Spatial Validation Map",
                        height=580,
                        elem_classes="output-image"
                    )

                gr.Markdown("### Target-by-Target Verification Table (Ground Truth vs Swarm Coordinates)")
                table_matches = gr.DataFrame(
                    label="Victim Coordinate Proximity Matching",
                    interactive=False
                )

            # -------------------------------------------------------------
            # TAB 3: FANET RF MESH & PROPAGATION DYNAMICS
            # -------------------------------------------------------------
            with gr.TabItem("📡 FANET RF Mesh & Propagation Dynamics"):
                gr.Markdown("### Inter-UAV Radio Physics, Signal-to-Noise Ratio (SNR), and QoS 1 Link Recovery")
                kpi_banner_2 = gr.HTML(value="Loading...")

                with gr.Row():
                    perf_curves_img = gr.Image(
                        label="RF Channel Physics & Mission Exploration Curves",
                        height=520,
                        elem_classes="output-image"
                    )

                gr.Markdown("### Real-Time P2P Packet Dissemination Stream (Recent 100 Mesh Alerts)")
                table_network = gr.DataFrame(
                    label="RF Transmission Telemetry Log",
                    interactive=False
                )

            # -------------------------------------------------------------
            # TAB 4: ACADEMIC BENCHMARK & LIVE MISSION RUNNER
            # -------------------------------------------------------------
            with gr.TabItem("🔬 Mission Simulator & Parameter Sweep"):
                gr.Markdown("### Execute a New Swarm Mission & Generate Fresh Paper Data")
                with gr.Row():
                    with gr.Column():
                        sim_drones_input = gr.Slider(minimum=2, maximum=8, value=3, step=1, label="Swarm Size (Number of UAVs)")
                        sim_arena_input = gr.Slider(minimum=200, maximum=600, value=400, step=50, label="Search Arena Width/Height (meters)")
                    with gr.Column():
                        sim_conf_input = gr.Slider(minimum=0.05, maximum=0.70, value=0.20, step=0.05, label="Vision Confidence Threshold (τ)")
                        sim_dur_input = gr.Slider(minimum=60, maximum=300, value=180, step=30, label="Simulation Duration (seconds)")

                btn_run_sim = gr.Button("🚀 Launch Swarm Mission & Re-Calculate Benchmark", variant="primary", size="lg")
                sim_result_status = gr.Textbox(label="Mission Execution Status", interactive=False)

                btn_run_sim.click(
                    fn=run_live_simulation,
                    inputs=[sim_drones_input, sim_arena_input, sim_conf_input, sim_dur_input],
                    outputs=[kpi_banner_1, kpi_banner_2, spatial_map_img, perf_curves_img, table_matches, table_network, sync_indicator, state_mtime, sim_result_status]
                )

    # 1. On page load: immediately load latest files from disk
    demo.load(
        fn=force_manual_refresh,
        outputs=[kpi_banner_1, kpi_banner_2, spatial_map_img, perf_curves_img, table_matches, table_network, sync_indicator, state_mtime]
    )

    # 2. Timer tick: every 2 seconds, check if files changed on disk and auto-refresh with zero flicker
    timer.tick(
        fn=check_and_auto_refresh,
        inputs=[state_mtime],
        outputs=[kpi_banner_1, kpi_banner_2, spatial_map_img, perf_curves_img, table_matches, table_network, sync_indicator, state_mtime]
    )

    # 3. Manual refresh button click
    btn_force_refresh.click(
        fn=force_manual_refresh,
        outputs=[kpi_banner_1, kpi_banner_2, spatial_map_img, perf_curves_img, table_matches, table_network, sync_indicator, state_mtime]
    )

if __name__ == "__main__":
    print("\n" + "=" * 65)
    print("🚀 STARTING MULTISPECTRAL DRONE SWARM CONTROL STATION & DASHBOARD")
    print(f"Model path: {MODEL_PATH} (exists: {os.path.exists(MODEL_PATH)})")
    print("Open http://localhost:7860 in your browser.")
    print("=" * 65 + "\n")
    demo.launch(server_name="0.0.0.0", server_port=7860)
