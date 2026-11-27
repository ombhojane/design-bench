"""Per-pattern precision/recall of detector output vs human labels.

Port of design-slop-cop tools/eval.mjs (MIT, Adrian Krebs), plus Wilson CIs.

Usage:
  .venv/bin/python -m judge.eval_labels --labels <labels.jsonl> --raw data/phase0/results/raw
  ... --pattern gradients   # adds FP/FN URLs for one pattern
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--pattern")
    args = ap.parse_args()

    labels: dict[str, dict] = {}
    for line in Path(args.labels).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("slug"):
            labels[rec["slug"]] = rec  # append-only: latest wins

    raw_dir = Path(args.raw)
    stats: dict[str, dict] = {}
    sites = 0
    errors = 0
    for slug, rec in labels.items():
        f = raw_dir / f"{slug}.json"
        if not f.exists():
            continue
        raw = json.loads(f.read_text())
        if raw.get("error"):
            errors += 1
            continue
        sites += 1
        det = {p["id"]: bool(p["triggered"]) for p in raw.get("patterns", [])}
        for pid, user in (rec.get("labels") or {}).items():
            if user not in ("present", "not_present"):
                continue
            if pid not in det:
                s = stats.setdefault(pid, {"tp": 0, "fp": 0, "fn": 0, "tn": 0,
                                           "fpU": [], "fnU": [], "unimplemented": True})
                continue
            s = stats.setdefault(pid, {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "fpU": [], "fnU": []})
            present, trig = user == "present", det[pid]
            if trig and present:
                s["tp"] += 1
            elif trig and not present:
                s["fp"] += 1
                s["fpU"].append(rec["url"])
            elif not trig and present:
                s["fn"] += 1
                s["fnU"].append(rec["url"])
            else:
                s["tn"] += 1

    print(f"{sites} scanned+labeled sites ({errors} scan errors, {len(labels)} labels total)\n")
    hdr = f"{'pattern':26s} {'TP':>3} {'FP':>3} {'FN':>3} {'TN':>3}  {'prec':>6} {'rec':>6} {'F1':>6}  prec 95% CI"
    print(hdr)
    print("-" * len(hdr))
    for pid, s in sorted(stats.items()):
        if s.get("unimplemented"):
            print(f"{pid:26s} (labeled but not implemented)")
            continue
        tp, fp, fn = s["tp"], s["fp"], s["fn"]
        prec = tp / (tp + fp) if tp + fp else float("nan")
        rec = tp / (tp + fn) if tp + fn else float("nan")
        f1 = 2 * prec * rec / (prec + rec) if prec + rec and not math.isnan(prec + rec) else float("nan")
        lo, hi = wilson(tp, tp + fp) if tp + fp else (0, 1)
        fmt = lambda x: f"{100 * x:5.1f}%" if not math.isnan(x) else "    - "
        print(f"{pid:26s} {tp:3d} {fp:3d} {fn:3d} {s['tn']:3d}  {fmt(prec)} {fmt(rec)} {fmt(f1)}  "
              f"[{100 * lo:.0f}–{100 * hi:.0f}%]")

    if args.pattern and args.pattern in stats:
        s = stats[args.pattern]
        print(f"\n{args.pattern} false positives:", *s["fpU"], sep="\n  ")
        print(f"{args.pattern} false negatives:", *s["fnU"], sep="\n  ")


if __name__ == "__main__":
    main()
