"""Per-model board computed on VALIDATED tells only.

Reads the three-corpus odds table, keeps tells whose OR CI excludes 1 upward,
weights each by log2(OR), and scores every model page. Reports per model:
mean validated-tell count, mean weighted score, t-based 95% CI (n = pages),
and the model's top tells.

Usage:
  .venv/bin/python -m judge.board --odds data/phase0/odds-three-corpus.json \
      --raw data/phase0/kombai-results/raw --out board/phase0-model-board.json
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

T95 = {19: 2.093, 20: 2.086}  # t two-sided 0.05 for df 19/20


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--odds", required=True)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    odds = json.loads(Path(args.odds).read_text())
    validated = {}
    for row in odds["rows"]:
        if row.get("or_lo", 0) > 1:
            validated[row["pattern"]] = {"or": row["or"], "weight": math.log2(row["or"])}
    print(f"validated tells ({len(validated)}):",
          ", ".join(f"{p} w={v['weight']:.1f}" for p, v in
                    sorted(validated.items(), key=lambda x: -x[1]["weight"])))

    pages = defaultdict(list)
    for f in Path(args.raw).glob("*.json"):
        r = json.loads(f.read_text())
        if r.get("error") or "patterns" not in r:
            continue
        model = r["slug"].split("__", 1)[0] if "__" in r["slug"] else "?"
        trig = [p["id"] for p in r["patterns"] if p["triggered"] and p["id"] in validated]
        pages[model].append({
            "slug": r["slug"],
            "tells": trig,
            "count": len(trig),
            "weighted": sum(validated[t]["weight"] for t in trig),
        })

    board = []
    for model, rows in pages.items():
        n = len(rows)
        for key in ("count", "weighted"):
            vals = [r[key] for r in rows]
            mean = sum(vals) / n
            var = sum((v - mean) ** 2 for v in vals) / (n - 1) if n > 1 else 0.0
            half = T95.get(n - 1, 2.0) * math.sqrt(var / n)
            if key == "count":
                c_mean, c_half = mean, half
            else:
                w_mean, w_half = mean, half
        tally = defaultdict(int)
        for r in rows:
            for t in r["tells"]:
                tally[t] += 1
        board.append({
            "model": model, "n": n,
            "tells_mean": round(c_mean, 2), "tells_ci": round(c_half, 2),
            "weighted_mean": round(w_mean, 2), "weighted_ci": round(w_half, 2),
            "top_tells": sorted(tally.items(), key=lambda x: -x[1])[:3],
        })
    board.sort(key=lambda b: b["weighted_mean"])

    print(f"\n{'model':28s} {'validated tells/page':>22s} {'weighted score':>18s}  top tells")
    for b in board:
        tops = ", ".join(f"{t}({c}/{b['n']})" for t, c in b["top_tells"])
        print(f"{b['model']:28s} {b['tells_mean']:>8.2f} ± {b['tells_ci']:<10.2f}"
              f" {b['weighted_mean']:>8.2f} ± {b['weighted_ci']:<6.2f}  {tops}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "validated_tells": {p: v for p, v in validated.items()},
        "board": board,
        "note": "Ties: treat models whose weighted CIs overlap as tied.",
    }, indent=1))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
