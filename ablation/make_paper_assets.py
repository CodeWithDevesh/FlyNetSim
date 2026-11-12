#!/usr/bin/env python3
"""Figures and LaTeX tables for the paper, computed from results/ablation/{runs,perception}.json.

Writes  results/figures/{detection_fused_vs_thermal,forwarding_tradeoff,allocation_baselines,lease_slack_tradeoff}.png
and     paper/generated/{tab_detection,tab_forwarding,tab_allocation,tab_recovery}.tex
Error bars and +- values are 95 % confidence intervals of the mean over seeds.
"""
import os, json, collections
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AB = os.path.join(ROOT, "results", "ablation")
FIG = os.path.join(ROOT, "results", "figures")
GEN = os.path.join(ROOT, "paper", "generated")
os.makedirs(FIG, exist_ok=True); os.makedirs(GEN, exist_ok=True)

C1, C2, C3, C4, GREY = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#8a8985"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e6e5e1", "#fcfcfb"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.facecolor": SURF, "figure.facecolor": SURF,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
                     "grid.linewidth": 0.6, "axes.axisbelow": True, "axes.titlesize": 8.5, "axes.titleweight": "bold",
                     "axes.titlecolor": INK, "legend.frameon": False})

doc = json.load(open(os.path.join(AB, "runs.json")))
IDX = collections.defaultdict(dict)
for r in doc["runs"]:
    IDX[(r["group"], r["scenario"], r["name"])][r["seed"]] = r["metrics"]
perc = json.load(open(os.path.join(AB, "perception.json")))
P = {(r["condition"], r["mode"]): r for r in perc["results"]}


def vals(k, m):
    return np.array([x[m] for x in IDX[k].values() if x.get(m) is not None], float)


def mean(k, m):
    return float(vals(k, m).mean())


def ci(k, m):
    v = vals(k, m)
    return float(2.09 * v.std(ddof=1) / np.sqrt(len(v))) if len(v) > 1 else 0.0


def save(fig, name):
    fig.savefig(os.path.join(FIG, name + ".png"), dpi=220, bbox_inches="tight")
    plt.close(fig)


# ------------------------------------------------------------------ detection
def detection():
    conds = [("day", "Day"), ("night", "Night"), ("thermal_washout", "Washout")]
    modes = [("fusion", "Fused (RGB + thermal)", C1), ("thermal_only", "Thermal only", C3)]
    fig, ax = plt.subplots(figsize=(3.4, 2.1))
    w = 0.36
    for i, (m, lab, col) in enumerate(modes):
        v = [P[(c, m)]["AP50"] for c, _ in conds]
        bars = ax.bar(np.arange(3) + (i - 0.5) * w, v, w * 0.92, color=col, label=lab)
        for b, y in zip(bars, v):
            ax.annotate(f"{y:.1f}", (b.get_x() + b.get_width() / 2, y), ha="center", va="bottom", fontsize=7, xytext=(0, 1.5),
                        textcoords="offset points", color=INK)
    ax.set_xticks(range(3)); ax.set_xticklabels([l for _, l in conds]); ax.set_ylabel("AP50 (%)"); ax.set_ylim(0, 118)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), fontsize=7, ncol=2, handlelength=1.1, columnspacing=1.2)
    ax.grid(axis="x", visible=False)
    save(fig, "detection_fused_vs_thermal")

    def row(m, lab):
        cells, best = [], {}
        for c, _ in conds:
            for key in ("AP50", "AP75", "precision", "recall"):
                best.setdefault((c, key), max(P[(c, mm)][key] for mm in ("fusion", "thermal_only")))
        for c, _ in conds:
            r = P[(c, m)]
            for key, f in (("AP50", "{:.1f}"), ("AP75", "{:.1f}"), ("precision", "{:.3f}"), ("recall", "{:.3f}")):
                s = f.format(r[key])
                cells.append(r"\textbf{%s}" % s if r[key] >= best[(c, key)] - 1e-9 else s)
        return lab + " & " + " & ".join(cells) + r" \\"
    tex = "\n".join([
        r"\begin{tabular}{lrrrrrrrrrrrr}", r"\toprule",
        r"& \multicolumn{4}{c}{Day} & \multicolumn{4}{c}{Night} & \multicolumn{4}{c}{Thermal washout}\\",
        r"\cmidrule(lr){2-5}\cmidrule(lr){6-9}\cmidrule(lr){10-13}",
        r"Input & AP50 & AP75 & Prec. & Rec. & AP50 & AP75 & Prec. & Rec. & AP50 & AP75 & Prec. & Rec.\\", r"\midrule",
        row("fusion", "Fused RGB + thermal (proposed)"), row("thermal_only", "Thermal only (RGB zeroed)"),
        r"\bottomrule", r"\end{tabular}"])
    open(os.path.join(GEN, "tab_detection.tex"), "w").write(tex + "\n")


# ------------------------------------------------------------------ forwarding
POL = [("Epidemic (ours)", "Epidemic (proposed)", C1), ("Spray-and-Wait (L=3)", "Spray-and-wait", C2), ("Buffer only", "Buffer only", GREY)]
SCEN = [("arena_1500", "1.5 km"), ("arena_3000", "3 km"), ("arena_5000", "5 km"), ("loss_arena_3000", "3 km, UAV lost")]


def forwarding():
    fig, axs = plt.subplots(1, 3, figsize=(7.2, 2.3))
    for ax, (sc, lab) in zip(axs, [SCEN[1], SCEN[2], SCEN[3]]):
        for key, short, col in POL:
            k = ("dtn_base", sc, key)
            x, y = mean(k, "carriers_per_alert"), mean(k, "alert_latency_mean_s")
            ax.errorbar(x, y, xerr=ci(k, "carriers_per_alert"), yerr=ci(k, "alert_latency_mean_s"), fmt="o", color=col, ms=5.5,
                        capsize=2, lw=1.1, mec=SURF, mew=0.8, label=short)
        ax.set_title(lab); ax.set_xlabel("copies per alert (traffic cost)")
        ax.margins(x=0.18, y=0.12)
    axs[0].set_ylabel("mean alert latency (s)")
    h, l = axs[0].get_legend_handles_labels()
    fig.legend([x[0] if isinstance(x, tuple) else x for x in h], l, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.12), fontsize=7.5,
               handlelength=1.0, columnspacing=1.6)
    fig.text(0.99, 0.97, "lower left is better", ha="right", fontsize=7, color=INK2)
    fig.tight_layout(w_pad=1.2)
    save(fig, "forwarding_tradeoff")

    rows = []
    for key, short, col in POL:
        cells = []
        for sc, _ in SCEN:
            k = ("dtn_base", sc, key)
            best = min(mean(("dtn_base", sc, kk), "alert_latency_mean_s") for kk, _, _ in POL)
            m = mean(k, "alert_latency_mean_s")
            lat = r"%.1f{\scriptsize$\pm$%.1f}" % (m, ci(k, "alert_latency_mean_s"))
            if m <= best + 1e-9:
                lat = r"\textbf{%s}" % lat
            cells += [lat, "%.2f" % mean(k, "carriers_per_alert")]
        rows.append(short + " & " + " & ".join(cells) + r" \\")
    tex = "\n".join([
        r"\begin{tabular}{lrrrrrrrr}", r"\toprule",
        r"& \multicolumn{2}{c}{1.5\,km} & \multicolumn{2}{c}{3\,km} & \multicolumn{2}{c}{5\,km} & \multicolumn{2}{c}{3\,km, UAV lost}\\",
        r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(lr){6-7}\cmidrule(lr){8-9}",
        r"Policy & Lat.\,(s) & Copies & Lat.\,(s) & Copies & Lat.\,(s) & Copies & Lat.\,(s) & Copies\\", r"\midrule",
        *rows, r"\bottomrule", r"\end{tabular}"])
    open(os.path.join(GEN, "tab_forwarding.tex"), "w").write(tex + "\n")


# ------------------------------------------------------------------ allocation
ALLOC = [("EW-CVT (ours)", "EW-CVT (proposed)", C1), ("Auction, no failover", "Auction, no failover", C3), ("Static partition", "Static partition", C4)]
METR = [("coverage_pct", "Coverage (%)", "{:.1f}", max), ("makespan_s", "Mission time (s)", "{:.0f}", min),
        ("batt_min_pct", "Min. final battery (%)", "{:.1f}", max), ("duplicate_scans", "Duplicate scans", "{:.2f}", min)]


def allocation():
    fig, axs = plt.subplots(1, 4, figsize=(7.2, 2.2))
    w = 0.26
    for ax, (m, lab, _, _) in zip(axs, METR):
        for i, (key, short, col) in enumerate(ALLOC):
            v = [mean(("alloc_base", sc, key), m) for sc in ("nominal", "uav_loss")]
            e = [ci(("alloc_base", sc, key), m) for sc in ("nominal", "uav_loss")]
            lo = [min(a, b) for a, b in zip(e, v)]
            ax.bar(np.arange(2) + (i - 1) * w, v, w * 0.9, yerr=[lo, e], color=col, label=short, error_kw=dict(lw=0.9, capsize=1.5, ecolor=INK2))
        ax.set_xticks([0, 1]); ax.set_xticklabels(["Nominal", "UAV lost"]); ax.set_title(lab)
        ax.grid(axis="x", visible=False)
        if m == "coverage_pct":
            ax.set_ylim(0, 108)
    h, l = axs[0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.09), fontsize=7.5, handlelength=1.1, columnspacing=1.6)
    fig.tight_layout(w_pad=1.0)
    save(fig, "allocation_baselines")

    rows = []
    for key, short, col in ALLOC:
        cells = []
        for sc in ("nominal", "uav_loss"):
            for m, _, f, better in METR:
                best = better(mean(("alloc_base", sc, kk), m) for kk, _, _ in ALLOC)
                x = mean(("alloc_base", sc, key), m)
                s = f.format(x)
                cells.append(r"\textbf{%s}" % s if abs(x - best) < 1e-9 or f.format(x) == f.format(best) else s)
        rows.append(short + " & " + " & ".join(cells) + r" \\")
    tex = "\n".join([
        r"\begin{tabular}{lrrrrrrrr}", r"\toprule",
        r"& \multicolumn{4}{c}{Nominal} & \multicolumn{4}{c}{UAV~2 lost}\\", r"\cmidrule(lr){2-5}\cmidrule(lr){6-9}",
        r"Policy & Cover.\,\% & Time (s) & Min.\,batt.\,\% & Dup. & Cover.\,\% & Time (s) & Min.\,batt.\,\% & Dup.\\", r"\midrule",
        *rows, r"\bottomrule", r"\end{tabular}"])
    open(os.path.join(GEN, "tab_allocation.tex"), "w").write(tex + "\n")


# ------------------------------------------------------------------ failure recovery + lease slack
def recovery():
    sl = [20, 60, 120, 240]
    fig, axs = plt.subplots(1, 2, figsize=(3.4, 2.0))
    ks = [("planner", f"slack_{s}", f"slack={s}") for s in sl]
    for ax, m, t in ((axs[0], "failover_latency_s", "Failover latency (s)"), (axs[1], "false_suspicions", "Wrong suspicions")):
        ax.errorbar(sl, [mean(k, m) for k in ks], yerr=[ci(k, m) for k in ks], color=C1, marker="o", ms=4, lw=1.6, capsize=2)
        ax.set_title(t); ax.set_xlabel("lease slack (s)"); ax.set_xticks(sl); ax.tick_params(axis="x", labelsize=7)
    fig.tight_layout(w_pad=0.8)
    save(fig, "lease_slack_tradeoff")

    rows = []
    for sc, lab in [("nominal", "5\\,km, no loss"), ("uav_loss", "5\\,km, loss"), ("loss_arena_3000", "3\\,km, loss"), ("loss_arena_1500", "1.5\\,km, loss")]:
        k = ("planner", sc, "decentralized")
        fl = "n/a" if sc == "nominal" else "%.0f" % mean(k, "failover_latency_s")
        rows.append(f"{lab} & {mean(k, 'coverage_pct'):.1f} & {mean(k, 'makespan_s'):.0f} & {fl}" + r" \\")
    tex = "\n".join([r"\begin{tabular}{lrrr}", r"\toprule", r"Scenario & Cover.\,\% & Time (s) & Failover (s)\\", r"\midrule", *rows,
                     r"\bottomrule", r"\end{tabular}"])
    open(os.path.join(GEN, "tab_recovery.tex"), "w").write(tex + "\n")


if __name__ == "__main__":
    detection(); forwarding(); allocation(); recovery()
    print("wrote figures to", FIG, "and tables to", GEN)
