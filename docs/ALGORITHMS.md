# Algorithms in FlyNetSim

A plain-language guide to every algorithm in the project: the ones we use in the proposed system and the ones we compare against. Numbers (thresholds, constants) are the defaults used in the paper (`paper/swarm_sar_paper.tex`) and the simulator (`simulate_swarm_mission.py`).

The system has three parts, and every UAV runs all three on its **own, possibly outdated view** of the swarm (there is no central planner):

1. **Perception** – find people in camera frames.
2. **Mesh communication** – get alerts and status around over a radio that is mostly out of range.
3. **Control** – decide which sectors to search and notice when a peer is lost.

The ground control station (GCS) is a passive sink: it receives alerts and plans nothing.

---

## 1. Perception

### 1.1 4-channel RGB + thermal early-fusion YOLO11s (ours)
- The visible (RGB) and thermal (long-wave infrared) frames are stacked into one 4-plane image; the first convolution of the detector takes 4 input channels.
- Model: YOLO11s, input 1280 px, one class (person). Trained on the NII-CU Multispectral Aerial Person Detection dataset.
- Thermal kernel is initialised from the pretrained **red** kernel (same trick as Speth et al.); no colour jitter in training (meaningless for thermal).
- **Georeferencing**: the centre of a detected box is mapped linearly into the bounds of the sector the frame came from. This is sector-based, not a camera model.
- Why early fusion: it adds almost no compute (cheap enough for onboard use) and lets the network use thermal when light is bad.

### 1.2 Detector evaluation conditions
- **Day**: frames unchanged.
- **Night**: RGB multiplied by 0.12 plus Gaussian noise (σ = 4); thermal untouched.
- **Thermal washout**: thermal contrast squeezed to 25 % of the mean plus noise (σ = 5); RGB untouched (people and background at nearly the same temperature).
- **RGB-only / Thermal-only**: the other plane is set to zero. This is *masked inference of one fused network*, not separately trained models.
- Night and washout are synthetic degradations of daytime frames, not recorded data.

### 1.3 Compared against: Speth et al. 2022 (base paper)
YOLOv3 trained on the same dataset in four ways: RGB only, thermal (FIR) only, an RGB+FIR **ensemble** (two networks, results merged), and the **4-channel** early-fusion model. Their Table 9 (485 aligned images, 891 people): AP50 / AP75 = 92.4 / 44.5, 97.5 / 72.7, 97.3 / 54.7, 97.9 / 76.9. Ours (YOLO11s, 150-frame subset): 99.8 / 85.8. Not a like-for-like comparison: different architecture and input size, subset evaluation, checkpoint selected on the same split.

---

## 2. Mesh communication

### 2.1 Radio channel model
- Log-distance path loss: `PL(d) = PL(d0) + 10·n·log10(d/d0) + Xσ + Δobs`, with `n = 2.5`, `d0 = 1 m`, shadowing σ = 4 dB, and a 15 dB extra loss on obstructed links (random 10 % chance beyond 50 m). Noise floor −90 dBm.
- SNR → packet error rate: PER = 0 above 25 dB, 1 below 5 dB, logistic in between.
- Arenas ≥ 2 km: 33 dBm at 2.4 GHz (PER ≈ 0.5 at ≈ 520 m). Smaller arenas: 30 dBm at 5 GHz (≈ 220 m). In a multi-km arena the swarm is **mostly disconnected in flight**.

### 2.2 Alert generation and buffering (ours)
When a UAV detects a victim it makes **one direct attempt** to reach every other UAV and the GCS. Each failed copy goes into a **per-recipient QoS-1 buffer** (retained until delivered). A buffer is flushed when the link to that recipient has PER < 0.2 – in practice when the UAV returns to base.

### 2.3 Store-carry-forward relaying = epidemic forwarding (ours)
A UAV that *receives* an alert also keeps a copy for every recipient not known to hold it, and hands it over when it later meets that recipient with a good link. No UAV has to be in the right place at the right moment, and an alert survives the loss of its finder. On contact only the copies the other side lacks are sent; a full buffer drops its oldest copy. Based on Vahdat & Becker (2000).

### 2.4 Status messages (ours)
Every **5 s** each UAV broadcasts: position, committed EW-CVT generator and weight, state, the time its route should bring it home, its sector claims, and the set of sectors it knows are scanned. They are single-hop and **not buffered** (stale state is not worth delivering late). Receivers merge the scanned sets as **grow-only sets**, so knowledge of coverage spreads transitively when UAVs meet.

### 2.5 Compared against: forwarding baselines
All replace *only* the relaying policy in the same simulator (same missions, radio, seeds).

| Policy | How it decides | Copies |
|---|---|---|
| **Epidemic** (ours) | give a copy to every UAV met that lacks one | many |
| **Spray-and-Wait** (Spyropoulos 2005), L = 3 | each alert gets 3 copies; the holder halves its copies at each hand-over, then waits to deliver directly | ≤ 3 |
| **Buffer only** | the finder carries each alert home itself; no relaying | 1 |

Metric *copies per alert* = number of UAVs holding a copy at the end (traffic cost).

**Finding:** epidemic has the lowest alert latency but the most copies; the others trade a few seconds of latency for fewer copies.

---

## 3. Control

### 3.1 EW-CVT: energy-weighted centroidal Voronoi tessellation (ours)
- Each UAV *i* has weight `w_i = (B_i / B_max)^α` (default α in the simulator config).
- A sector with centre `c_s` is preferred by the UAV with the smallest weighted distance
  `d(s,i) = ‖c_s − g_i‖² / max(0.01, w_i)` where `g_i` is the UAV's *committed* generator.
- α = 0 gives a plain Voronoi diagram; larger α **shrinks the territory of low-battery UAVs**, so healthy UAVs do more of the work.
- The launch partition is the converged CVT (15 Lloyd iterations: move each generator to the centroid of its cell, repeat).
- Technically a multiplicatively weighted Voronoi diagram, not a power diagram.

### 3.2 Dual-threshold hysteresis (ours)
Every 5 s a UAV computes the centroid `C_i*` its cell *should* have, over the peers it **believes** are active. It only **commits** the new generator and weight if
`(ΔB ≥ 2 % of B_max AND ‖C* − C‖ ≥ 5 m)  OR  (its view of the live set changed)`.
Without this gate, noisy battery readings (σ = 1.5 points) would trigger a new partition every tick (route churn).

### 3.3 Claim-and-yield sector assignment (ours)
- A UAV **claims** a sector if it is the preferred owner by `d(s,i)` (using committed values) and nobody else holds a valid claim.
- It **keeps** its claims unless a better claim (smaller `d`, ties broken by id) reaches it – it then **yields**.
- It may take over a peer's claim only if it would arrive well before that peer's advertised arrival time.
- A UAV with no claims left takes the nearest unclaimed sector.
- Routes are greedy nearest-neighbour tours ending at the launch pad.

### 3.4 Lease-based failure detection and failover (ours)
- In flight, **silence tells nothing**: a quiet peer may be out of range or landed. So each peer advertises the time its route should bring it home (its **sortie lease**; idea from Gray & Cheriton's leases).
- A peer still missing **slack** seconds after that time (default **60 s**) is *suspected*; its claims are released.
- Since a lost UAV looks like one that landed quietly, released work is taken **only by UAVs at base** (which have heard the landed peers). Landed UAVs listen for 10 s, split the work by `d(s,i)`, and relaunch if the battery allows.
- A suspicion is withdrawn if the peer is heard again.
- A UAV aborts and returns home at 15 % battery; it is lost at 0 %.
- **Lease slack trade-off**: short slack = faster detection but more wrong suspicions (mostly landed UAVs that look crashed). Slack 20/60/120/240 s gives mean failover latency 192/231/293/411 s and wrong suspicions falling from 11.2 of 15.6 to 0.4 of 4.7 per mission. Wrong suspicions cost little because released work is only taken at base.

Control tick (every 5 s): merge received status → mark overdue peers suspected / release claims → build the believed-active set → compute EW-CVT centroid → apply the hysteresis gate → keep non-beaten claims, add preferred free sectors → if idle, claim the nearest unclaimed sector (and share released work if at base) → rebuild the route if needed.

### 3.5 Compared against: allocation baselines
| Policy | What it does |
|---|---|
| **EW-CVT** (ours) | full scheme above (energy-weighted partition + hysteresis + claims + lease failover) |
| **Auction, no failover** | assign each sector to the nearest UAV (all weights = 1); lost UAVs' sectors are never reassigned |
| **Static partition** | fixed launch partition; no reassignment at all |

**Findings:** failover is what drives the coverage gain after a loss (98.4 % vs 89.2 % without; static 87.6 %). The price is a longer mission after a loss (554 s vs about 340 s), because the survivors take over the lost work.

---

## 4. Metrics (how the algorithms are scored)
- **Coverage**: share of sectors scanned at least once. **Mission time**: until completion or 1,500 s.
- **Precision / recall**: reported victims matched to ground truth within 15 m, one-to-one. **Operator recall**: only victims whose alert reached the GCS. **Alert latency**: detection → arrival at the GCS.
- **Failover latency**: injected failure → first claim of its sectors by a survivor.
- **Duplicate scans**, **sector flips** (claims given up for a better one), **route changes**, **commits** (hysteresis-approved updates).
- **Copies per alert**: UAVs holding a copy at the end (traffic cost).
- Protocol: paired seeds (each seed fixes the sector frames and launch batteries so every variant sees the same worlds); results as paired differences with 95 % CIs; no effect claimed when the CI contains zero.

## 5. References for the compared methods
- Speth et al., *Deep learning with RGB and thermal images onboard a drone for monitoring operations*, J. Field Robotics 39(6), 2022 (base paper, dataset).
- Vahdat & Becker, *Epidemic routing for partially connected ad hoc networks*, 2000.
- Spyropoulos et al., *Spray and wait*, 2005.
- Gray & Cheriton, *Leases*, 1989.
