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
        return "<p style='color: #888;'>No mission data available yet.</p>"

    mtime = os.path.getmtime(report_file)
    time_str = time.strftime('%H:%M:%S', time.localtime(mtime))

    with open(report_file, "r") as f:
        rep = json.load(f)
    s = rep.get("summary", {})

    coverage = s.get("area_coverage_pct", 0)
    ttfd = s.get("ttfd_sec", 0)
    gt_total = s.get("ground_truth_targets_in_surveyed", 0)
    tp = s.get("true_positives", 0)
    recall = s.get("recall", 0) * 100
    mean_err = s.get("mean_localization_error_m", 0)
    pdr = s.get("pdr_pct", 0)
    consensus = s.get("swarm_consensus_pct", 0)

    fail_html = ""
    failed_uav_info = rep.get("failed_uav_info")
    if failed_uav_info:
        uav_id = failed_uav_info.get("uav_id")
        t_fail = failed_uav_info.get("time")
        c_pos = failed_uav_info.get("crash_pos", [0, 0])
        aband = failed_uav_info.get("abandoned_sectors", [])
        fail_html = f"""
        <div style="background: #252528; border-left: 3px solid #b54747; padding: 10px 14px; margin-bottom: 16px; border-radius: 4px; font-size: 0.9em; color: #ccc;">
            <strong>Drone {uav_id} stopped at {t_fail}s</strong> at coordinates ({c_pos[0]:.0f}m, {c_pos[1]:.0f}m). Remaining sectors {aband} were transferred to Drone 3.
        </div>
        """

    html = f"""
    {fail_html}
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 18px;">
        <div style="background: #18181b; border: 1px solid #27272a; padding: 12px; border-radius: 6px;">
            <div style="color: #71717a; font-size: 0.78em; text-transform: uppercase; letter-spacing: 0.04em;">Area Covered</div>
            <div style="font-size: 1.5em; font-weight: 600; color: #f4f4f5; margin-top: 4px;">{coverage}%</div>
        </div>
        <div style="background: #18181b; border: 1px solid #27272a; padding: 12px; border-radius: 6px;">
            <div style="color: #71717a; font-size: 0.78em; text-transform: uppercase; letter-spacing: 0.04em;">Targets Found</div>
            <div style="font-size: 1.5em; font-weight: 600; color: #f4f4f5; margin-top: 4px;">{tp} <span style="font-size: 0.6em; color: #71717a; font-weight: normal;">/ {gt_total}</span></div>
        </div>
        <div style="background: #18181b; border: 1px solid #27272a; padding: 12px; border-radius: 6px;">
            <div style="color: #71717a; font-size: 0.78em; text-transform: uppercase; letter-spacing: 0.04em;">Location Error</div>
            <div style="font-size: 1.5em; font-weight: 600; color: #f4f4f5; margin-top: 4px;">{mean_err} m</div>
        </div>
        <div style="background: #18181b; border: 1px solid #27272a; padding: 12px; border-radius: 6px;">
            <div style="color: #71717a; font-size: 0.78em; text-transform: uppercase; letter-spacing: 0.04em;">Detection Rate</div>
            <div style="font-size: 1.5em; font-weight: 600; color: #f4f4f5; margin-top: 4px;">{recall:.1f}%</div>
        </div>
        <div style="background: #18181b; border: 1px solid #27272a; padding: 12px; border-radius: 6px;">
            <div style="color: #71717a; font-size: 0.78em; text-transform: uppercase; letter-spacing: 0.04em;">Delivered</div>
            <div style="font-size: 1.5em; font-weight: 600; color: #f4f4f5; margin-top: 4px;">{pdr:.1f}%</div>
        </div>
        <div style="background: #18181b; border: 1px solid #27272a; padding: 12px; border-radius: 6px;">
            <div style="color: #71717a; font-size: 0.78em; text-transform: uppercase; letter-spacing: 0.04em;">Swarm Sync</div>
            <div style="font-size: 1.5em; font-weight: 600; color: #f4f4f5; margin-top: 4px;">{consensus:.1f}%</div>
        </div>
    </div>
    """
    return html


def load_matches_dataframe():
    report_file = "mission_validation_report.json"
    if not os.path.exists(report_file):
        return pd.DataFrame(columns=["Target ID", "Actual Location", "Detected Location", "Error (m)", "Detected By", "Status"])

    with open(report_file, "r") as f:
        rep = json.load(f)
    matches = rep.get("matches", [])
    
    rows = []
    for m in matches:
        rows.append({
            "Target ID": m["gt_id"],
            "Actual Location": f"({m['gt_pos'][0]:.1f}, {m['gt_pos'][1]:.1f})",
            "Detected Location": f"({m['rep_pos'][0]:.1f}, {m['rep_pos'][1]:.1f})",
            "Error (m)": m["error_m"],
            "Detected By": f"Drone {m['detected_by']}",
            "Status": "Confirmed"
        })
    return pd.DataFrame(rows)


def load_network_dataframe():
    csv_file = "metrics_network.csv"
    if not os.path.exists(csv_file):
        return pd.DataFrame(columns=["Time (s)", "From", "To", "Distance (m)", "Signal (dB)", "Status"])
    df = pd.read_csv(csv_file)
    df_recent = df.tail(80).copy()
    df_recent["Status"] = df_recent["delivered"].apply(lambda x: "Delivered" if x == 1 else "Buffered")
    df_recent = df_recent[["sim_time", "src_uav", "dst_uav", "distance_m", "snr_db", "Status"]]
    df_recent.columns = ["Time (s)", "From", "To", "Distance (m)", "Signal (dB)", "Status"]
    return df_recent


def load_images_clean():
    img_map = "sar_mission_spatial_validation.png" if os.path.exists("sar_mission_spatial_validation.png") else None
    img_perf = "sar_network_and_mission_performance.png" if os.path.exists("sar_network_and_mission_performance.png") else None
    return img_map, img_perf


def check_and_auto_refresh(last_mtime):
    current_mtime = get_files_max_mtime()
    if current_mtime > last_mtime or last_mtime == 0.0:
        kpi_html = load_validation_summary_html()
        img_map, img_perf = load_images_clean()
        df_matches = load_matches_dataframe()
        df_net = load_network_dataframe()
        time_str = time.strftime('%H:%M:%S', time.localtime(current_mtime)) if current_mtime else "None"
        sync_msg = f"Last updated: {time_str}"
        return kpi_html, kpi_html, img_map, img_perf, df_matches, df_net, sync_msg, current_mtime
    else:
        return gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(), last_mtime


def force_manual_refresh():
    return check_and_auto_refresh(0.0)


# =====================================================================
# CAMERA INFERENCE CALLBACK
# =====================================================================
def run_vision_inference(view_mode, conf_thresh):
    if not detector.is_ready():
        return None, "Error: Weights file 'best.pt' not found."
    if not val_images:
        return None, "Error: No validation images found."

    img_source = random.choice(val_images)
    img_name = os.path.basename(img_source)

    try:
        t0 = time.time()
        detections, img_bgra = detector.detect(img_source, conf=conf_thresh)
        elapsed_ms = (time.time() - t0) * 1000

        mode_key = "multispectral" if "Composite" in view_mode else ("thermal" if "Thermal" in view_mode else "rgb")
        annotated_img = detector.render_annotated(img_bgra, detections, mode=mode_key)

        det_str = f"{len(detections)} target(s) located" if detections else "No targets detected"
        status = f"Frame: {img_name}  |  Processing time: {elapsed_ms:.0f} ms  |  Result: {det_str}"
        return annotated_img, status
    except Exception as e:
        return None, f"Processing error: {str(e)}"


def run_live_simulation(num_drones, arena_size, conf_thresh, duration, fail_drone="None", fail_time=80.0):
    try:
        fail_id = int(fail_drone) if fail_drone and fail_drone != "None" else None
        sim = SwarmSimulation(num_drones=int(num_drones), arena_size=float(arena_size),
                              grid_dim=5, model_path="best.pt", conf_thresh=float(conf_thresh),
                              seed=42, fail_drone_id=fail_id, fail_time=float(fail_time))
        sim.run(max_sim_seconds=int(duration), dt=1.0)
        run_validation()

        kpi_html = load_validation_summary_html()
        img_map, img_perf = load_images_clean()
        df_matches = load_matches_dataframe()
        df_net = load_network_dataframe()
        mtime = get_files_max_mtime()
        time_str = time.strftime('%H:%M:%S', time.localtime(mtime))
        sync_msg = f"Last updated: {time_str}"
        status_msg = f"Mission complete: {num_drones} drones, {arena_size}m area, duration {duration}s."
        return kpi_html, kpi_html, img_map, img_perf, df_matches, df_net, sync_msg, mtime, status_msg
    except Exception as e:
        return gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(), 0.0, f"Error: {str(e)}"


# =====================================================================
# USER INTERFACE
# =====================================================================
custom_css = """
.container { max-width: 1200px; margin: auto; padding: 12px 16px; }
.output-box { border-radius: 6px; border: 1px solid #27272a; }
"""

with gr.Blocks(theme=gr.themes.Soft(primary_hue="zinc", secondary_hue="zinc"), css=custom_css, title="Drone Swarm SAR") as demo:
    state_mtime = gr.State(value=0.0)
    timer = gr.Timer(value=2.0)

    with gr.Column(elem_classes="container"):
        # Header
        with gr.Row():
            with gr.Column(scale=5):
                gr.Markdown("## Drone Swarm Search and Rescue")
                gr.Markdown("Autonomous aerial search and mapping console.")
            with gr.Column(scale=2):
                sync_indicator = gr.Markdown("Status: Initializing...", elem_classes="text-muted")
                btn_force_refresh = gr.Button("Refresh Data", variant="secondary", size="sm")

        with gr.Tabs():
            # -------------------------------------------------------------
            # TAB 1: MISSION MAP
            # -------------------------------------------------------------
            with gr.TabItem("Mission Map"):
                kpi_banner_1 = gr.HTML(value="Loading metrics...")

                with gr.Row():
                    spatial_map_img = gr.Image(
                        label="Search Area Map and Flight Paths",
                        height=620,
                        elem_classes="output-box"
                    )

                gr.Markdown("#### Located Targets")
                table_matches = gr.DataFrame(
                    interactive=False
                )

            # -------------------------------------------------------------
            # TAB 2: LIVE CAMERA
            # -------------------------------------------------------------
            with gr.TabItem("Camera Feed"):
                gr.Markdown("#### Onboard Camera View")
                with gr.Row():
                    output_cam_img = gr.Image(
                        show_label=False,
                        elem_classes="output-box",
                        height=500
                    )

                with gr.Row():
                    with gr.Column(scale=2):
                        btn_scan = gr.Button("Capture Frame", variant="primary")
                        view_mode = gr.Radio(
                            choices=["Composite (Color & Thermal)", "Visible", "Thermal"],
                            value="Composite (Color & Thermal)",
                            label="Channel View"
                        )
                        conf_slider = gr.Slider(minimum=0.05, maximum=0.80, value=0.20, step=0.05, label="Detection Threshold")

                    with gr.Column(scale=2):
                        cam_status = gr.Textbox(
                            label="Camera Status",
                            lines=3,
                            interactive=False,
                            placeholder="Click 'Capture Frame' to view image..."
                        )

                btn_scan.click(
                    fn=run_vision_inference,
                    inputs=[view_mode, conf_slider],
                    outputs=[output_cam_img, cam_status]
                )

            # -------------------------------------------------------------
            # TAB 3: NETWORK STATUS
            # -------------------------------------------------------------
            with gr.TabItem("Network Status"):
                kpi_banner_2 = gr.HTML(value="Loading metrics...")

                with gr.Row():
                    perf_curves_img = gr.Image(
                        label="Signal and Delivery Analysis",
                        height=500,
                        elem_classes="output-box"
                    )

                gr.Markdown("#### Transmission Activity")
                table_network = gr.DataFrame(
                    interactive=False
                )

            # -------------------------------------------------------------
            # TAB 4: RUN SIMULATION
            # -------------------------------------------------------------
            with gr.TabItem("Run Mission"):
                gr.Markdown("#### Mission Parameters")
                with gr.Row():
                    with gr.Column():
                        sim_drones_input = gr.Slider(minimum=2, maximum=12, value=10, step=1, label="Number of Drones")
                        sim_arena_input = gr.Slider(minimum=400, maximum=5000, value=5000, step=200, label="Search Area Size (meters)")
                        sim_fail_drone = gr.Dropdown(choices=["None", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"], value="4", label="Simulate Drone Failure")
                    with gr.Column():
                        sim_conf_input = gr.Slider(minimum=0.05, maximum=0.70, value=0.20, step=0.05, label="Detection Threshold")
                        sim_dur_input = gr.Slider(minimum=60, maximum=320, value=300, step=20, label="Mission Duration (seconds)")
                        sim_fail_time = gr.Slider(minimum=10, maximum=200, value=80, step=5, label="Failure Time (seconds)")

                btn_run_sim = gr.Button("Start Simulation", variant="primary", size="lg")
                sim_result_status = gr.Textbox(label="Status", interactive=False)

                btn_run_sim.click(
                    fn=run_live_simulation,
                    inputs=[sim_drones_input, sim_arena_input, sim_conf_input, sim_dur_input, sim_fail_drone, sim_fail_time],
                    outputs=[kpi_banner_1, kpi_banner_2, spatial_map_img, perf_curves_img, table_matches, table_network, sync_indicator, state_mtime, sim_result_status]
                )

    # Auto-refresh and manual triggers
    demo.load(
        fn=force_manual_refresh,
        outputs=[kpi_banner_1, kpi_banner_2, spatial_map_img, perf_curves_img, table_matches, table_network, sync_indicator, state_mtime]
    )

    timer.tick(
        fn=check_and_auto_refresh,
        inputs=[state_mtime],
        outputs=[kpi_banner_1, kpi_banner_2, spatial_map_img, perf_curves_img, table_matches, table_network, sync_indicator, state_mtime]
    )

    btn_force_refresh.click(
        fn=force_manual_refresh,
        outputs=[kpi_banner_1, kpi_banner_2, spatial_map_img, perf_curves_img, table_matches, table_network, sync_indicator, state_mtime]
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
