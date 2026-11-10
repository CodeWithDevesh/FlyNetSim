#!/usr/bin/env python3
"""
Perception ablation: does the thermal channel (early fusion) actually help?

Runs the *same* 4-channel model (best.pt) on held-out NII-CU val frames with
  - modality masking:  fusion (RGB+T) | rgb_only (thermal zeroed) | thermal_only (RGB zeroed)
  - scene conditions:  day (clean) | night (RGB dark+noisy) | thermal_washout (low-contrast thermal)

NOTE: this is *modality-masked inference* of one fused network, not three separately
trained networks. It measures robustness of the fused model to losing/degrading a
modality. Separately trained variants are covered by training/ablation notebook.

Outputs: results/ablation/perception.json
"""
import os, sys, json, time, glob, random, argparse
import numpy as np
import cv2

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

DEFAULT_VAL = "/home/devesh/Downloads/NII_CU_MAPD_4CH/images/val"


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def load_gt(img_path, W, H):
    lp = img_path.replace("/images/", "/labels/").rsplit(".", 1)[0] + ".txt"
    gt = []
    if os.path.exists(lp):
        for l in open(lp).read().splitlines():
            p = l.split()
            if len(p) >= 5:
                _, cx, cy, w, h = map(float, p[:5])
                gt.append([(cx - w / 2) * W, (cy - h / 2) * H, (cx + w / 2) * W, (cy + h / 2) * H])
    return gt


def apply_condition(img, cond, rng):
    """img: BGRA uint8. Returns degraded copy."""
    out = img.copy()
    if cond == "night":
        rgb = out[..., :3].astype(np.float32) * 0.12 + rng.normal(0, 4.0, out[..., :3].shape)
        out[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    elif cond == "thermal_washout":
        th = out[..., 3].astype(np.float32)
        th = th.mean() + (th - th.mean()) * 0.25 + rng.normal(0, 5.0, th.shape)
        out[..., 3] = np.clip(th, 0, 255).astype(np.uint8)
    return out


def apply_mode(img, mode):
    out = img.copy()
    if mode == "rgb_only":
        out[..., 3] = 0
    elif mode == "thermal_only":
        out[..., :3] = 0
    return out


def ap_from_matches(records, n_gt):
    """records: list of (conf, is_tp). COCO-style 101-point interpolated AP."""
    if n_gt == 0:
        return 0.0
    records = sorted(records, key=lambda r: -r[0])
    tp = np.cumsum([1 if r[1] else 0 for r in records]) if records else np.array([])
    fp = np.cumsum([0 if r[1] else 1 for r in records]) if records else np.array([])
    if len(records) == 0:
        return 0.0
    rec = tp / n_gt
    prec = tp / np.maximum(tp + fp, 1e-9)
    for i in range(len(prec) - 2, -1, -1):
        prec[i] = max(prec[i], prec[i + 1])
    ap = 0.0
    for t in np.linspace(0, 1, 101):
        idx = np.searchsorted(rec, t, side="left")
        ap += prec[idx] if idx < len(prec) else 0.0
    return float(ap / 101.0)


def match_image(dets, gt, thr):
    """Greedy match by confidence. Returns list of (conf, is_tp) and n_matched."""
    used, recs = set(), []
    for d in sorted(dets, key=lambda d: -d["conf"]):
        best, bi = 0.0, -1
        for i, g in enumerate(gt):
            if i in used:
                continue
            v = iou(d["box"], g)
            if v > best:
                best, bi = v, i
        if best >= thr and bi >= 0:
            used.add(bi)
            recs.append((d["conf"], True))
        else:
            recs.append((d["conf"], False))
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--val", default=DEFAULT_VAL)
    ap.add_argument("--model", default=os.path.join(ROOT, "best.pt"))
    ap.add_argument("--n", type=int, default=150, help="number of val frames (fixed-seed subset)")
    ap.add_argument("--op-conf", type=float, default=0.25, help="operating confidence for P/R/F1")
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "ablation", "perception.json"))
    ap.add_argument("--threads", type=int, default=6)
    args = ap.parse_args()

    import torch
    torch.set_num_threads(args.threads)
    from rgbt_detector import RGBTDetector

    det = RGBTDetector(args.model, conf_thresh=0.001, iou_thresh=0.6, device="cpu")
    files = sorted(glob.glob(os.path.join(args.val, "*.png")))
    rnd = random.Random(0)
    files = rnd.sample(files, min(args.n, len(files)))
    print(f"[perception] {len(files)} frames, model={os.path.basename(args.model)}")

    modes = ["fusion", "rgb_only", "thermal_only"]
    conds = ["day", "night", "thermal_washout"]
    rng = np.random.default_rng(0)

    acc = {(m, c): {"rec50": [], "rec75": [], "n_gt": 0, "tp": 0, "fp": 0, "lat": [], "loc_err_px": []}
           for m in modes for c in conds}

    t0 = time.time()
    for k, f in enumerate(files):
        base = cv2.imread(f, cv2.IMREAD_UNCHANGED)
        H, W = base.shape[:2]
        gt = load_gt(f, W, H)
        for c in conds:
            degraded = apply_condition(base, c, rng)
            for m in modes:
                img = apply_mode(degraded, m)
                t1 = time.time()
                dets, _ = det.detect(img, conf=0.001)
                lat = (time.time() - t1) * 1000
                a = acc[(m, c)]
                a["lat"].append(lat)
                a["n_gt"] += len(gt)
                a["rec50"] += match_image(dets, gt, 0.5)
                a["rec75"] += match_image(dets, gt, 0.75)
                # operating point
                op = [d for d in dets if d["conf"] >= args.op_conf]
                r = match_image(op, gt, 0.5)
                tp = sum(1 for _, t in r if t)
                a["tp"] += tp
                a["fp"] += len(r) - tp
        if (k + 1) % 10 == 0:
            el = time.time() - t0
            print(f"  {k+1}/{len(files)} frames  elapsed {el/60:.1f} min  eta {(el/(k+1))*(len(files)-k-1)/60:.1f} min", flush=True)

    results = []
    for m in modes:
        for c in conds:
            a = acc[(m, c)]
            tp, fp, n_gt = a["tp"], a["fp"], a["n_gt"]
            fn = n_gt - tp
            prec = tp / (tp + fp) if tp + fp else 0.0
            rec = tp / n_gt if n_gt else 0.0
            f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
            results.append({
                "mode": m, "condition": c,
                "AP50": round(ap_from_matches(a["rec50"], n_gt) * 100, 2),
                "AP75": round(ap_from_matches(a["rec75"], n_gt) * 100, 2),
                "precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4),
                "tp": tp, "fp": fp, "fn": fn, "n_gt": n_gt,
                "latency_ms_mean": round(float(np.mean(a["lat"])), 1),
            })
    out = {"meta": {"model": os.path.basename(args.model), "n_frames": len(files),
                    "op_conf": args.op_conf, "iou_match": 0.5,
                    "note": "modality-masked inference of one fused network (not separately trained models)"},
           "results": results}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(out, open(args.out, "w"), indent=2)
    print(f"[perception] done in {(time.time()-t0)/60:.1f} min -> {args.out}")
    for r in results:
        print(f"  {r['condition']:16s} {r['mode']:13s} AP50={r['AP50']:6.2f} AP75={r['AP75']:6.2f} P={r['precision']:.3f} R={r['recall']:.3f} F1={r['f1']:.3f}")


if __name__ == "__main__":
    main()
