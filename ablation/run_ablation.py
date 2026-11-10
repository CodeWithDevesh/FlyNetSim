#!/usr/bin/env python3
"""
Swarm ablation harness.

Every experiment is a SwarmSimulation configuration run over several seeds. A seed fixes the
world (which dataset frame sits in which sector) and each UAV's launch battery, so the same
seed is a *paired* comparison across configurations.

Groups
  control   : EW-CVT / hysteresis / failover / dynamic re-planning      (nominal + UAV-loss scenario)
  network   : store-and-forward (DTN) / multi-hop relaying              (across arena sizes)
  noise     : hysteresis on/off vs battery-sensor noise                 (churn)
  alpha     : EW-CVT exponent sweep                                     (time vs energy-reserve trade-off)
  scale     : swarm size sweep

All output goes to results/ablation/ - nothing in the repo root is touched.
"""
import os, sys, io, json, time, argparse, contextlib, multiprocessing as mp
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "FlySim"))

OUT = os.path.join(ROOT, "results", "ablation")
CACHE = os.path.join(OUT, "det_cache.pkl")
MAX_SIM_SECONDS = 1500

BASE = dict(num_drones=6, arena_size=5000.0, grid_dim=5, conf_thresh=0.20, model_path=os.path.join(ROOT, "best.pt"),
            ewcvt_alpha=1.0, hysteresis_enabled=True, failover_enabled=True, dynamic_repartition=True,
            dtn_enabled=True, multihop_enabled=True, initial_battery_range=(20.0, 100.0),
            battery_noise_std=1.5, fail_drone_id=None, fail_time=None)

FAIL = dict(fail_drone_id=2, fail_time=80.0)

CONTROL_VARIANTS = {
    "Full system":              {},
    "- EW weighting (alpha=0)": dict(ewcvt_alpha=0.0),
    "- Hysteresis":             dict(hysteresis_enabled=False),
    "- Failover":               dict(failover_enabled=False),
    "Static baseline":          dict(ewcvt_alpha=0.0, dynamic_repartition=False, failover_enabled=False,
                                     hysteresis_enabled=False),
}
NETWORK_VARIANTS = {
    "Full (DTN + multi-hop)": {},
    "- DTN buffer":           dict(dtn_enabled=False),
    "- Multi-hop":            dict(multihop_enabled=False),
    "- Both (direct only)":   dict(dtn_enabled=False, multihop_enabled=False),
}


def build_experiments(quick=False):
    ex = []
    def add(group, scenario, name, **over):
        cfg = dict(BASE); cfg.update(over)
        ex.append(dict(group=group, scenario=scenario, name=name, cfg=cfg))

    # --- control ablation -------------------------------------------------------------
    for name, o in CONTROL_VARIANTS.items():
        if name != "- Failover":                     # identical to full when nobody fails
            add("control", "nominal", name, **o)
    for name, o in CONTROL_VARIANTS.items():
        add("control", "uav_loss", name, **{**o, **FAIL})
    # --- network ablation (equal batteries, no failure, three arena sizes) ----------------
    for arena in (1500.0, 3000.0, 5000.0):
        for name, o in NETWORK_VARIANTS.items():
            add("network", f"arena_{int(arena)}", name, arena_size=arena, initial_battery_range=(100.0, 100.0),
                battery_noise_std=0.0, **o)
    if quick:
        return ex
    # --- hysteresis vs sensor noise -------------------------------------------------------
    for sigma in (0.0, 1.0, 2.0, 4.0):
        add("noise", f"sigma_{sigma:g}", "Hysteresis ON", battery_noise_std=sigma)
        add("noise", f"sigma_{sigma:g}", "Hysteresis OFF", battery_noise_std=sigma, hysteresis_enabled=False)
    # --- alpha sweep ------------------------------------------------------------------------
    for a in (0.0, 0.5, 1.0, 2.0, 3.0):
        add("alpha", f"alpha_{a:g}", f"alpha={a:g}", ewcvt_alpha=a, initial_battery_range=(15.0, 100.0))
    # --- swarm size ---------------------------------------------------------------------------
    for n in (2, 4, 6, 8, 12):
        add("scale", f"n_{n}", f"{n} UAVs", num_drones=n, initial_battery_range=(100.0, 100.0), battery_noise_std=0.0)
    return ex


def run_one(job):
    exp, seed = job
    from simulate_swarm_mission import SwarmSimulation
    cfg = dict(exp["cfg"])
    t0 = time.time()
    with contextlib.redirect_stdout(io.StringIO()):
        sim = SwarmSimulation(seed=seed, out_dir=OUT, write_logs=False, verbose=False, **cfg)
        for _ in sim.run_streaming(max_sim_seconds=MAX_SIM_SECONDS, dt=1.0, yield_interval=1e9):
            pass
    m = sim.collect_metrics()
    ts = [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in row.items()} for row in sim.timeseries[::5]]
    return dict(group=exp["group"], scenario=exp["scenario"], name=exp["name"], seed=seed,
                metrics=m, timeseries=ts, wall_s=round(time.time() - t0, 2),
                init_battery=[round(d.initial_battery, 1) for d in sim.drones])


def warm_cache(seeds, workers_note=""):
    """Run the detector once per distinct frame; everything after is a dict lookup."""
    import simulate_swarm_mission as S
    n0 = S.load_detection_cache(CACHE)
    paths = set()
    with contextlib.redirect_stdout(io.StringIO()):
        for s in seeds:
            sim = S.SwarmSimulation(num_drones=1, arena_size=5000.0, seed=s, write_logs=False, verbose=False,
                                    model_path=BASE["model_path"])
            paths.update(sec["image_path"] for sec in sim.world.sectors.values())
    todo = [p for p in sorted(paths) if (os.path.basename(BASE["model_path"]), p, 0.2) not in S._DET_CACHE]
    print(f"[warm] {len(paths)} distinct frames needed, {len(todo)} not cached (cache had {n0})", flush=True)
    if todo:
        import torch; torch.set_num_threads(6)
        with contextlib.redirect_stdout(io.StringIO()):
            sim = S.SwarmSimulation(num_drones=1, arena_size=5000.0, seed=seeds[0], write_logs=False, verbose=False,
                                    model_path=BASE["model_path"])
        t0 = time.time()
        for i, p in enumerate(todo):
            sim._detect(p)
            if (i + 1) % 20 == 0:
                print(f"  detected {i+1}/{len(todo)}  ({(time.time()-t0)/60:.1f} min)", flush=True)
        S.save_detection_cache(CACHE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--quick", action="store_true", help="control+network groups only")
    ap.add_argument("--out", default=os.path.join(OUT, "runs.json"))
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    seeds = list(range(args.seeds))
    exps = build_experiments(args.quick)
    jobs = [(e, s) for e in exps for s in seeds]
    print(f"[ablation] {len(exps)} configurations x {len(seeds)} seeds = {len(jobs)} missions", flush=True)

    warm_cache(seeds)
    t0 = time.time()
    results = []
    ctx = mp.get_context("fork")
    with ctx.Pool(args.workers) as pool:
        for i, r in enumerate(pool.imap_unordered(run_one, jobs, chunksize=1)):
            results.append(r)
            if (i + 1) % 20 == 0 or i + 1 == len(jobs):
                el = time.time() - t0
                print(f"  {i+1}/{len(jobs)} missions  {el/60:.1f} min  eta {el/(i+1)*(len(jobs)-i-1)/60:.1f} min", flush=True)
    meta = dict(seeds=seeds, base=BASE, fail=FAIL, max_sim_seconds=MAX_SIM_SECONDS,
                experiments=[dict(group=e["group"], scenario=e["scenario"], name=e["name"]) for e in exps])
    json.dump(dict(meta=meta, runs=results), open(args.out, "w"))
    print(f"[ablation] wrote {args.out} ({len(results)} runs, {(time.time()-t0)/60:.1f} min)")


if __name__ == "__main__":
    main()
