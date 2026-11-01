# Autonomous Multi-Modal UAV Swarms for Post-Disaster Search-and-Rescue (SAR)
## Experimental Framework, Evaluation Metrics, and Data Collection Specification

---

## 1. Executive Overview

This document specifies the complete experimental framework and evaluation metrics for our research paper on **Autonomous Multispectral UAV Swarms in Post-Disaster Search and Rescue**. 

The evaluation is organized across three hierarchical layers, capped by a cross-layer synergy analysis:
1. **Perception Layer**: 4-Channel Early-Fusion YOLOv8-P2 Multispectral Object Detection.
2. **Communication Layer**: Decentralized Flying Ad-Hoc Network (FANET) with Log-Distance RF Physics & DMLT EdgeBroker.
3. **Mission Execution Layer**: Swarm Spatial Dynamics, Area Coverage, and Target Consensus.
4. **Cross-Layer Coupling**: Trade-off between detection confidence, false-positive alerts, and RF channel saturation.

---

## 2. Layer 1: Perception & Multispectral Vision Benchmark

Evaluates the effectiveness of early-fusion multispectral sensing (RGB + LWIR Thermal) and the high-resolution P2 stride-4 feature pyramid in aerial search missions.

### 2.1 Independent Variables (Control Parameters)
| Parameter | Symbol | Test Values | Description |
| :--- | :---: | :---: | :--- |
| **Input Modality** | $M$ | `RGB-only`, `Thermal-only`, `4-Channel Early Fusion (RGB+T)` | Compares single-modality baselines against early fusion. |
| **Feature Pyramid** | $A$ | `YOLOv8n (P3-P5)`, `YOLOv8n-P2 (P2-P5)` | Compares standard stride-8/16/32 pyramid with stride-4 high-res head. |
| **Confidence Threshold** | $\tau_{\text{conf}}$ | $0.05 \text{ to } 0.85$ (step $0.05$) | Detection sensitivity operating point. |
| **Target Scale** | $S$ | $\text{Small } (< 32^2 \text{ px})$, $\text{Medium } (32^2 - 96^2 \text{ px})$, $\text{Large } (> 96^2 \text{ px})$ | Categorized by target pixel footprint from drone altitude. |
| **Illumination Condition** | $I$ | `Daylight / Unobstructed`, `Shadow / Camouflage`, `Thermal Contrast / Clutter` | Evaluates environmental edge cases in disaster debris. |

### 2.2 Dependent Metrics (Mathematical Definitions)
* **Precision ($P$)**:
  $$P = \frac{TP}{TP + FP}$$
* **Recall ($R$)**:
  $$R = \frac{TP}{TP + FN}$$
* **Mean Average Precision at IoU 0.50 ($\text{mAP}_{50}$)**:
  $$\text{mAP}_{50} = \int_{0}^{1} P(R) \, dR \quad \text{at } \text{IoU} \ge 0.50$$
* **Small Target Average Precision ($\text{AP}_S$)**:
  $$\text{AP}_S = \text{mAP evaluation restricted strictly to targets where } \text{area} < 32^2 \text{ pixels}$$
  *Hypothesis: The P2 stride-4 head provides a $> 15\%$ boost in $\text{AP}_S$ compared to baseline YOLOv8.*
* **F1-Score Harmonic Mean ($F_1$)**:
  $$F_1 = 2 \cdot \frac{P \cdot R}{P + R}$$
* **Inference Latency ($T_{\text{inf}}$)**:
  Mean forward-pass execution time in milliseconds ($\text{ms}$) per frame across CPU (Intel x86) and edge GPU (NVIDIA Jetson / CUDA).

---

## 3. Layer 2: RF Communication & Edge Broker Resilience

Evaluates decentralized peer-to-peer telemetry and alert dissemination over an unreliable wireless link governed by RF path loss, shadow fading, and dynamic packet loss.

### 3.1 RF Physical Channel Formulation
* **Free Space Path Loss with Log-Distance Shadow Fading**:
  $$PL(d) = 20 \log_{10}(d) + 20 \log_{10}(f) - 27.55 + X_\sigma$$
  where:
  * $d$ = 3D Euclidean distance between UAVs in meters ($\text{m}$).
  * $f$ = Carrier frequency ($5000 \text{ MHz}$ ISM band).
  * $X_\sigma \sim \mathcal{N}(0, \sigma^2)$ = Zero-mean Gaussian random variable modeling shadow fading ($\sigma = 4.0 \text{ dB}$ for open air, $\sigma = 7.5 \text{ dB}$ in post-disaster obstacle clutter).
* **Signal-to-Noise Ratio ($\text{SNR}$)**:
  $$\text{SNR}(d) = P_{\text{tx}} + G_{\text{tx}} + G_{\text{rx}} - PL(d) - P_{\text{noise}}$$
  where $P_{\text{tx}} = 30 \text{ dBm} \, (1 \text{W})$, $G_{\text{tx}} = G_{\text{rx}} = 2.15 \text{ dBi}$, $P_{\text{noise}} = -95 \text{ dBm}$.
* **Dynamic Packet Error Rate ($\text{PER}$)**:
  $$\text{PER}(\text{SNR}) = \frac{1}{1 + e^{k \cdot (\text{SNR} - \text{SNR}_{\text{thresh}})}}$$
  where $k = 0.5$, $\text{SNR}_{\text{thresh}} = 10 \text{ dB}$.

### 3.2 Independent Variables (Control Parameters)
| Parameter | Symbol | Test Values | Description |
| :--- | :---: | :---: | :--- |
| **Inter-UAV Distance** | $d$ | $10\text{m} \text{ to } 350\text{m}$ (step $10\text{m}$) | Spatial baseline distance. |
| **Obstacle Shadowing** | $\sigma$ | `Low (4.0 dB)` vs `High / Disaster Clutter (7.5 dB)` | Multipath and building debris blockage. |
| **Routing / QoS Protocol** | $\pi$ | `Baseline QoS 0 (Unbuffered Flood)` vs `EdgeBroker QoS 1 (DMLT + Store-and-Forward)` | Protocol resilience strategy. |
| **Swarm Density** | $N$ | $3, 5, 8, 12 \text{ UAVs}$ | Total active nodes in the swarm network. |

### 3.3 Dependent Metrics
* **Packet Delivery Ratio ($\text{PDR}$)**:
  $$\text{PDR} = \frac{\sum \text{Packets Received by Intended Targets}}{\sum \text{Packets Published by Source UAVs}} \times 100\%$$
* **End-to-End Alert Dissemination Latency ($T_{\text{alert}}$)**:
  Time in milliseconds ($\text{ms}$) from target detection by UAV $i$ until all reachable swarm peers receive and parse the alert.
* **QoS 1 Queue Depth & Flush Recovery Time ($T_{\text{flush}}$)**:
  Duration required to successfully retransmit and acknowledge buffered packets upon RF link recovery ($\text{PER} < 0.20$).
* **Network Transmission Overhead**:
  Total bytes transmitted across the RF spectrum per second ($\text{kB/s}$), comparing DMLT selective filtering vs. full broadcast flooding.

---

## 4. Layer 3: Swarm Robotics & SAR Mission Dynamics

Evaluates decentralized swarm coordination, spatial dispersion, victim discovery speed, and flight safety.

### 4.1 Independent Variables (Control Parameters)
| Parameter | Symbol | Test Values | Description |
| :--- | :---: | :---: | :--- |
| **Search Arena Area** | $A_{\text{arena}}$ | $200\text{m} \times 200\text{m}$ up to $600\text{m} \times 600\text{m}$ | Mission operational footprint. |
| **Victim Distribution** | $D_{\text{victim}}$ | `Uniform Random` vs `Clustered Hotspots (Debris sites)` | Spatial distribution of search targets. |
| **Swarm Flight Speed** | $V$ | $5 \text{ m/s}, 10 \text{ m/s}, 15 \text{ m/s}$ | Nominal operational cruise speed. |
| **Safety Threshold** | $R_{\text{safe}}$ | $5.0 \text{ m}, 10.0 \text{ m}$ | Minimum threshold for collision avoidance. |

### 4.2 Dependent Metrics
* **Time to First Detection (TTFD)**:
  $$\text{TTFD} = t_{\text{first\_detection}} - t_{\text{takeoff}} \quad (\text{seconds})$$
* **Time to Global Consensus ($T_{\text{consensus}}$)**:
  Timestamp when $100\%$ of active swarm nodes and the Ground Control Station (GCS) have synchronized the victim's verified coordinates in their local world map.
* **Spatial Area Coverage Rate ($\text{ACR}(t)$)**:
  $$\text{Coverage}(t) = \frac{\text{Union of Monitored Sensor Footprints at time } t}{\text{Total Search Area}} \times 100\%$$
* **Minimum Inter-UAV Distance ($d_{\text{min}}$)**:
  $$\min_{i \ne j, \, t} \| \mathbf{p}_i(t) - \mathbf{p}_j(t) \|_2$$
  Verifies zero collision violations ($d_{\text{min}} > R_{\text{safe}}$).
* **Battery / Energy Depletion per Victim Found ($E_{\text{victim}}$)**:
  $$\text{Joules or } \% \Delta \text{Battery consumed per confirmed target discovery}.$$

### 4.3 Dual-Threshold Hysteresis Loop for Anti-Chattering Dynamic Partitioning

In dynamic Energy-Weighted Centroidal Voronoi Tessellations (EW-CVT), partition generator weights $w_i(t)$ scale with residual battery levels to balance workload. However, continuous computational tick updates subject to ADC voltage sensor jitter, ESC noise, and infinitesimal centroid drifts drive UAV flight controllers into a high-frequency oscillatory state (**chattering**). In this state, excessive yaw, pitch, and roll corrections squander rotor propulsion energy without expanding sensor coverage.

To guarantee that trajectory corrections occur only when coverage optimization benefits strictly offset the aerodynamic turning cost, a **Dual-Threshold Hysteresis Loop** is integrated into each UAV's flight controller.

#### 1. Battery Decay Hysteresis (Temporal & Energy Threshold $\tau_\epsilon$)
Rather than continuously updating generator weights $w_i(t)$, the system locks the weight until residual battery capacity drops by a discrete threshold margin:

$$w_i(t) = \begin{cases} \left( \frac{B_i(t)}{B_{\text{max}}} \right)^\alpha, & \text{if } B_i(t_k) - B_i(t) \ge \tau_\epsilon \\ w_i(t_k), & \text{otherwise} \end{cases}$$

* **$\tau_\epsilon = 0.02 \times B_{\text{max}}$**: Discrete 2% discharge threshold. Eliminates millivolt sensor noise from perturbing Voronoi cell boundaries every millisecond.
* **$\alpha$ (EW-CVT Energy Weighting Sensitivity Exponent)**:
  * **$\alpha = 0.0$ (Standard CVT Baseline)**: Degenerates into unweighted Centroidal Voronoi Tessellation based strictly on Euclidean distance. Workload allocation ignores battery variance across nodes.
  * **$\alpha = 1.0$ (Linear EW-CVT)**: Search cell footprint scales linearly with residual battery capacity.
  * **$\alpha > 1.0$ (Aggressive Non-Linear EW-CVT, e.g. $\alpha = 2.0$)**: Substantially penalizes low-battery UAVs, rapidly shedding remaining patrol sectors and transferring them to healthier peers with higher battery reserves.

#### 2. Spatial Centroid Hysteresis (Kinetic Threshold $\tau_\delta$)
Even after a battery weight update, adjacent boundary adjustments may shift the mass centroid target $C_i^*$ by only a few centimeters. Forcing the UAV to alter yaw and roll for micro-shifts is aerodynamically wasteful:

$$C_i(t) = \begin{cases} C_i^*, & \text{if } \|C_i^* - C_i(t_k)\| \ge \tau_\delta \\ C_i(t_k), & \text{otherwise} \end{cases}$$

* **$\tau_\delta = 5.0\text{ meters}$**: Spatial hysteresis margin, calibrated against UAV minimum turning radius and optical sensor field-of-view (FOV).

#### 3. Forced-Override Condition (Node Failure & Topology Mutation)
While hysteresis operates during steady-state cruising, catastrophic events (e.g. UAV motor failure or packet loss partitioning) require instantaneous partition reassignment to prevent coverage blindspots.

Evaluating the active network topology $\mathcal{N}(t)$ via Data Link Layer (DLL) heartbeats, the comprehensive update trigger $\mathcal{U}_i(t)$ evaluates as:

$$\mathcal{U}_i(t) = \left( (B_i(t_k) - B_i(t) \ge \tau_\epsilon) \land (\|C_i^* - C_i(t_k)\| \ge \tau_\delta) \right) \lor (\mathcal{N}(t) \ne \mathcal{N}(t_k))$$

When $\mathcal{N}(t) \ne \mathcal{N}(t_k)$ (e.g., node loss $n \to n-1$), the right-hand term forces an immediate hard update, instantaneously overriding $\tau_\epsilon$ and $\tau_\delta$ thresholds.

#### 4. Aerodynamic Power Model & Kinetic Energy Savings Formulation
The total rotor propulsion power $P_{\text{propulsion}}(v)$ required for level cruise at airspeed $v$ is modeled as:

$$P_{\text{propulsion}}(v) = P_0 \left(1 + \frac{3 v^2}{v_{\text{tip}}^2}\right) + P_i \left( \sqrt{1 + \frac{v^4}{4 v_0^4}} - \frac{v^2}{2 v_0^2} \right)^{1/2} + \frac{1}{2} d_0 \rho s A v^3$$

where $P_0$ is blade profile power, $P_i$ is induced hover power, $v_{\text{tip}}$ is rotor tip speed, $v_0$ is mean rotor induced velocity in hover, $d_0$ is fuselage drag ratio, and $s$ is rotor solidity.

For every chattering oscillation suppressed by spatial threshold $\tau_\delta$, the kinetic turning energy saved is:

$$E_{\text{turn}} = \frac{1}{2} I_{\text{yaw}} \omega_{\text{yaw}}^2 + \int_0^{\Delta t_{\text{turn}}} P_{\text{propulsion}}(v) \, dt$$

The cumulative kinetic energy preserved across the swarm mission is tracked directly in `swarm_mission_output.json`.

#### 5. Methodological Paper Justification Excerpt
> *"To mitigate continuous boundary chattering and excessive flight path corrections inherent in dynamic Voronoi partitioning, a dual-threshold hysteresis loop was introduced. By establishing discrete energy decay ($\tau_{\epsilon}$) and spatial shift ($\tau_{\delta}$) thresholds, the proposed architecture guarantees that propulsion energy is expended on trajectory corrections only when the aerodynamic cost is strictly offset by coverage optimization gains, except during topology degradation events which trigger instantaneous hard-updates via the Data Link layer."*

---

## 5. Layer 4: Cross-Layer Coupled Metrics

Evaluates how vision detection confidence thresholds directly govern communication load and network stability.

### 5.1 The Vision-Network Coupling Formulation
When a drone runs onboard inference, every detection exceeding confidence $\tau_{\text{conf}}$ triggers an immediate network packet transmission:
$$\lambda_{\text{alert}}(\tau_{\text{conf}}) = \lambda_{\text{true\_target}} + \lambda_{\text{false\_alarm}}(\tau_{\text{conf}})$$

* If $\tau_{\text{conf}}$ is set **too low** (e.g. $0.05$):
  * Recall is high, but false alarms generate excessive network traffic, saturating the RF channel, elevating collision probability, and causing queue overflow in the `EdgeBroker`.
* If $\tau_{\text{conf}}$ is set **too high** (e.g. $0.60$):
  * Network traffic is low, but true victims are missed (false negatives), prolonging TTFD and failing mission objectives.

### 5.2 Evaluated Coupled Metrics
* **False Alarm Communication Overhead ($\eta_{\text{overhead}}$)**:
  $$\eta_{\text{overhead}} = \frac{\text{RF Bandwidth consumed by False Positive Alerts}}{\text{Total RF Bandwidth used for Alerts}} \times 100\%$$
* **Channel Saturation Probability ($P_{\text{sat}}$)**:
  Probability that packet generation rate exceeds RF channel capacity during peak swarm search phases.
* **Pareto Optimal Operating Frontier**:
  Optimal $\tau_{\text{conf}}^*$ maximizing $F_1$ while keeping network channel utilization $< 40\%$.

---

## 6. Target Publication Figures & Visualizations

| Figure # | Title | X-Axis | Y-Axis | Comparison Curves / Legend | Key Research Takeaway |
| :---: | :--- | :--- | :--- | :--- | :--- |
| **Fig. 1** | Multispectral Detection Precision-Recall | Recall ($R$) | Precision ($P$) | RGB-only, Thermal-only, 4-Channel P2 | Early fusion achieves superior PR area under adverse contrast. |
| **Fig. 2** | Small Object Recall by Feature Pyramid | Object Size ($\text{px}^2$) | $\text{AP}$ / Recall | Standard YOLOv8 vs. Proposed YOLOv8-P2 | Stride-4 P2 head significantly boosts small human target detection. |
| **Fig. 3** | RF Physics & Link Degradation | Distance ($10 \text{ to } 350\text{m}$) | SNR ($\text{dB}$) & PER ($0 \text{ to } 1.0$) | LoS ($\sigma=4.0$), NLoS Debris Clutter ($\sigma=7.5$) | Characterizes the physical wireless boundary of the FANET. |
| **Fig. 4** | Packet Delivery Ratio Under Intermittent Drops | Disruption Duration ($\text{s}$) | $\text{PDR} \, (\%)$ | Baseline QoS 0 vs. EdgeBroker QoS 1 | Store-and-Forward eliminates packet loss during temporary link severance. |
| **Fig. 5** | Swarm Spatial Area Coverage over Time | Mission Time ($\text{min}$) | Area Covered ($\%$) | Swarm Size $N=3, 5, 8$ | Demonstrates sub-linear scaling in multi-UAV cooperative coverage. |
| **Fig. 6** | Cross-Layer Pareto Optimization | Confidence $\tau_{\text{conf}}$ | $F_1\text{-Score}$ (Left), Network Overhead (Right) | Perception $F_1$, Alert Bandwidth ($\text{kB/s}$) | Identifies the optimal trade-off point between vision sensitivity and network load. |

---

## 7. Data Logging Schema & File Specifications

To automate data gathering from `FlyNetSim`, experimental runs should append timestamped records into standardized CSV formats:

### 7.1 Perception Evaluation Log (`metrics_vision.csv`)
```csv
timestamp,model_name,modality,is_p2,conf_thresh,precision,recall,map50,map50_95,map_small,latency_ms
```

### 7.2 RF & Communication Log (`metrics_network.csv`)
```csv
timestamp,src_uav,dst_uav,distance_m,snr_db,per,is_obstacle_shadowed,qos_level,packet_id,delivered,latency_ms
```

### 7.3 Swarm Mission Log (`metrics_mission.csv`)
```csv
timestamp,swarm_size,area_m2,elapsed_sec,area_covered_pct,ttfd_sec,consensus_sec,active_peers,min_peer_dist_m,buffered_alerts_total
```

---

## 8. Benchmark Experiment: Wide-Area 5 km Swarm with Unified Base Station Launch & Fault Recovery

### 8.1 Operational Flight Architecture
* **Launch Base Station / GCS**: Unified staging area at $(250.0\text{m}, 250.0\text{m})$ (South-West Incident Command Post).
* **Dual-Speed Flight Envelope**:
  * **Ingress / Egress Transit Dash**: $50\text{ m/s}$ ($180\text{ km/h}$) to cross multi-kilometer corridors rapidly.
  * **Sensor Survey Cruise**: $32\text{ m/s}$ ($115\text{ km/h}$) for steady multispectral imaging and optimal forward overlap.
* **Search Domain**: $5000\text{m} \times 5000\text{m}$ ($25\text{ km}^2$, 25 sectors of $1000\text{m} \times 1000\text{m}$).
* **Fleet Configuration**: $N = 10$ autonomous UAVs with geographic centroid territorial clustering.
* **Perception Architecture**: 4-channel early-fusion YOLOv8n-P2 (Stride 4) at $\tau = 0.20$.
* **Injected Mid-Mission Fault**: Catastrophic propulsion failure on **UAV 4** at $T = 80.0\text{s}$ at coordinates $(756.0\text{m}, 3500.0\text{m})$.
* **Fault-Tolerant Dynamic Failover**: Unsurveyed abandoned sectors (Sectors 16 & 20) autonomously reassigned to nearest active peer UAV 3.
* **Return-to-Base (RTL) Convergence**: Surviving UAVs return to the launch pad, triggering proximity buffer flushes and map synchronization.

### 8.2 Empirical Results
| Experimental Metric | Measured Swarm Outcome | Resilient Swarm Behavior |
| :--- | :--- | :--- |
| **Launch Origin** | **Single Base Pad $(250\text{m}, 250\text{m})$** | All 10 UAVs fan outward from a unified Ground Control Station. |
| **Area Survey Coverage** | **$100.0\%$ (25/25 Sectors)** | Surviving UAV 3 dynamically adopted abandoned Sectors 16 & 20. |
| **Ground Truth Targets** | **259 Human Victims** | Ground-truth annotations from RGBT SAR dataset. |
| **True Positive Detections (TP)** | **185 Human Victims** | Correct spatial victim identifications. |
| **Perception Recall** | **$71.43\%$ Recall** | High victim discovery across $25\text{ km}^2$ wilderness. |
| **Mean / RMSE Spatial Error** | **$2.60\text{ m}$ / $3.64\text{ m}$** | High localization accuracy across a 5 km domain. |
| **Mesh Consensus at Egress** | **$97.7\%$ Final Consensus** | Swarm convergence at base station flushes all QoS 1 buffers. |
| **Total Mission Duration** | **$286.0\text{ seconds}$** | Complete launch $\rightarrow$ transit $\rightarrow$ search $\rightarrow$ failover $\rightarrow$ return cycle. |

