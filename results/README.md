# Ablation Results

Autonomous multispectral UAV swarm for search and rescue (SAR). This document reports what each of the
three contributions buys, by switching it off and measuring what happens.

| # | Contribution | Where |
|---|---|---|
| 1 | 4-channel RGB + thermal early-fusion detector (YOLO11) | `rgbt_detector.py` |
| 2 | Delay-tolerant FANET mesh: RF physics, QoS-1 store-and-forward, multi-hop relay | `FlySim/swarm_network.py` |
| 3 | Swarm control: Energy-Weighted CVT partitioning, dual-threshold hysteresis, autonomous failover | `FlySim/hysteresis_controller.py`, `simulate_swarm_mission.py` |

Everything here is **780 simulated missions** plus a detector evaluation, and is reproducible
(see [Reproduce](#reproduce)). A self-contained HTML version with the same charts is in
[`final_report.html`](final_report.html).

## Headline: what each component buys

| Component removed → measured effect | Full system | Ablated | Change (paired mean ± 95% CI) |
|---|---:|---:|---:|
| **Failover** (UAV lost): area coverage | 100.0 % | 87.0 % | -13.0 ± 3.0 pts |
| &nbsp;&nbsp;victims found, whole arena (recall) | 0.980 | 0.840 | -0.140 ± 0.037 |
| **Hysteresis**: sector flips / mission | 2.1 | 10.7 | +8.6 ± 2.8 |
| &nbsp;&nbsp;route changes / mission | 4.0 | 20.1 | +16.1 ± 5.0 |
| &nbsp;&nbsp;mission time | 367 s | 390 s | +22 ± 29 s |
| **EW weighting** (α=0): min final battery | 18.9 % | 17.4 % | -1.6 ± 1.3 pts |
| Static baseline vs full: mission time (cost of re-planning) | 331 s | 367 s | +36 ± 22 s |
| **DTN buffer** (5 km): victims known to operator | 98.0 % | 4.3 % | -93.7 ± 1.4 pts |
| &nbsp;&nbsp;swarm-wide consensus | 100.0 % | 22.4 % | -77.6 ± 1.2 pts |
| **Multi-hop** (5 km): victims known to operator | 98.0 % | 98.0 % | +0.0 ± 0.0 pts |
| **Thermal channel** (masked), day: AP50 | 99.8 | 0.0 | -99.8 |
| &nbsp;&nbsp;night: AP50 | 94.3 | 0.0 | -94.3 |

*Change* is the paired difference over 20 seeds with a 95 % confidence interval; if the interval
contains zero the effect is not established. The mission-time change from removing hysteresis is within noise:
hysteresis removes churn (flips, route changes, commits), not flight time.

## How the experiments are set up

- **Mission.** 6 UAVs search a 5 km × 5 km arena divided into 25 sectors. Each sector shows one real frame
  from the NII-CU RGB-thermal drone dataset, with its human labels as ground truth. UAVs launch from a base
  station, fly to sector centres, run the detector there, and return home.
- **Seeds and pairing.** A seed fixes which frame sits in which sector and each UAV's launch battery
  (uniform 20–100 %). Every variant runs on the same 20 seeds, so differences come from the removed
  component rather than the draw. Tables show mean ± standard deviation across seeds.
- **UAV loss scenario.** UAV 2 suffers a motor failure at t = 80 s.
- **Energy rule.** A UAV at 15 % battery or below aborts and returns to base; at 0 % it is lost.
- **Control loop** (every 5 s): each UAV reads its battery (with sensor noise σ = 1.5 % points by default),
  computes weight `w = (B / 100)^α`, and the EW-CVT centroid its cell *should* have. The hysteresis
  controller commits the change only if the battery has dropped by at least 2 % **and** the centroid has moved at
  least 5 m, or the set of live UAVs changed (forced override). Unscanned sectors are then assigned to the
  nearest UAV by power distance `‖c_s − g_i‖² / w_i` using only committed values.
- **Operator view.** Every victim alert is sent to all peers and to a ground control station (GCS) at the
  base. *Operator recall* is the share of all victims in the arena that the GCS actually learned about.

## 1. Perception: does the thermal channel matter?

| Condition | Input | AP50 | AP75 | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Day (clean) | RGB + Thermal (fused) | 99.82 | 85.76 | 0.993 | 0.989 | 0.991 |
| Day (clean) | RGB only (thermal masked) | 0.0 | 0.0 | 0.000 | 0.000 | 0.000 |
| Day (clean) | Thermal only (RGB masked) | 89.03 | 50.52 | 0.944 | 0.731 | 0.824 |
| Night (RGB dark + noisy) | RGB + Thermal (fused) | 94.31 | 58.26 | 0.916 | 0.869 | 0.892 |
| Night (RGB dark + noisy) | RGB only (thermal masked) | 0.0 | 0.0 | 0.000 | 0.000 | 0.000 |
| Night (RGB dark + noisy) | Thermal only (RGB masked) | 89.03 | 50.52 | 0.944 | 0.731 | 0.824 |
| Thermal washout | RGB + Thermal (fused) | 61.82 | 25.07 | 0.991 | 0.386 | 0.555 |
| Thermal washout | RGB only (thermal masked) | 0.0 | 0.0 | 0.000 | 0.000 | 0.000 |
| Thermal washout | Thermal only (RGB masked) | 0.0 | 0.0 | 0.000 | 0.000 | 0.000 |

![AP50 by modality and condition](figures/detection_ap50_by_modality_and_condition.png)

150 held-out NII-CU val frames (fixed random subset), IoU 0.5 matching, operating point conf ≥ 0.25.
*Night* darkens RGB to 12 % brightness and adds noise; *thermal washout* squashes thermal contrast to 25 %.

- Fusion beats thermal-only by about 11 AP points in daylight, so RGB adds real information.
- Losing RGB light (night) costs the fused model only 5.5 AP points, because thermal carries it.
- Thermal washout hurts most: recall falls to 0.39 while precision stays at 0.99.

> **Important caveat.** This is *modality-masked inference* of one fused network (a channel is set to zero),
> **not** three separately trained networks. The 0.0 for RGB-only means the network was never trained to work
> without thermal; it does not mean RGB is uninformative. Properly trained RGB-only / thermal-only baselines
> are set up in the notebook `nii_cu_ablation_2gpu.ipynb` but have not been run. Train and val come from the
> same site, so absolute numbers are optimistic.

## 2. Swarm control: EW-CVT, hysteresis, failover

Variants: **Full** (EW-CVT α = 1, hysteresis, failover, 5 s replans); **− EW weighting** (α = 0, plain Voronoi);
**− Hysteresis** (every replan commits); **− Failover** (a lost UAV's sectors stay lost); **Static baseline**
(partition once at launch, never change).

| Scenario | Variant | Coverage % | Recall (arena) | Mission time s | Min final battery % | Sector flips | Route changes | Low-batt. aborts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Nominal | Full system | 100.0 ± 0.0 | 0.980 ± 0.015 | 367 ± 47 | 18.9 ± 8.5 | 2.1 ± 1.8 | 4.0 ± 3.1 | 0.55 ± 0.60 |
| Nominal | - EW weighting (alpha=0) | 100.0 ± 0.0 | 0.980 ± 0.015 | 360 ± 50 | 17.4 ± 7.6 | 0.7 ± 1.8 | 1.6 ± 3.4 | 0.55 ± 0.69 |
| Nominal | - Hysteresis | 100.0 ± 0.0 | 0.980 ± 0.015 | 390 ± 56 | 18.4 ± 8.7 | 10.7 ± 6.4 | 20.1 ± 11.8 | 0.60 ± 0.68 |
| Nominal | Static baseline | 97.6 ± 5.1 | 0.959 ± 0.039 | 331 ± 20 | 17.9 ± 7.9 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.50 ± 0.61 |
| UAV loss | Full system | 100.0 ± 0.0 | 0.980 ± 0.015 | 421 ± 67 | 20.7 ± 11.5 | 3.4 ± 2.6 | 6.5 ± 3.9 | 0.55 ± 0.60 |
| UAV loss | - EW weighting (alpha=0) | 100.0 ± 0.0 | 0.980 ± 0.015 | 363 ± 40 | 19.3 ± 11.4 | 2.4 ± 1.3 | 6.0 ± 2.4 | 0.60 ± 0.68 |
| UAV loss | - Hysteresis | 100.0 ± 0.0 | 0.980 ± 0.015 | 422 ± 51 | 20.6 ± 11.5 | 10.9 ± 5.8 | 21.2 ± 11.5 | 0.50 ± 0.61 |
| UAV loss | - Failover | 87.0 ± 6.5 | 0.840 ± 0.076 | 366 ± 34 | 21.1 ± 11.1 | 2.8 ± 1.7 | 4.9 ± 3.1 | 0.50 ± 0.61 |
| UAV loss | Static baseline | 85.8 ± 5.1 | 0.847 ± 0.061 | 330 ± 24 | 20.3 ± 10.9 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.45 ± 0.60 |

*Sector flips* = unscanned sectors that change owner between replans (failover excluded). *Route changes* = times a
UAV had to re-plan its route. High values mean the swarm is chattering. *Recall (arena)* counts victims over the whole arena, so
sectors that are never searched count against the system.

### Resilience: coverage over time

![Coverage over time](figures/coverage_over_time.png)

With no failure every variant reaches full coverage around 350 s. After the UAV loss, only variants with failover reach 100 %;
without it the lost UAV's sectors are never searched (about 87 % coverage).

### Hysteresis suppresses chattering under sensor noise

![Hysteresis vs sensor noise](figures/hysteresis_vs_sensor_noise.png)

| Sensor noise σ (%) | Flips: hyst. ON | Flips: hyst. OFF | Commits ON | Commits OFF | Time ON (s) | Time OFF (s) |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 1.8 ± 1.3 | 5.2 ± 3.4 | 32 ± 5 | 294 ± 24 | 377 ± 49 | 389 ± 55 |
| 1 | 2.1 ± 1.9 | 9.6 ± 5.9 | 31 ± 4 | 295 ± 28 | 372 ± 46 | 388 ± 59 |
| 2 | 2.5 ± 2.0 | 13.5 ± 7.8 | 31 ± 4 | 296 ± 24 | 362 ± 42 | 392 ± 49 |
| 4 | 4.1 ± 2.6 | 23.4 ± 13.4 | 30 ± 5 | 300 ± 30 | 364 ± 37 | 400 ± 56 |

Without hysteresis every replan commits, so battery-sensor noise keeps moving sector borders. Commits are about
10× fewer with hysteresis, and the gap in sector flips widens as noise grows.

### EW-CVT exponent α: time versus energy reserve

![alpha sweep](figures/alpha_sweep.png)

| α | Min final battery % | Mission time s | Coverage % | Low-battery aborts |
|---|---:|---:|---:|---:|
| 0 | 15.1 ± 6.3 | 354 ± 41 | 100.0 ± 0.0 | 0.90 ± 0.85 |
| 0.5 | 16.2 ± 6.7 | 357 ± 37 | 100.0 ± 0.0 | 0.80 ± 0.77 |
| 1 | 16.8 ± 6.9 | 377 ± 47 | 100.0 ± 0.0 | 0.75 ± 0.72 |
| 2 | 18.4 ± 6.3 | 436 ± 74 | 100.0 ± 0.0 | 0.30 ± 0.57 |
| 3 | 21.1 ± 8.4 | 507 ± 125 | 100.0 ± 0.0 | 0.25 ± 0.44 |

Larger α shrinks weak UAVs' territory, which raises the minimum remaining battery and reduces low-battery aborts but lengthens the mission, because
healthy UAVs carry more of the work. α is a dial between speed and energy safety; it is not a free improvement.
Coverage is 100 % at every α, so the third panel is flat.

## 3. Networking: delay-tolerant mesh and multi-hop

| Arena | Variant | Operator recall | Alert latency s | Consensus | First-attempt PDR to GCS | Messages lost | Delivered late (DTN) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1.5 km | Full (DTN + multi-hop) | 0.985 ± 0.013 | 42 ± 5 | 1.000 ± 0.000 | 0.064 ± 0.030 | 0 ± 0 | 249 ± 29 |
| 1.5 km | - DTN buffer | 0.056 ± 0.026 | 0 ± 0 | 0.243 ± 0.031 | 0.058 ± 0.030 | 250 ± 29 | 0 ± 0 |
| 1.5 km | - Multi-hop | 0.985 ± 0.013 | 40 ± 5 | 1.000 ± 0.000 | 0.055 ± 0.028 | 0 ± 0 | 252 ± 29 |
| 1.5 km | - Both (direct only) | 0.043 ± 0.026 | 0 ± 0 | 0.236 ± 0.027 | 0.043 ± 0.026 | 252 ± 29 | 0 ± 0 |
| 3 km | Full (DTN + multi-hop) | 0.985 ± 0.013 | 59 ± 7 | 1.000 ± 0.000 | 0.080 ± 0.038 | 0 ± 0 | 239 ± 29 |
| 3 km | - DTN buffer | 0.087 ± 0.040 | 0 ± 0 | 0.279 ± 0.031 | 0.089 ± 0.042 | 239 ± 30 | 0 ± 0 |
| 3 km | - Multi-hop | 0.985 ± 0.013 | 60 ± 7 | 1.000 ± 0.000 | 0.053 ± 0.041 | 0 ± 0 | 244 ± 28 |
| 3 km | - Both (direct only) | 0.049 ± 0.033 | 0 ± 0 | 0.266 ± 0.027 | 0.051 ± 0.037 | 244 ± 28 | 0 ± 0 |
| 5 km | Full (DTN + multi-hop) | 0.980 ± 0.015 | 109 ± 12 | 1.000 ± 0.000 | 0.047 ± 0.035 | 0 ± 0 | 256 ± 29 |
| 5 km | - DTN buffer | 0.043 ± 0.027 | 0 ± 0 | 0.224 ± 0.027 | 0.045 ± 0.032 | 256 ± 31 | 0 ± 0 |
| 5 km | - Multi-hop | 0.980 ± 0.015 | 110 ± 11 | 1.000 ± 0.000 | 0.034 ± 0.022 | 0 ± 0 | 257 ± 29 |
| 5 km | - Both (direct only) | 0.038 ± 0.023 | 0 ± 0 | 0.221 ± 0.027 | 0.039 ± 0.026 | 257 ± 30 | 0 ± 0 |

![Network ablation](figures/network_ablation.png)

Under the RF model (log-distance path loss, exponent 2.5, 4 dB shadowing) direct links reach only a few hundred metres, so
the swarm is mostly disconnected in flight and first-attempt delivery to the GCS is low everywhere. Store-and-forward queues
alerts in the UAV's buffer and flushes them when it returns to base, which turns a mostly-offline swarm into one the operator can
rely on. Multi-hop relaying adds nothing here: a relay must be closer to *both* endpoints, which rarely holds in a sparse swarm.

## 4. Scaling with swarm size

![Scaling](figures/scaling.png)

| Swarm size | Mission time s | Mean energy used / UAV % | Recall (arena) |
|---|---:|---:|---:|
| 2 | 554 ± 0 | 24.9 ± 0.0 | 0.980 ± 0.015 |
| 4 | 329 ± 0 | 16.9 ± 0.0 | 0.980 ± 0.015 |
| 6 | 337 ± 0 | 12.9 ± 0.0 | 0.980 ± 0.015 |
| 8 | 296 ± 0 | 12.2 ± 0.0 | 0.980 ± 0.015 |
| 12 | 261 ± 0 | 11.6 ± 0.0 | 0.980 ± 0.015 |

Time falls and per-UAV energy falls as the swarm grows; the speedup is sublinear because transit from the base is a fixed cost.
The small non-monotonicity between 4 and 6 UAVs is probably an artefact of how starting territories are laid out (corners for ≤ 4, a ring for more); this has not been verified.

## What these results do and do not show

- **Simulation, not flight.** Dynamics are kinematic (constant speed, linear battery drain). The EW-CVT, hysteresis, failover and DTN logic is real code under test; the aircraft and radio are models.
- **Detection inside missions replays static frames.** Each sector shows one image, so mission-level precision and recall mostly reflect the detector on those frames plus sector coverage.
- **Network results depend on the RF model** (33 dBm at 2.4 GHz for arenas ≥ 2 km, 30 dBm at 5 GHz below). Real links would differ.
- **Assumptions.** The 15 % abort rule and the 0–4 % battery-sensor-noise levels are scenario assumptions (noise is swept above).
- **Re-planning is not free.** In the nominal case the static baseline finishes about 36 s sooner than the full system, but it also leaves some sectors unsearched even without any failure
  (97.6 % coverage), because weak-battery UAVs abort.
- **Earlier numbers superseded.** An earlier version of the simulator let UAVs teleport to their first waypoint and then drift back toward the launch pad, which invalidated mission time,
  time-to-first-detection, energy and hysteresis statistics (the benchmark table in the top-level `README.md` came from that version). That is fixed; detection precision, recall and localization were unaffected. The numbers in this document replace them.

## Reproduce

```bash
source FlySim/venv/bin/activate

python ablation/perception_eval.py --n 150          # ~20 min on CPU  -> results/ablation/perception.json
python ablation/run_ablation.py --seeds 20            # ~1 min after detector cache is warm -> results/ablation/runs.json
python ablation/make_report.py                       # -> results/final_report.html + results/figures/*.png
python ablation/make_readme.py                       # -> this file
```

Each switch can also be used from the single-mission CLI, for example:

```bash
python simulate_swarm_mission.py --drones 6 --arena 5000 --duration 900 \
    --batt-min 20 --batt-noise 1.5 --fail-drone 2 --fail-time 80 \
    --no-hysteresis --out-dir /tmp/run1          # also: --no-failover --static --no-dtn --no-multihop --alpha 0
```

The ablation harness never writes outside `results/`, so it will not overwrite mission outputs in the repository root.

## Files

| Path | Contents |
|---|---|
| `ablation/perception_eval.py` | Modality-masked detector evaluation |
| `ablation/run_ablation.py` | Swarm ablation harness (configurations, seeds, parallel runs) |
| `ablation/make_report.py` | HTML report and chart export |
| `ablation/make_readme.py` | Generates this file from the run data |
| `results/ablation/runs.json` | Raw per-mission metrics and coverage time series |
| `results/ablation/perception.json` | Raw detector metrics |
| `results/final_report.html` | Self-contained HTML report |
| `results/figures/` | Charts used above |
