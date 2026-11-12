# System Architecture: Diagram Proposal

Proposed set of architecture diagrams for the UAV-swarm SAR system. Each one answers a single question a
reviewer is likely to ask, and each is drawn from the **current code** (not from the earlier paper figure).
The diagrams are Mermaid so they render on GitHub; once the set is agreed they can be redrawn in TikZ for the paper.

| # | Diagram | The question it answers | Priority |
|---|---|---|---|
| D1 | System overview | What are the parts and how do they relate? | **Core** (one-slide architecture) |
| D2 | Per-UAV pipeline | What runs on each aircraft, from pixels to alert? | **Core** |
| D3 | Swarm control loop | How does EW-CVT + hysteresis decide who searches where? | **Core** |
| D4 | Hysteresis gate | When exactly does the controller change its mind? | Supporting |
| D5 | Alert dissemination and DTN | How does a victim alert reach the operator when links are down? | **Core** |
| D5b | Packet delivery algorithm | What exactly happens to one alert packet, step by step? | **Core** |
| D5c | Forwarding policies compared | How do epidemic, spray-and-wait and buffer-only differ? | Supporting |
| D6 | UAV state machine | What states can a UAV be in and what moves it between them? | Supporting |
| D7 | Failure and failover | What happens when a UAV is lost or runs low on battery? | Supporting |
| D8 | Software module map | Where does each idea live in the code? | Appendix |
| D9 | Evaluation architecture | How do the ablation switches map to the measured results? | **Core** (bridges to results) |

Suggested presentation order: D1 → D2 → D3 (with D4 as a zoom) → D5 → D9, with D6, D7 and D8 as backup slides.

---

## D1. System overview

Three contributions sit inside every UAV; the mission layer and the operator sit around them.

```mermaid
flowchart TB
  ARENA["Search arena<br/>K sectors, one RGB + thermal frame each"]
  GCS["Ground Control Station<br/>passive alert sink, no planning"]

  subgraph UAV["Every UAV (x N): its own view, its own decisions, no central planner"]
    direction TB
    PERC["<b>1. Perception</b><br/>4-channel early fusion, YOLO11s, 1280 px<br/>box to sector position to alert (victim, time)"]
    COMM["<b>2. Mesh communications</b><br/>log-distance RF link gives PER<br/>status message every 5 s, single hop<br/>per-recipient QoS-1 buffers, flushed when PER < 0.2<br/>store-carry-forward with buffer cap"]
    CTRL["<b>3. Swarm control</b><br/>view of peers built from received status messages<br/>EW-CVT weight w = (B/Bmax)^alpha<br/>dual-threshold hysteresis<br/>claim and yield on sectors<br/>sortie lease: release work at base"]
    FLT["<b>Flight and battery</b><br/>route over own sectors, 15 % reserve, return to base"]
    PERC -- "alerts" --> COMM
    COMM -- "peer state: position, claims, scanned sectors" --> CTRL
    CTRL -- "sector route" --> FLT
    FLT -- "position, battery" --> CTRL
    FLT -- "position" --> COMM
  end

  PEERS["Peer UAVs<br/>lossy, often disconnected"]

  ARENA -- "frames" --> PERC
  GCS -- "launch" --> FLT
  COMM -- "alerts: on contact, or at return to base" --> GCS
  COMM <-->|"status messages and alerts"| PEERS
```

**Say:** each UAV carries a perception stack, a comms stack and a control stack. They interact through
three narrow interfaces: alerts (perception to comms), a sector route (control to flight), and peer beacons (comms to control). There is no central planner: control works only from the beacons this UAV has actually received.

---

## D2. Per-UAV pipeline

From sensor to operator, on one aircraft.

```mermaid
flowchart TB
  subgraph SENSE["Sensing"]
    RGB["Visible camera<br/>RGB"]
    THM["Thermal camera<br/>LWIR"]
  end
  subgraph VISION["Perception"]
    FUSE["Early fusion<br/>stack to 4-channel tensor,<br/>model-specific channel order"]
    DET["YOLO11 detector<br/>conf threshold 0.20"]
    GEO["Georeference<br/>box centre to sector coordinates"]
    DEDUP["Local and swarm-wide<br/>target de-duplication"]
  end
  subgraph NET["Comms"]
    ALERT["Alert<br/>key, class, conf, x, y"]
    SEND["Send to every UAV and the GCS<br/>one direct attempt each"]
    BUF["QoS-1 buffer<br/>per recipient"]
    FWD["Receivers keep copies and<br/>forward on later contact"]
  end
  RGB --> FUSE
  THM --> FUSE
  FUSE --> DET --> GEO --> DEDUP --> ALERT --> SEND
  SEND -- "failed" --> BUF
  BUF -. "flush when link PER < 0.2" .-> SEND
  SEND -- "received by a peer" --> FWD
  FWD -. "flush to recipients that lack it" .-> SEND
```

**Notes for accuracy:** georeferencing is a linear map from the box centre in the frame to the sector's bounds
(each sector is represented by one frame); it is **not** a pinhole camera model.

---

## D3. Swarm control loop (EW-CVT + hysteresis + claims), per UAV

Runs on **every UAV** every 5 s of mission time, from that UAV's own view only. There is no central planner. The hysteresis gate decides whether the UAV's territory parameters change.

```mermaid
flowchart TD
  BEACON["Peer beacons received over RF<br/>position, committed g, w, state,<br/>return ETA, claims, scanned sectors"] --> VIEW["Local view<br/>peers, claims, scanned set"]
  TICK["Replan tick, every 5 s"] --> EXP["Expire leases:<br/>peer overdue back at base + slack<br/>=> suspected lost, claims released"]
  VIEW --> EXP
  EXP --> MEAS["Read own battery B_i<br/>(with sensor noise)"]
  MEAS --> WGT["Fresh weight<br/>w*_i = (B_i / Bmax)^alpha"]
  WGT --> CENT["EW-CVT centroid C*_i over peers<br/>believed active, using their<br/>advertised g and w"]
  CENT --> GATE{"Hysteresis gate<br/>(see D4)"}
  GATE -- "locked" --> KEEP["Keep committed g_i and w_i"]
  GATE -- "commit" --> NEW["g_i = C*_i,  w_i = w*_i"]
  KEEP --> CLAIM
  NEW --> CLAIM["Claim sectors:<br/>keep mine unless a better claim beats it,<br/>take free sectors I am best for,<br/>take released work only if at base,<br/>idle: nearest leftover"]
  CLAIM --> CHG{"My claim set<br/>changed?"}
  CHG -- "yes" --> ROUTE["Rebuild route:<br/>nearest-neighbour tour, then return to pad"]
  CHG -- "no" --> FLY["Keep flying current route"]
  ROUTE --> FLY
  FLY --> OUT["Advertise route ETA and claims<br/>in my next beacon"]
```

**Say:** alpha = 0 gives ordinary Voronoi; larger alpha shrinks low-battery UAVs' territories.
Because claiming uses only *committed* values, a locked gate means few ownership flips and little re-routing.
A test-only mode (`--planner centralized`) recomputes the partition from true state at every tick; it is used only for the hysteresis experiment.

---

## D4. Hysteresis gate

The dual-threshold rule with the topology override.

```mermaid
flowchart TD
  IN["Inputs: battery B_i(t), centroid C*_i(t),<br/>this UAV's view of the live set N(t)"] --> Q1{"N(t) differs from<br/>N(t_k)?"}
  Q1 -- "yes" --> FORCE["FORCED OVERRIDE<br/>commit immediately"]
  Q1 -- "no" --> Q2{"Battery down >= 2% of Bmax<br/>since last commit?"}
  Q2 -- "no" --> LOCK["LOCK<br/>keep g_i, w_i<br/>(chattering suppressed)"]
  Q2 -- "yes" --> Q3{"Centroid moved >= 5 m<br/>since last commit?"}
  Q3 -- "no" --> LOCK
  Q3 -- "yes" --> COMMIT["COMMIT<br/>g_i = C*_i, w_i = w*_i<br/>reset baseline t_k"]
```

---

## D5. Alert dissemination and delay-tolerant delivery

Why the operator still learns about victims when the swarm is mostly out of radio range.

```mermaid
sequenceDiagram
  participant U as Detecting UAV
  participant P as Peer UAV
  participant G as GCS (at base)

  U->>U: detect, georeference, de-duplicate
  par to every other UAV and the GCS
    U->>P: alert over direct RF link (succeeds with probability 1 - PER)
  and
    U->>G: alert over direct RF link
  end
  alt undelivered and DTN enabled
    U->>U: keep a copy in the QoS-1 buffer for that recipient
  else DTN disabled
    Note over U: message is lost
  end
  opt peer received it and forwarding enabled
    P->>P: keep a copy for every recipient not known to hold it
  end
  Note over U,G: later, any holder meets a recipient (often at base)
  P->>G: flush copies the recipient lacks once link PER < 0.2
  U->>G: or the finder itself flushes
  G->>G: record first-known time (alert latency)
```

Because any UAV that received the alert carries it onward, the alert survives the finder being lost.

**RF model behind PER:** log-distance path loss (exponent 2.5), 4 dB shadow fading, 15 dB obstruction penalty,
SNR mapped to PER over 5 to 25 dB; 33 dBm at 2.4 GHz for arenas of 2 km or more, otherwise 30 dBm at 5 GHz.

---

## D5b. Packet delivery algorithm (what happens to one alert)

Decision flow for a single victim alert, as implemented in `simulate_swarm_mission.py`
(`_broadcast_alert`, `_try_deliver`, `_queue_copy`, `_receive_alert`, `_flush_buffers`).

```mermaid
flowchart TD
  DET["UAV detects a victim<br/>georeference box to sector position<br/>key = TGT_sector_x_y"] --> DUP{"Already known<br/>to this UAV?"}
  DUP -- "yes" --> STOP1["ignore (de-duplicated)"]
  DUP -- "no" --> SEND["For every recipient r<br/>(each other UAV and the GCS):<br/>ONE direct radio attempt"]
  SEND --> PER{"Delivered?<br/>random draw vs PER from SNR<br/>(dead UAV never receives)"}
  PER -- "yes" --> RX["r receives the alert<br/>r records it, marks it known"]
  PER -- "no" --> DTN{"DTN buffering<br/>enabled?"}
  DTN -- "no" --> LOST["copy lost"]
  DTN -- "yes" --> BUF["QoS-1 buffer for r<br/>one queue per recipient<br/>buffer cap: drop OLDEST copy"]
  RX --> ISGCS{"r is the GCS?"}
  ISGCS -- "yes" --> DONE["first-known time recorded<br/>= alert latency stops"]
  ISGCS -- "no (peer UAV)" --> FWD{"store-carry-forward<br/>enabled?"}
  FWD -- "no" --> END1["peer holds the alert only"]
  FWD -- "yes" --> CARRY["peer queues a copy for every<br/>recipient NOT known to hold it<br/>(its own fwd_known set)"]
  BUF --> TICK
  CARRY --> TICK
  subgraph LATER["Every simulation tick, for every alive UAV with buffered copies"]
    TICK{"Link to recipient<br/>good? PER below 0.2"} -- "no" --> WAIT["keep carrying"]
    TICK -- "yes (contact, often at base)" --> CHK{"Recipient already<br/>holds it, or GCS<br/>already told?"}
    CHK -- "yes" --> DROP["discard copy,<br/>mark recipient as holder"]
    CHK -- "no" --> HAND["hand over the copy<br/>(delivered late)"]
  end
  HAND --> RX
```

Key properties:
- **Direct first, then carry.** There is no routing table. The only network operation is a point-to-point attempt; everything indirect is *store-carry-forward*.
- **Per-recipient buffers** mean a copy for the GCS and a copy for each peer are tracked and flushed independently.
- **Contact-triggered:** a hand-over happens only when the link to the recipient is good (PER below 0.2), which for the GCS in a large arena usually means when a holder returns to base.
- **Only the missing copies are sent** (`fwd_known` and the recipient's own holdings are checked), so a pair of UAVs that meet exchange only what the other lacks.
- **Survives the finder's loss:** any UAV that received the alert is itself a carrier.

---

## D5c. Forwarding policies compared

The baselines replace *only* the GCS-bound relaying step; detection, direct attempts and buffers are identical.
Contacts are UAV pairs with PER below 0.2. Each policy answers one question when carrier **x** meets peer **y**
that does not hold alert `k`: *should x give y a copy?*

```mermaid
flowchart LR
  C["Contact: x carries alert k,<br/>y does not hold k, link good"] --> P{"Policy"}
  P --> E["<b>Epidemic (ours)</b><br/>always give a copy<br/>x keeps its copy<br/>many copies, lowest latency"]
  P --> S["<b>Spray-and-Wait, L=3</b><br/>if x has more than 1 token:<br/>give floor(tokens/2) to y<br/>else wait for direct delivery<br/>at most 3 copies"]
  P --> B["<b>Buffer only</b><br/>never relay<br/>the finder carries it home"]
```

| Policy | Copies after a hand-over | Needs | Traffic cost |
|---|---|---|---|
| Epidemic (ours) | x and y both hold | nothing | highest |
| Spray-and-Wait | tokens split between x and y | copy budget L | at most L |
| Buffer only | only the finder holds | nothing | one copy |

---

## D6. UAV state machine

```mermaid
stateDiagram-v2
  [*] --> TRANSIT: launch from pad
  TRANSIT --> SEARCHING: first sector reached, scan
  SEARCHING --> SEARCHING: next sector reached, scan
  SEARCHING --> RETURNING: no sectors pending
  RETURNING --> SEARCHING: claims new sectors before landing
  TRANSIT --> RETURNING: battery at or below 15%
  SEARCHING --> RETURNING: battery at or below 15%
  RETURNING --> LANDED: reached pad
  TRANSIT --> CRASHED: motor failure or battery 0%
  SEARCHING --> CRASHED: motor failure or battery 0%
  RETURNING --> CRASHED: motor failure or battery 0%
  LANDED --> TRANSIT: relaunch for released work (after listening on the pad)
  LANDED --> [*]
  CRASHED --> [*]
```

Speeds: transit and return up to 50 m/s; search cruise up to 32 m/s. Battery drains faster in transit than in search.

---

## D7. Failure and failover

```mermaid
sequenceDiagram
  participant E as Event
  participant D as Dead UAV (silent)
  participant S as Surviving UAV (own view)
  participant B as At base (landed survivors)

  E->>D: motor failure or 0% battery
  Note over S: No signal. Silence in flight is normal.
  S->>S: peer's advertised return time passes, plus lease slack
  S->>S: peer suspected lost, claims released, view of live UAVs changes
  S->>S: hysteresis forced override (topology changed)
  alt failover enabled
    S->>B: released sectors are taken only by UAVs at base
    B->>B: landed UAVs share the work by weighted distance and relaunch
  else failover disabled
    S->>S: released sectors stay unsearched
  end
  Note over D,B: A peer that only landed and went quiet looks the same as a dead one until a UAV reaches base
```

---

## D8. Software module map

Where each idea lives. The ArduPilot / ns-3 path is a separate, hardware-in-the-loop route and does not run in the Python mission simulator.

```mermaid
flowchart LR
  subgraph ENTRY["Entry points"]
    DEMO["demo.py<br/>Gradio console"]
    CLI["simulate_swarm_mission.py<br/>CLI"]
    VAL["validate_swarm_mission.py<br/>validator and figures"]
    ABL["ablation/<br/>perception_eval, run_ablation,<br/>make_report, make_readme"]
  end

  subgraph CORE["Mission simulator"]
    SIM["SwarmSimulation<br/>SimulatedUAV"]
  end

  subgraph SERVICES["Components under study"]
    DETM["rgbt_detector.py<br/>RGBTDetector"]
    CTRLM["FlySim/hysteresis_controller.py<br/>EW-CVT + dual-threshold gate"]
    AGENT["FlySim/swarm_agent.py<br/>per-UAV view, claims, leases"]
    NETM["FlySim/swarm_network.py<br/>RF physics, EdgeBroker"]
    WORLD["sar_world.py<br/>SARWorld"]
  end

  subgraph DATA["Data and models"]
    FR["NII-CU frames and labels"]
    W["best.pt<br/>4-channel YOLO11"]
  end

  subgraph OUT["Outputs"]
    LOGS["metrics CSVs, mission JSON"]
    RES["results/<br/>README, report, figures"]
  end

  subgraph SITL["Separate path: hardware-in-the-loop"]
    FN["FlySim/FlyNetSim.py<br/>uav_pubsub.py"]
    AP["ArduPilot SITL + ns-3"]
  end

  DEMO --> SIM
  CLI --> SIM
  ABL --> SIM
  SIM --> DETM
  SIM --> CTRLM
  SIM --> AGENT
  SIM --> NETM
  SIM --> WORLD
  WORLD --> FR
  DETM --> W
  SIM --> LOGS
  LOGS --> VAL
  ABL --> RES
  FN --> AP
  FN -. "uses" .-> CTRLM
```

---

## D9. Evaluation architecture

How each switch removes one component and which measurements change. This links the architecture to the results.

```mermaid
flowchart LR
  subgraph KNOBS["Ablation switches"]
    K1["Input masking<br/>fused / RGB only / thermal only"]
    K2["DTN buffer on or off<br/>forwarding on or off<br/>buffer cap"]
    K3["EW weighting alpha<br/>hysteresis on or off<br/>failover on or off<br/>dynamic replanning on or off"]
    K4["Control parameters<br/>lease slack, beacon interval"]
    K5["Baselines<br/>forwarding: spray-and-wait, buffer only<br/>allocation: auction without failover, static"]
    SC["Scenario<br/>swarm size, arena, battery spread,<br/>sensor noise, UAV loss"]
  end

  K1 --> EVAL["Detector evaluation<br/>held-out frames, day / night / washout"]
  K2 --> SIMX["Mission simulator<br/>paired seeds"]
  K3 --> SIMX
  K4 --> SIMX
  K5 --> SIMX
  SC --> SIMX

  EVAL --> M1["AP50, precision, recall, F1"]
  SIMX --> M2["Coverage, recall over whole arena,<br/>mission time, distance"]
  SIMX --> M3["Min battery, aborts,<br/>sector flips, route changes, commits"]
  SIMX --> M4["Operator recall, alert latency,<br/>consensus, messages lost,<br/>copies per alert"]
  SIMX --> M5["Failover latency, duplicate scans,<br/>false suspicions, control messages"]

  M1 --> REP["Final report"]
  M2 --> REP
  M3 --> REP
  M4 --> REP
  M5 --> REP
```

---

## Decisions needed before drawing

1. **Scope of "the system":** present only the Python mission simulator (what the results measure), or also the ArduPilot/ns-3 SITL path as a deployment route? Proposal: simulator in D1 to D7, SITL only in D8.
2. **Format:** keep Mermaid for GitHub and rebuild D1, D3 and D5 in TikZ for the paper, or produce one set only?
3. **Detail level for the professor:** D1 on its own may be enough for the main slide, with D3 and D5 as the two "how it works" slides. Say if you want fewer or more.
4. **Numbers on the diagrams:** which thresholds to show (2 %, 5 m, 5 s replan, 15 % reserve, RF parameters)? Proposal: show them only on D3, D4 and D5.
