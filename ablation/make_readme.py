#!/usr/bin/env python3
"""Writes results/README.md (GitHub-rendered) with every table computed from results/ablation/*.json."""
import os, json, collections
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AB = os.path.join(ROOT, "results", "ablation")
runs_doc = json.load(open(os.path.join(AB, "runs.json")))
RUNS, META = runs_doc["runs"], runs_doc["meta"]
N = len(META["seeds"])
perc = json.load(open(os.path.join(AB, "perception.json")))
P = {(r["condition"], r["mode"]): r for r in perc["results"]}

IDX = collections.defaultdict(dict)
for r in RUNS:
    IDX[(r["group"], r["scenario"], r["name"])][r["seed"]] = r["metrics"]

def vals(k, m): return {s: v[m] for s, v in IDX[k].items() if v.get(m) is not None}
def mean(k, m): v = list(vals(k, m).values()); return float(np.mean(v)) if v else float("nan")
def ms(k, m, d=1):
    v = list(vals(k, m).values())
    return f"{np.mean(v):.{d}f} ± {np.std(v, ddof=1):.{d}f}" if len(v) > 1 else "n/a"
def paired(kA, kB, m, scale=1.0, d=1, unit=""):
    a, b = vals(kA, m), vals(kB, m); sh = sorted(set(a) & set(b))
    diff = np.array([b[s] - a[s] for s in sh], float) * scale
    t = 2.09 if len(sh) >= 20 else 2.26
    return f"{diff.mean():+.{d}f} ± {t * diff.std(ddof=1) / np.sqrt(len(diff)):.{d}f}{unit}"
def md(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] + ["---:"] * (len(header) - 1)) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)

ck = lambda sc, n: ("control", sc, n)
NOM, LOSS = "nominal", "uav_loss"
full_n, full_l = ck(NOM, "Full system"), ck(LOSS, "Full system")
fk, dk, mk = [("network", "arena_5000", n) for n in ("Full (DTN + multi-hop)", "- DTN buffer", "- Multi-hop")]

# ---------------------------------------------------------------- tables
headline = md(["Component removed → measured effect", "Full system", "Ablated", "Change (paired mean ± 95% CI)"], [
    ["**Failover** (UAV lost): area coverage", f"{mean(full_l,'coverage_pct'):.1f} %", f"{mean(ck(LOSS,'- Failover'),'coverage_pct'):.1f} %", paired(full_l, ck(LOSS, "- Failover"), "coverage_pct", unit=" pts")],
    ["&nbsp;&nbsp;victims found, whole arena (recall)", f"{mean(full_l,'recall_arena'):.3f}", f"{mean(ck(LOSS,'- Failover'),'recall_arena'):.3f}", paired(full_l, ck(LOSS, "- Failover"), "recall_arena", d=3)],
    ["**Hysteresis**: sector flips / mission", f"{mean(full_n,'sector_flips'):.1f}", f"{mean(ck(NOM,'- Hysteresis'),'sector_flips'):.1f}", paired(full_n, ck(NOM, "- Hysteresis"), "sector_flips")],
    ["&nbsp;&nbsp;route changes / mission", f"{mean(full_n,'route_changes'):.1f}", f"{mean(ck(NOM,'- Hysteresis'),'route_changes'):.1f}", paired(full_n, ck(NOM, "- Hysteresis"), "route_changes")],
    ["&nbsp;&nbsp;mission time", f"{mean(full_n,'makespan_s'):.0f} s", f"{mean(ck(NOM,'- Hysteresis'),'makespan_s'):.0f} s", paired(full_n, ck(NOM, "- Hysteresis"), "makespan_s", d=0, unit=" s")],
    ["**EW weighting** (α=0): min final battery", f"{mean(full_n,'batt_min_pct'):.1f} %", f"{mean(ck(NOM,'- EW weighting (alpha=0)'),'batt_min_pct'):.1f} %", paired(full_n, ck(NOM, "- EW weighting (alpha=0)"), "batt_min_pct", unit=" pts")],
    ["Static baseline vs full: mission time (cost of re-planning)", f"{mean(ck(NOM,'Static baseline'),'makespan_s'):.0f} s", f"{mean(full_n,'makespan_s'):.0f} s", paired(ck(NOM, "Static baseline"), full_n, "makespan_s", d=0, unit=" s")],
    ["**DTN buffer** (5 km): victims known to operator", f"{mean(fk,'operator_recall')*100:.1f} %", f"{mean(dk,'operator_recall')*100:.1f} %", paired(fk, dk, "operator_recall", 100, unit=" pts")],
    ["&nbsp;&nbsp;swarm-wide consensus", f"{mean(fk,'consensus_final')*100:.1f} %", f"{mean(dk,'consensus_final')*100:.1f} %", paired(fk, dk, "consensus_final", 100, unit=" pts")],
    ["**Multi-hop** (5 km): victims known to operator", f"{mean(fk,'operator_recall')*100:.1f} %", f"{mean(mk,'operator_recall')*100:.1f} %", paired(fk, mk, "operator_recall", 100, unit=" pts")],
    ["**Thermal channel** (masked), day: AP50", f"{P[('day','fusion')]['AP50']:.1f}", f"{P[('day','rgb_only')]['AP50']:.1f}", f"{P[('day','rgb_only')]['AP50']-P[('day','fusion')]['AP50']:+.1f}"],
    ["&nbsp;&nbsp;night: AP50", f"{P[('night','fusion')]['AP50']:.1f}", f"{P[('night','rgb_only')]['AP50']:.1f}", f"{P[('night','rgb_only')]['AP50']-P[('night','fusion')]['AP50']:+.1f}"],
])

pn = {"day": "Day (clean)", "night": "Night (RGB dark + noisy)", "thermal_washout": "Thermal washout"}
pm = {"fusion": "RGB + Thermal (fused)", "rgb_only": "RGB only (thermal masked)", "thermal_only": "Thermal only (RGB masked)"}
perc_tbl = md(["Condition", "Input", "AP50", "AP75", "Precision", "Recall", "F1"],
              [[pn[c], pm[m], P[(c, m)]["AP50"], P[(c, m)]["AP75"], f"{P[(c,m)]['precision']:.3f}", f"{P[(c,m)]['recall']:.3f}", f"{P[(c,m)]['f1']:.3f}"]
               for c in pn for m in pm])

ctl_rows = []
for sc, scl in [(NOM, "Nominal"), (LOSS, "UAV loss")]:
    for n in ["Full system", "- EW weighting (alpha=0)", "- Hysteresis", "- Failover", "Static baseline"]:
        k = ck(sc, n)
        if k in IDX:
            ctl_rows.append([scl, n, ms(k, "coverage_pct"), ms(k, "recall_arena", 3), ms(k, "makespan_s", 0), ms(k, "batt_min_pct"),
                             ms(k, "sector_flips"), ms(k, "route_changes"), ms(k, "rtl_aborts", 2)])
ctl_tbl = md(["Scenario", "Variant", "Coverage %", "Recall (arena)", "Mission time s", "Min final battery %", "Sector flips", "Route changes", "Low-batt. aborts"], ctl_rows)

noise_tbl = md(["Sensor noise σ (%)", "Flips: hyst. ON", "Flips: hyst. OFF", "Commits ON", "Commits OFF", "Time ON (s)", "Time OFF (s)"],
               [[f"{s:g}"] + [ms(("noise", f"sigma_{s:g}", n), m, d) for m, d in (("sector_flips", 1),) for n in ("Hysteresis ON", "Hysteresis OFF")]
                + [ms(("noise", f"sigma_{s:g}", n), "partition_commits", 0) for n in ("Hysteresis ON", "Hysteresis OFF")]
                + [ms(("noise", f"sigma_{s:g}", n), "makespan_s", 0) for n in ("Hysteresis ON", "Hysteresis OFF")] for s in (0.0, 1.0, 2.0, 4.0)])

alpha_tbl = md(["α", "Min final battery %", "Mission time s", "Coverage %", "Low-battery aborts"],
               [[f"{a:g}", ms(("alpha", f"alpha_{a:g}", f"alpha={a:g}"), "batt_min_pct"), ms(("alpha", f"alpha_{a:g}", f"alpha={a:g}"), "makespan_s", 0),
                 ms(("alpha", f"alpha_{a:g}", f"alpha={a:g}"), "coverage_pct"), ms(("alpha", f"alpha_{a:g}", f"alpha={a:g}"), "rtl_aborts", 2)] for a in (0, 0.5, 1, 2, 3)])

net_rows = []
for a in (1500, 3000, 5000):
    for n in ("Full (DTN + multi-hop)", "- DTN buffer", "- Multi-hop", "- Both (direct only)"):
        k = ("network", f"arena_{a}", n)
        net_rows.append([f"{a/1000:g} km", n, ms(k, "operator_recall", 3), ms(k, "alert_latency_mean_s", 0), ms(k, "consensus_final", 3),
                         ms(k, "gcs_pdr_first_attempt", 3), ms(k, "msgs_lost_forever", 0), ms(k, "msgs_delivered_late", 0)])
net_tbl = md(["Arena", "Variant", "Operator recall", "Alert latency s", "Consensus", "First-attempt PDR to GCS", "Messages lost", "Delivered late (DTN)"], net_rows)

scale_tbl = md(["Swarm size", "Mission time s", "Mean energy used / UAV %", "Recall (arena)"],
               [[n, ms(("scale", f"n_{n}", f"{n} UAVs"), "makespan_s", 0), ms(("scale", f"n_{n}", f"{n} UAVs"), "energy_used_mean_pct"),
                 ms(("scale", f"n_{n}", f"{n} UAVs"), "recall_arena", 3)] for n in (2, 4, 6, 8, 12)])

# ---------------------------------------------------------------- document
doc = f"""# Ablation Results

Autonomous multispectral UAV swarm for search and rescue (SAR). This document reports what each of the
three contributions buys, by switching it off and measuring what happens.

| # | Contribution | Where |
|---|---|---|
| 1 | 4-channel RGB + thermal early-fusion detector (YOLO11) | `rgbt_detector.py` |
| 2 | Delay-tolerant FANET mesh: RF physics, QoS-1 store-and-forward, multi-hop relay | `FlySim/swarm_network.py` |
| 3 | Swarm control: Energy-Weighted CVT partitioning, dual-threshold hysteresis, autonomous failover | `FlySim/hysteresis_controller.py`, `simulate_swarm_mission.py` |

Everything here is **{len(RUNS)} simulated missions** plus a detector evaluation, and is reproducible
(see [Reproduce](#reproduce)). A self-contained HTML version with the same charts is in
[`final_report.html`](final_report.html).

## Headline: what each component buys

{headline}

*Change* is the paired difference over {N} seeds with a 95 % confidence interval; if the interval
contains zero the effect is not established. The mission-time change from removing hysteresis is within noise:
hysteresis removes churn (flips, route changes, commits), not flight time.

## How the experiments are set up

- **Mission.** 6 UAVs search a 5 km × 5 km arena divided into 25 sectors. Each sector shows one real frame
  from the NII-CU RGB-thermal drone dataset, with its human labels as ground truth. UAVs launch from a base
  station, fly to sector centres, run the detector there, and return home.
- **Seeds and pairing.** A seed fixes which frame sits in which sector and each UAV's launch battery
  (uniform 20–100 %). Every variant runs on the same {N} seeds, so differences come from the removed
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

{perc_tbl}

![AP50 by modality and condition](figures/detection_ap50_by_modality_and_condition.png)

{perc["meta"]["n_frames"]} held-out NII-CU val frames (fixed random subset), IoU 0.5 matching, operating point conf ≥ {perc["meta"]["op_conf"]}.
*Night* darkens RGB to 12 % brightness and adds noise; *thermal washout* squashes thermal contrast to 25 %.

- Fusion beats thermal-only by about {P[("day","fusion")]["AP50"]-P[("day","thermal_only")]["AP50"]:.0f} AP points in daylight, so RGB adds real information.
- Losing RGB light (night) costs the fused model only {P[("day","fusion")]["AP50"]-P[("night","fusion")]["AP50"]:.1f} AP points, because thermal carries it.
- Thermal washout hurts most: recall falls to {P[("thermal_washout","fusion")]["recall"]:.2f} while precision stays at {P[("thermal_washout","fusion")]["precision"]:.2f}.

> **Important caveat.** This is *modality-masked inference* of one fused network (a channel is set to zero),
> **not** three separately trained networks. The 0.0 for RGB-only means the network was never trained to work
> without thermal; it does not mean RGB is uninformative. Properly trained RGB-only / thermal-only baselines
> are set up in the notebook `nii_cu_ablation_2gpu.ipynb` but have not been run. Train and val come from the
> same site, so absolute numbers are optimistic.

## 2. Swarm control: EW-CVT, hysteresis, failover

Variants: **Full** (EW-CVT α = 1, hysteresis, failover, 5 s replans); **− EW weighting** (α = 0, plain Voronoi);
**− Hysteresis** (every replan commits); **− Failover** (a lost UAV's sectors stay lost); **Static baseline**
(partition once at launch, never change).

{ctl_tbl}

*Sector flips* = unscanned sectors that change owner between replans (failover excluded). *Route changes* = times a
UAV had to re-plan its route. High values mean the swarm is chattering. *Recall (arena)* counts victims over the whole arena, so
sectors that are never searched count against the system.

### Resilience: coverage over time

![Coverage over time](figures/coverage_over_time.png)

With no failure every variant reaches full coverage around 350 s. After the UAV loss, only variants with failover reach 100 %;
without it the lost UAV's sectors are never searched (about 87 % coverage).

### Hysteresis suppresses chattering under sensor noise

![Hysteresis vs sensor noise](figures/hysteresis_vs_sensor_noise.png)

{noise_tbl}

Without hysteresis every replan commits, so battery-sensor noise keeps moving sector borders. Commits are about
{mean(("noise","sigma_2","Hysteresis OFF"),"partition_commits")/mean(("noise","sigma_2","Hysteresis ON"),"partition_commits"):.0f}× fewer with hysteresis, and the gap in sector flips widens as noise grows.

### EW-CVT exponent α: time versus energy reserve

![alpha sweep](figures/alpha_sweep.png)

{alpha_tbl}

Larger α shrinks weak UAVs' territory, which raises the minimum remaining battery and reduces low-battery aborts but lengthens the mission, because
healthy UAVs carry more of the work. α is a dial between speed and energy safety; it is not a free improvement.
Coverage is 100 % at every α, so the third panel is flat.

## 3. Networking: delay-tolerant mesh and multi-hop

{net_tbl}

![Network ablation](figures/network_ablation.png)

Under the RF model (log-distance path loss, exponent 2.5, 4 dB shadowing) direct links reach only a few hundred metres, so
the swarm is mostly disconnected in flight and first-attempt delivery to the GCS is low everywhere. Store-and-forward queues
alerts in the UAV's buffer and flushes them when it returns to base, which turns a mostly-offline swarm into one the operator can
rely on. Multi-hop relaying adds nothing here: a relay must be closer to *both* endpoints, which rarely holds in a sparse swarm.

## 4. Scaling with swarm size

![Scaling](figures/scaling.png)

{scale_tbl}

Time falls and per-UAV energy falls as the swarm grows; the speedup is sublinear because transit from the base is a fixed cost.
The small non-monotonicity between 4 and 6 UAVs is probably an artefact of how starting territories are laid out (corners for ≤ 4, a ring for more); this has not been verified.

## What these results do and do not show

- **Simulation, not flight.** Dynamics are kinematic (constant speed, linear battery drain). The EW-CVT, hysteresis, failover and DTN logic is real code under test; the aircraft and radio are models.
- **Detection inside missions replays static frames.** Each sector shows one image, so mission-level precision and recall mostly reflect the detector on those frames plus sector coverage.
- **Network results depend on the RF model** (33 dBm at 2.4 GHz for arenas ≥ 2 km, 30 dBm at 5 GHz below). Real links would differ.
- **Assumptions.** The 15 % abort rule and the 0–4 % battery-sensor-noise levels are scenario assumptions (noise is swept above).
- **Re-planning is not free.** In the nominal case the static baseline finishes about {mean(full_n,'makespan_s')-mean(ck(NOM,'Static baseline'),'makespan_s'):.0f} s sooner than the full system, but it also leaves some sectors unsearched even without any failure
  ({mean(ck(NOM,'Static baseline'),'coverage_pct'):.1f} % coverage), because weak-battery UAVs abort.
- **Earlier numbers superseded.** An earlier version of the simulator let UAVs teleport to their first waypoint and then drift back toward the launch pad, which invalidated mission time,
  time-to-first-detection, energy and hysteresis statistics (the benchmark table in the top-level `README.md` came from that version). That is fixed; detection precision, recall and localization were unaffected. The numbers in this document replace them.

## Reproduce

```bash
source FlySim/venv/bin/activate

python ablation/perception_eval.py --n 150          # ~20 min on CPU  -> results/ablation/perception.json
python ablation/run_ablation.py --seeds {N}            # ~1 min after detector cache is warm -> results/ablation/runs.json
python ablation/make_report.py                       # -> results/final_report.html + results/figures/*.png
python ablation/make_readme.py                       # -> this file
```

Each switch can also be used from the single-mission CLI, for example:

```bash
python simulate_swarm_mission.py --drones 6 --arena 5000 --duration 900 \\
    --batt-min 20 --batt-noise 1.5 --fail-drone 2 --fail-time 80 \\
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
"""
open(os.path.join(ROOT, "results", "README.md"), "w").write(doc)
open(os.path.join(ROOT, "results", "headline_table.md"), "w").write(headline + "\n")   # reused by the top-level README
print("wrote results/README.md", len(doc), "chars")
