#!/usr/bin/env python3
"""Builds results/final_report.html (self-contained) from results/ablation/{runs,perception}.json."""
import os, io, json, base64, collections, html
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AB = os.path.join(ROOT, "results", "ablation")
OUTHTML = os.path.join(ROOT, "results", "final_report.html")

# validated reference palette, categorical slots 1-3 (light mode)
C1, C2, C3, C4 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e6e5e1", "#fcfcfb"

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.facecolor": SURF, "figure.facecolor": SURF,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
                     "grid.linewidth": 0.6, "axes.axisbelow": True, "axes.titlesize": 10, "axes.titleweight": "bold",
                     "axes.titlecolor": INK})

runs_doc = json.load(open(os.path.join(AB, "runs.json")))
RUNS = runs_doc["runs"]; META = runs_doc["meta"]; SEEDS = META["seeds"]
perc = json.load(open(os.path.join(AB, "perception.json"))) if os.path.exists(os.path.join(AB, "perception.json")) else None

IDX = collections.defaultdict(dict)       # (group,scenario,name) -> seed -> run
for r in RUNS:
    IDX[(r["group"], r["scenario"], r["name"])][r["seed"]] = r

def vals(key, metric):
    return {s: r["metrics"][metric] for s, r in IDX[key].items() if r["metrics"].get(metric) is not None}

def ms(key, metric, d=2):
    v = list(vals(key, metric).values())
    if not v: return "n/a"
    return f"{np.mean(v):.{d}f} ± {np.std(v, ddof=1) if len(v) > 1 else 0:.{d}f}"

def mean(key, metric):
    v = list(vals(key, metric).values()); return float(np.mean(v)) if v else float("nan")

def sd(key, metric):
    v = list(vals(key, metric).values()); return float(np.std(v, ddof=1)) if len(v) > 1 else 0.0

def paired(keyA, keyB, metric):
    """mean(B - A) over shared seeds and 95% CI half-width (normal approx / t for small n)."""
    a, b = vals(keyA, metric), vals(keyB, metric)
    sh = sorted(set(a) & set(b))
    if len(sh) < 2: return None
    d = np.array([b[s] - a[s] for s in sh], float)
    tcrit = {5: 2.78, 8: 2.36, 10: 2.26, 15: 2.14, 19: 2.09, 20: 2.09, 30: 2.05}
    t = tcrit.get(len(sh) - 1, 2.09 if len(sh) > 19 else 2.26)
    return d.mean(), t * d.std(ddof=1) / np.sqrt(len(d)), len(sh)

FIGDIR = os.path.join(ROOT, "results", "figures")
os.makedirs(FIGDIR, exist_ok=True)

def fig_html(fig, alt):
    slug = "".join(c if c.isalnum() else "_" for c in alt.lower()).strip("_")
    fig.savefig(os.path.join(FIGDIR, slug + ".png"), format="png", dpi=150, bbox_inches="tight")   # for the GitHub README
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=150, bbox_inches="tight"); plt.close(fig)
    return f'<img alt="{html.escape(alt)}" src="data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}">'

def bar_labels(ax, bars, fmt="{:.1f}"):
    for b in bars:
        h = b.get_height()
        ax.annotate(fmt.format(h), (b.get_x() + b.get_width() / 2, h), ha="center", va="bottom", fontsize=7.5,
                    color=INK, xytext=(0, 2), textcoords="offset points")

def table(header, rows, cls=""):
    h = "".join(f"<th>{html.escape(str(c))}</th>" for c in header)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tw"><table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'

N = len(SEEDS)
sections = []

# =============================================================== 1. perception
perc_html = ""
if perc:
    R = {(r["condition"], r["mode"]): r for r in perc["results"]}
    conds = [("day", "Day (clean)"), ("night", "Night (RGB dark + noisy)"), ("thermal_washout", "Thermal washout (low contrast)")]
    modes = [("fusion", "RGB + Thermal (fused)", C1), ("rgb_only", "RGB only (thermal masked)", C2), ("thermal_only", "Thermal only (RGB masked)", C3)]
    fig, ax = plt.subplots(figsize=(7.4, 3.3))
    w = 0.26
    for i, (m, lab, col) in enumerate(modes):
        xs = np.arange(len(conds)) + (i - 1) * w
        bars = ax.bar(xs, [R[(c, m)]["AP50"] for c, _ in conds], w * 0.9, color=col, label=lab)
        bar_labels(ax, bars)
    ax.set_xticks(range(len(conds))); ax.set_xticklabels([c[1] for c in conds]); ax.set_ylabel("AP@0.5 (%)")
    ax.set_ylim(0, 112); ax.grid(axis="x", visible=False); ax.legend(frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.16))
    img = fig_html(fig, "Detection AP50 by modality and condition")
    rows = []
    for c, cl in conds:
        for m, ml, _ in modes:
            r = R[(c, m)]
            rows.append([cl, ml, f"{r['AP50']:.1f}", f"{r['AP75']:.1f}", f"{r['precision']:.3f}", f"{r['recall']:.3f}", f"{r['f1']:.3f}"])
    perc_html = f"""
<h2>1 &nbsp; Perception: does the thermal channel matter?</h2>
<p class="lead">Held-out NII-CU val frames ({perc['meta']['n_frames']} frames, fixed random subset), IoU&nbsp;0.5 matching, operating point conf&nbsp;&ge;&nbsp;{perc['meta']['op_conf']}.
The same 4-channel YOLO11 network is run with a modality <b>masked</b> (set to zero) and under degraded scene conditions.</p>
{img}
{table(["Condition", "Input", "AP50", "AP75", "Precision", "Recall", "F1"], rows)}
<p class="note"><b>Read with care.</b> This is <i>modality-masked inference of one fused network</i>, not three separately trained networks. It shows how the fused model behaves when a sensor is lost or degraded; it is not a substitute for training RGB-only / thermal-only baselines (notebook <code>nii_cu_ablation_2gpu.ipynb</code> is set up for that and has not been run). Train and val come from the same site, so absolute numbers are optimistic.</p>"""
sections.append(perc_html)

# =============================================================== 2. control
CV = ["Full system", "- EW weighting (alpha=0)", "- Hysteresis", "- Failover", "Static baseline"]
def ck(sc, n): return ("control", sc, n)

# failover coverage over time
def curve(key, field="coverage", step=5, tmax=700):
    grid = np.arange(0, tmax + 1, step); mat = []
    for s, r in IDX[key].items():
        ts = r["timeseries"]; t = np.array([x["t"] for x in ts]); y = np.array([x[field] for x in ts], float)
        mat.append(np.interp(grid, t, y, right=y[-1]))
    return grid, np.array(mat)

fig, axs = plt.subplots(1, 2, figsize=(7.6, 3.1), sharey=True)
for ax, sc, ttl in zip(axs, ["nominal", "uav_loss"], ["Nominal mission", "UAV 2 lost at t = 80 s"]):
    for n, col, lab in [("Full system", C1, "Full system"), ("- Failover", C2, "No failover"), ("Static baseline", C3, "Static baseline")]:
        if (("control", sc, n)) not in IDX: continue
        g, m = curve(("control", sc, n)); ax.plot(g, m.mean(0), color=col, lw=2, label=lab)
    ax.set_title(ttl); ax.set_xlabel("mission time (s)")
    if sc == "uav_loss": ax.axvline(80, color=INK2, lw=0.8, ls=":")
axs[0].set_ylabel("area coverage (%)"); axs[0].set_ylim(0, 104); axs[1].legend(frameon=False, loc="lower right")
cov_img = fig_html(fig, "Coverage over time")

rows = []
for sc, scl in [("nominal", "Nominal"), ("uav_loss", "UAV loss")]:
    for n in CV:
        if ck(sc, n) not in IDX: continue
        k = ck(sc, n)
        rows.append([scl, n, ms(k, "coverage_pct", 1), ms(k, "recall_arena", 3), ms(k, "makespan_s", 0), ms(k, "batt_min_pct", 1),
                     ms(k, "sector_flips", 1), ms(k, "route_changes", 1), ms(k, "total_distance_km", 1), ms(k, "rtl_aborts", 2)])
ctl_tbl = table(["Scenario", "Variant", "Coverage %", "Recall (whole arena)", "Mission time s", "Min final battery %",
                 "Sector flips", "Route changes", "Distance km", "Low-battery aborts"], rows)

# noise chart
sig = [0.0, 1.0, 2.0, 4.0]
fig, axs = plt.subplots(1, 2, figsize=(7.6, 3.0))
for metric, ax, ttl in [("sector_flips", axs[0], "Sector ownership flips"), ("makespan_s", axs[1], "Mission time (s)")]:
    for n, col in [("Hysteresis ON", C1), ("Hysteresis OFF", C2)]:
        m = [mean(("noise", f"sigma_{s:g}", n), metric) for s in sig]; e = [sd(("noise", f"sigma_{s:g}", n), metric) / np.sqrt(N) * 2 for s in sig]
        ax.errorbar(sig, m, yerr=e, color=col, lw=2, marker="o", ms=5, capsize=3, label=n)
    ax.set_title(ttl); ax.set_xlabel("battery-sensor noise σ (% points)"); ax.set_xticks(sig)
axs[0].legend(frameon=False)
noise_img = fig_html(fig, "Hysteresis vs sensor noise")
noise_rows = [[f"{s:g}", ms(("noise", f"sigma_{s:g}", "Hysteresis ON"), "sector_flips", 1), ms(("noise", f"sigma_{s:g}", "Hysteresis OFF"), "sector_flips", 1),
               ms(("noise", f"sigma_{s:g}", "Hysteresis ON"), "partition_commits", 0), ms(("noise", f"sigma_{s:g}", "Hysteresis OFF"), "partition_commits", 0),
               ms(("noise", f"sigma_{s:g}", "Hysteresis ON"), "makespan_s", 0), ms(("noise", f"sigma_{s:g}", "Hysteresis OFF"), "makespan_s", 0)] for s in sig]
noise_tbl = table(["σ (%)", "Flips ON", "Flips OFF", "Commits ON", "Commits OFF", "Time ON (s)", "Time OFF (s)"], noise_rows)

# alpha sweep
al = [0.0, 0.5, 1.0, 2.0, 3.0]
fig, axs = plt.subplots(1, 3, figsize=(8.2, 2.8))
for metric, ax, ttl in [("batt_min_pct", axs[0], "Min final battery (%)"), ("makespan_s", axs[1], "Mission time (s)"), ("coverage_pct", axs[2], "Coverage (%)")]:
    m = [mean(("alpha", f"alpha_{a:g}", f"alpha={a:g}"), metric) for a in al]
    e = [sd(("alpha", f"alpha_{a:g}", f"alpha={a:g}"), metric) / np.sqrt(N) * 2 for a in al]
    ax.errorbar(al, m, yerr=e, color=C1, lw=2, marker="o", ms=5, capsize=3); ax.set_title(ttl); ax.set_xlabel("EW-CVT exponent α"); ax.set_xticks(al)
alpha_img = fig_html(fig, "alpha sweep")

ctl_html = f"""
<h2>2 &nbsp; Swarm control: EW-CVT partitioning, hysteresis, failover</h2>
<p class="lead">Paired seeds per variant (a seed fixes the world and each UAV's launch battery, so variants are paired). Scenario: 6 UAVs, 5&nbsp;km&nbsp;&times;&nbsp;5&nbsp;km, 25 sectors, launch batteries U(20,100)&nbsp;%, battery-sensor noise σ&nbsp;=&nbsp;1.5&nbsp;%. “UAV loss” injects a motor failure on UAV&nbsp;2 at t&nbsp;=&nbsp;80&nbsp;s.</p>
<h3>Resilience: coverage over time</h3>{cov_img}
<h3>Ablation table (mean ± std over seeds)</h3>{ctl_tbl}
<p class="note"><b>Sector flips</b> = unscanned sectors that change owner between re-plans (excluding failover); <b>route changes</b> = times a UAV had to re-plan its route. High values mean the swarm is “chattering”. <b>Recall (whole arena)</b> counts victims over the entire arena, so sectors that were never searched count against the system.</p>
<h3>Hysteresis suppresses chattering under sensor noise</h3>{noise_img}{noise_tbl}
<h3>EW-CVT exponent α: time versus energy reserve</h3>{alpha_img}"""
sections.append(ctl_html)

# =============================================================== 3. network
arenas = [1500, 3000, 5000]
NV = ["Full (DTN + forwarding)", "- Forwarding", "- DTN buffer"]
fig, axs = plt.subplots(1, 2, figsize=(7.8, 3.1))
w = 0.25
for i, (n, col) in enumerate(zip(NV, [C1, C2, C3])):
    xs = np.arange(3) + (i - 1) * w
    b = axs[0].bar(xs, [mean(("network", f"arena_{a}", n), "operator_recall") * 100 for a in arenas], w * 0.9, color=col, label=n)
    bar_labels(axs[0], b, "{:.0f}")
    b = axs[1].bar(xs, [mean(("network", f"arena_{a}", n), "consensus_final") * 100 for a in arenas], w * 0.9, color=col)
    bar_labels(axs[1], b, "{:.0f}")
for ax, t in zip(axs, ["Victims known to the operator (%)", "Swarm-wide consensus at end (%)"]):
    ax.set_xticks(range(3)); ax.set_xticklabels([f"{a/1000:g} km arena" for a in arenas]); ax.set_title(t); ax.set_ylim(0, 118); ax.grid(axis="x", visible=False)
axs[0].legend(frameon=False, fontsize=7.5, loc="upper center", bbox_to_anchor=(1.1, -0.12), ncol=3)
net_img = fig_html(fig, "Network ablation")
rows = []
for a in arenas:
    for n in NV:
        k = ("network", f"arena_{a}", n)
        rows.append([f"{a/1000:g} km", n, ms(k, "operator_recall", 3), ms(k, "operator_known_frac", 3), ms(k, "alert_latency_mean_s", 0),
                     ms(k, "consensus_final", 3), ms(k, "gcs_pdr_first_attempt", 3), ms(k, "msgs_lost_forever", 0), ms(k, "msgs_delivered_late", 0)])
net_tbl = table(["Arena", "Variant", "Operator recall", "Reports known to GCS", "Alert latency s", "Consensus", "First-attempt PDR to GCS",
                 "Messages lost", "Delivered late (DTN)"], rows)
net_html = f"""
<h2>3 &nbsp; Networking: delay-tolerant mesh and store-carry-forward relaying</h2>
<p class="lead">Every victim alert is sent to all peers <i>and</i> to a Ground Control Station at the base. <b>Operator recall</b> is the fraction of all victims in the arena that the operator actually learned about, so it is the end-to-end quantity the network exists to protect. 6 UAVs, equal batteries, no failures, {len(SEEDS)} seeds.</p>
{net_img}{net_tbl}
<p class="note">At these ranges the swarm is mostly <b>disconnected</b> in flight (direct link range is a few hundred metres under the RF model), so first-attempt delivery is low everywhere. Store-and-forward is what turns a mostly-offline swarm into a working one: alerts wait in the QoS-1 buffer and flush when the UAV returns to base. <b>Forwarding</b> adds to this: any UAV that receives an alert keeps it and hands it over whenever it later meets a recipient, so no UAV has to be in the right place at the right time.</p>"""
loss_rows = []
for a in arenas:
    for n in NV[:2]:
        k = ("network", f"loss_arena_{a}", n)
        loss_rows.append([f"{a/1000:g} km", n, ms(k, "operator_known_frac", 3), ms(k, "alert_latency_mean_s", 0), ms(k, "consensus_final", 3), ms(k, "alerts_forwarded", 0)])
net_html += "<h3>A UAV is lost at t = 60 s</h3>" + table(["Arena", "Variant", "Reports known to GCS", "Alert latency s", "Consensus", "Copies forwarded"], loss_rows)
cap_rows = [[n, ms(("network", f"cap_{c}", n), "operator_known_frac", 3), ms(("network", f"cap_{c}", n), "alert_latency_mean_s", 0),
             ms(("network", f"cap_{c}", n), "buffer_drops", 0)] for c, n in [(5, "buffer cap 5"), (15, "buffer cap 15"), (40, "buffer cap 40"), (120, "buffer cap 120"), ("none", "buffer cap none")]]
net_html += "<h3>Buffer cap per UAV (3 km, UAV lost)</h3>" + table(["Cap", "Reports known to GCS", "Alert latency s", "Copies dropped"], cap_rows)
sections.append(net_html)

# =============================================================== 4. scale
ns = [2, 4, 6, 8, 12]
fig, axs = plt.subplots(1, 3, figsize=(8.2, 2.8))
for metric, ax, ttl in [("makespan_s", axs[0], "Mission time (s)"), ("energy_used_mean_pct", axs[1], "Mean energy used per UAV (%)"), ("recall_arena", axs[2], "Recall (whole arena)")]:
    m = [mean(("scale", f"n_{n}", f"{n} UAVs"), metric) for n in ns]; e = [sd(("scale", f"n_{n}", f"{n} UAVs"), metric) / np.sqrt(N) * 2 for n in ns]
    ax.errorbar(ns, m, yerr=e, color=C1, lw=2, marker="o", ms=5, capsize=3); ax.set_title(ttl); ax.set_xlabel("swarm size"); ax.set_xticks(ns)
scale_img = fig_html(fig, "Scaling")
sections.append(f"<h2>4 &nbsp; Scaling with swarm size</h2><p class=\"lead\">Equal batteries, no failures, 5 km arena.</p>{scale_img}")


# =============================================================== 6. baselines
DN = ["Epidemic (ours)", "Spray-and-Wait (L=3)", "Buffer only"]
drows = [[lab, n, ms(("dtn_base", sc, n), "alert_latency_mean_s", 1), ms(("dtn_base", sc, n), "operator_recall", 3), ms(("dtn_base", sc, n), "carriers_per_alert", 2)]
         for sc, lab in [("arena_1500", "1.5 km"), ("arena_3000", "3 km"), ("arena_5000", "5 km"), ("loss_arena_3000", "3 km, UAV lost")] for n in DN]
AN = ["EW-CVT (ours)", "Auction, no failover", "Static partition"]
arows = [[lab, n, ms(("alloc_base", sc, n), "coverage_pct", 1), ms(("alloc_base", sc, n), "makespan_s", 0), ms(("alloc_base", sc, n), "batt_min_pct", 1), ms(("alloc_base", sc, n), "duplicate_scans", 2)]
         for sc, lab in [("nominal", "Nominal"), ("uav_loss", "UAV 2 lost")] for n in AN]
sections.append("<h2>6 &nbsp; Baselines from the literature</h2><p class=\"lead\">Each baseline replaces one policy in the same simulator, with the same radio model, worlds and seeds.</p>"
    "<h3>Alert forwarding</h3>" + table(["Scenario", "Forwarding", "Alert latency s", "Operator recall", "Copies per alert"], drows) +
    "<p class=\"note\">Epidemic (ours) copies an alert to every UAV met. Spray-and-Wait gives each alert L&nbsp;=&nbsp;3 copies. Buffer only carries each alert home with its finder. Epidemic has the lowest latency everywhere and costs the most copies.</p>"
    "<h3>Task allocation</h3>" + table(["Scenario", "Allocation", "Coverage %", "Mission time s", "Min final battery %", "Duplicate scans"], arows) +
    "<p class=\"note\">The auction assigns each sector to the nearest UAV (all weights equal to 1) and has no failover. After a loss, EW-CVT with failover keeps far more coverage, at the cost of a longer mission. The coverage gain comes from the lease-based failover.</p>")

# =============================================================== headline
def hl(label, kA, kB, metric, unit="", d=1, scale=1.0, better="lower"):
    p = paired(kA, kB, metric)
    if not p: return None
    return [label, f"{mean(kA, metric)*scale:.{d}f}{unit}", f"{mean(kB, metric)*scale:.{d}f}{unit}", f"{p[0]*scale:+.{d}f} ± {p[1]*scale:.{d}f}{unit}"]

H = []
full_loss, nofail = ck("uav_loss", "Full system"), ck("uav_loss", "- Failover")
H.append(["<b>Swarm control</b>", "", "", ""])
for row in [hl("Remove <b>failover</b> (UAV lost): area coverage", full_loss, nofail, "coverage_pct", " %", 1),
            hl("&nbsp;&nbsp;&nbsp;&nbsp;victims found, whole arena (recall)", full_loss, nofail, "recall_arena", "", 3),
            hl("Remove <b>hysteresis</b> (per-tick re-planning test, noise 2 %): sector flips per mission", ("noise", "sigma_2", "Hysteresis ON"), ("noise", "sigma_2", "Hysteresis OFF"), "sector_flips", "", 1),
            hl("&nbsp;&nbsp;&nbsp;&nbsp;route changes per mission", ("noise", "sigma_2", "Hysteresis ON"), ("noise", "sigma_2", "Hysteresis OFF"), "route_changes", "", 1),
            hl("&nbsp;&nbsp;&nbsp;&nbsp;mission time", ("noise", "sigma_2", "Hysteresis ON"), ("noise", "sigma_2", "Hysteresis OFF"), "makespan_s", " s", 0),
            hl("Remove <b>EW weighting</b> (α=0): min final battery", ck("nominal", "Full system"), ck("nominal", "- EW weighting (alpha=0)"), "batt_min_pct", " %", 1),
            hl("Static baseline vs full: mission time (cost of re-planning)", ck("nominal", "Static baseline"), ck("nominal", "Full system"), "makespan_s", " s", 0)]:
    if row: H.append(row)
dk3 = lambda n: ("dtn_base", "arena_3000", n)
for row in [hl("<b>Epidemic vs spray-and-wait</b> (3 km): mean alert latency", dk3(DN[0]), dk3(DN[1]), "alert_latency_mean_s", " s", 0),
            hl("&nbsp;&nbsp;&nbsp;&nbsp;copies per alert", dk3(DN[0]), dk3(DN[1]), "carriers_per_alert", "", 2)]:
            
    if row: H.append(row)
H.append(["<b>Networking</b> (5 km arena)", "", "", ""])
fk, dk, mk = ("network", "arena_5000", NV[0]), ("network", "arena_5000", NV[2]), ("network", "arena_5000", NV[1])
fl, ml = ("network", "loss_arena_5000", NV[0]), ("network", "loss_arena_5000", NV[1])
for row in [hl("Remove <b>DTN buffer</b>: victims known to operator", fk, dk, "operator_recall", " %", 1, 100),
            hl("&nbsp;&nbsp;&nbsp;&nbsp;swarm consensus", fk, dk, "consensus_final", " %", 1, 100),
            hl("Remove <b>forwarding</b>: victims known to operator", fk, mk, "operator_recall", " %", 1, 100),
            hl("&nbsp;&nbsp;&nbsp;&nbsp;mean alert latency", fk, mk, "alert_latency_mean_s", " s", 0),
            hl("Remove <b>forwarding</b>, UAV lost: reports known to GCS", fl, ml, "operator_known_frac", " %", 1, 100)]:
    if row: H.append(row)
if perc:
    H.append(["<b>Perception</b> (AP50, %)", "", "", ""])
    for c, cl in [("day", "day"), ("night", "night")]:
        H.append([f"Fused vs RGB-only ({cl})", f"{R[(c,'fusion')]['AP50']:.1f}", f"{R[(c,'rgb_only')]['AP50']:.1f}", f"{R[(c,'rgb_only')]['AP50']-R[(c,'fusion')]['AP50']:+.1f}"])
    H.append(["Fused vs thermal-only (night)", f"{R[('night','fusion')]['AP50']:.1f}", f"{R[('night','thermal_only')]['AP50']:.1f}", f"{R[('night','thermal_only')]['AP50']-R[('night','fusion')]['AP50']:+.1f}"])
head_tbl = table(["Component removed &rarr; effect", "Full system", "Ablated", "Change (paired mean ± 95% CI)"], H, "hl")

# =============================================================== page
css = """
:root{--bg:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--line:#e6e5e1;--accent:#2a78d6;--soft:#f3f2ee}
@media (prefers-color-scheme:dark){:root{--bg:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--line:#33322f;--accent:#3987e5;--soft:#232321}
img{background:#fcfcfb;border-radius:6px}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1000px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:28px;margin:0 0 4px}h2{font-size:21px;margin:44px 0 6px;padding-top:14px;border-top:1px solid var(--line)}h3{font-size:15px;margin:26px 0 6px}
.sub{color:var(--ink2);margin:0 0 22px}.lead{color:var(--ink2);margin:4px 0 14px}
img{max-width:100%;height:auto;display:block;margin:10px 0}
.tw{overflow-x:auto;margin:10px 0}table{border-collapse:collapse;width:100%;font-size:12.5px;font-variant-numeric:tabular-nums}
th,td{padding:5px 9px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}th{background:var(--soft);font-weight:600}
td:first-child,th:first-child,td:nth-child(2),th:nth-child(2){text-align:left}
.hl td:first-child,.hl th:first-child{text-align:left;white-space:normal}
.note{background:var(--soft);border-left:3px solid var(--accent);padding:9px 12px;font-size:13px;color:var(--ink2);margin:12px 0}
code{font-size:12px}ul{margin:6px 0 6px 20px;padding:0}li{margin:3px 0}
"""
valid = """
<h2>7 &nbsp; What these results do and do not show</h2>
<ul>
<li><b>Simulation, not flight.</b> Dynamics are kinematic (constant speed, linear battery drain). The EW-CVT, hysteresis, failover and DTN logic are real code under test; the aircraft and the radio are models.</li>
<li><b>Perception inside the mission replays static frames.</b> Each sector shows one dataset image, so detection results are per-frame and deterministic; mission-level precision/recall mainly reflect the detector on those frames plus sector coverage.</li>
<li><b>Network assumptions.</b> Log-distance path loss (exponent 2.5, σ&nbsp;=&nbsp;4&nbsp;dB shadowing), 33&nbsp;dBm at 2.4&nbsp;GHz for arenas &ge; 2&nbsp;km. Results depend on this model; real links would differ.</li>
<li><b>Energy rule.</b> A UAV at &le;&nbsp;15&nbsp;% battery aborts and returns to base; at 0&nbsp;% it is lost. The battery-sensor noise levels (0&ndash;4&nbsp;% points) are scenario assumptions and are swept above.</li>
<li><b>Dynamic re-planning is not free.</b> In the nominal case the static baseline finishes faster; re-planning buys resilience (failover) and energy balance at a time cost, shown in the headline table.</li>
<li><b>Statistics.</b> Paired seeds per variant; ± values are standard deviations in tables and paired 95 % confidence intervals in the headline table. Seeds vary the world layout and launch batteries only.</li>
</ul>"""

page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FlyNetSim Ablation Results</title><style>{css}</style></head><body><main>
<h1>Autonomous Multispectral UAV Swarm for SAR: ablation results</h1>
<p class="sub">Three contributions, each switched off in turn: 4-channel RGB+thermal perception · delay-tolerant FANET mesh · EW-CVT swarm control with hysteresis and failover. {len(RUNS)} simulated missions.</p>
<h2 style="border:0;margin-top:8px">Headline: what each component buys</h2>{head_tbl}
{''.join(sections)}{valid}
</main></body></html>"""
open(OUTHTML, "w").write(page)
print("wrote", OUTHTML, f"({len(page)/1e6:.2f} MB)")
