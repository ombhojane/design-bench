"""Deterministic distinctiveness from computed-style features (reproducible check
on the LLM judge's sameness ratings).

Per page feature vector from the scan: heading font, top body font, body
background (CIELAB), dark-mode flag, and the validated-tell set. Per arm, mean
pairwise distance across its neutral-brief pages (seed-matched, all seeds):
higher = more distinct. Distance = mean of [heading font differs, body font
differs, ΔE(bg)/50 capped at 1, dark differs, Jaccard distance of tell sets].
"""
from __future__ import annotations

import itertools
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def lab(rgb: str):
    m = re.match(r"rgb\((\d+),(\d+),(\d+)\)", rgb or "")
    if not m:
        return None
    r, g, b = (int(x) / 255 for x in m.groups())
    f = lambda v: v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    R, G, B = f(r), f(g), f(b)
    X = (R * .4124 + G * .3576 + B * .1805) / .95047
    Y = R * .2126 + G * .7152 + B * .0722
    Z = (R * .0193 + G * .1192 + B * .9505) / 1.08883
    h = lambda t: t ** (1 / 3) if t > .008856 else 7.787 * t + 16 / 116
    X, Y, Z = h(X), h(Y), h(Z)
    return (116 * Y - 16, 500 * (X - Y), 200 * (Y - Z))


def main() -> None:
    briefs = [json.loads(l) for l in (ROOT / "data/briefs/all-briefs.jsonl").read_text().splitlines() if l.strip()]
    neutral = {b["id"] for b in briefs if b["group"] == "neutral"}
    by_arm_seed = defaultdict(lambda: defaultdict(dict))
    for f in (ROOT / "data/phase1/scan/raw").glob("*.json"):
        r = json.loads(f.read_text())
        if r.get("error"):
            continue
        brief, arm, seed = r["slug"].split("__")
        if brief not in neutral:
            continue
        fonts = r.get("fonts") or {}
        top = (fonts.get("topFonts") or [{}])[0].get("name")
        by_arm_seed[arm][seed][brief] = {
            "h": (fonts.get("headingFont") or "").lower(), "b": (top or "").lower(),
            "bg": lab((r.get("meta") or {}).get("bodyBg")), "dark": bool((r.get("meta") or {}).get("isDarkMode")),
            "tells": {p["id"] for p in r.get("patterns", []) if p["triggered"]},
        }

    def dist(a, b):
        de = 1.0 if not (a["bg"] and b["bg"]) else min(1.0, sum((x - y) ** 2 for x, y in zip(a["bg"], b["bg"])) ** .5 / 50)
        u = a["tells"] | b["tells"]
        jac = 0.0 if not u else 1 - len(a["tells"] & b["tells"]) / len(u)
        return (float(a["h"] != b["h"]) + float(a["b"] != b["b"]) + de + float(a["dark"] != b["dark"]) + jac) / 5

    out = {}
    for arm, seeds in by_arm_seed.items():
        ds = []
        for seed, pages in seeds.items():
            for x, y in itertools.combinations(sorted(pages), 2):
                ds.append(dist(pages[x], pages[y]))
        out[arm] = {"mean_pairwise_distance": round(sum(ds) / len(ds), 3), "pairs": len(ds)}
    print(f"{'arm':28s} distinctiveness (0=identical, 1=all differ)   pairs")
    for arm, v in sorted(out.items(), key=lambda x: -x[1]["mean_pairwise_distance"]):
        print(f"{arm:28s} {v['mean_pairwise_distance']:.3f}                                   {v['pairs']}")
    (ROOT / "board/phase1-css-distinctiveness.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
