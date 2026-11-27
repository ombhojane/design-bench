"""Per-tell fire rates across corpora + AI-vs-human odds ratios.

A tell is only real if it separates AI output from human pages. For each
pattern: rate per corpus, odds ratio (Haldane–Anscombe 0.5 correction),
log-method 95% CI. Optional per-model breakdown for slugs shaped
`<model>__<task>`.

Usage:
  .venv/bin/python -m judge.corpus_stats \
      --corpus ai=data/phase0/kombai-results/raw \
      --corpus human=data/phase0/tranco-results/raw \
      [--corpus ceiling=data/phase0/awwwards-results/raw] \
      [--per-model ai] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path


def load_dir(raw: Path) -> dict[str, dict]:
    out = {}
    for f in raw.glob("*.json"):
        r = json.loads(f.read_text())
        if r.get("error") or "patterns" not in r:
            continue
        out[r["slug"]] = {p["id"]: bool(p["triggered"]) for p in r["patterns"]}
    return out


def odds_ratio(a: int, n1: int, b: int, n2: int) -> tuple[float, float, float]:
    """OR of rate1 vs rate2 with Haldane–Anscombe correction; log-method 95% CI."""
    a2, b2 = a + 0.5, b + 0.5
    c2, d2 = (n1 - a) + 0.5, (n2 - b) + 0.5
    or_ = (a2 / c2) / (b2 / d2)
    se = math.sqrt(1 / a2 + 1 / b2 + 1 / c2 + 1 / d2)
    return or_, math.exp(math.log(or_) - 1.96 * se), math.exp(math.log(or_) + 1.96 * se)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", action="append", required=True,
                    help="name=path/to/raw (first is the AI corpus, second the human reference)")
    ap.add_argument("--per-model", help="corpus name whose slugs are <model>__<task>")
    ap.add_argument("--json", help="also write machine-readable output here")
    args = ap.parse_args()

    corpora: dict[str, dict[str, dict]] = {}
    for spec in args.corpus:
        name, path = spec.split("=", 1)
        corpora[name] = load_dir(Path(path))

    names = list(corpora)
    pattern_ids: list[str] = []
    for sites in corpora.values():
        for verd in sites.values():
            for pid in verd:
                if pid not in pattern_ids:
                    pattern_ids.append(pid)

    sizes = {n: len(s) for n, s in corpora.items()}
    print("corpus sizes:", ", ".join(f"{n}={v}" for n, v in sizes.items()), "\n")

    rows = []
    for pid in sorted(pattern_ids):
        counts = {n: sum(1 for v in corpora[n].values() if v.get(pid)) for n in names}
        rates = {n: counts[n] / sizes[n] if sizes[n] else float("nan") for n in names}
        row = {"pattern": pid, "counts": counts, "rates": rates}
        if len(names) >= 2:
            a, n1 = counts[names[0]], sizes[names[0]]
            b, n2 = counts[names[1]], sizes[names[1]]
            row["or"], row["or_lo"], row["or_hi"] = odds_ratio(a, n1, b, n2)
        rows.append(row)

    hdr = f"{'pattern':26s}" + "".join(f" {n:>12s}" for n in names)
    if len(names) >= 2:
        hdr += f"  {'OR ' + names[0] + '/' + names[1]:>16s}  95% CI"
    print(hdr)
    print("-" * len(hdr))
    for row in sorted(rows, key=lambda r: -r.get("or", 0)):
        line = f"{row['pattern']:26s}"
        for n in names:
            line += f" {100 * row['rates'][n]:10.1f}%"
        if "or" in row:
            sig = "*" if row["or_lo"] > 1 or row["or_hi"] < 1 else " "
            line += f"  {row['or']:15.1f}{sig}  [{row['or_lo']:.1f}–{row['or_hi']:.1f}]"
        print(line)
    if len(names) >= 2:
        print("\n* = CI excludes 1 (the tell separates the two corpora)")

    if args.per_model and args.per_model in corpora:
        print(f"\nPer-model tell counts ({args.per_model}):")
        by_model: dict[str, list[dict]] = defaultdict(list)
        for slug, verd in corpora[args.per_model].items():
            model = slug.split("__", 1)[0] if "__" in slug else "?"
            by_model[model].append(verd)
        model_rows = []
        for model, verds in by_model.items():
            mean_tells = sum(sum(v.values()) for v in verds) / len(verds)
            top = defaultdict(int)
            for v in verds:
                for pid, t in v.items():
                    if t:
                        top[pid] += 1
            common = sorted(top.items(), key=lambda x: -x[1])[:3]
            model_rows.append((mean_tells, model, len(verds), common))
        for mean_tells, model, n, common in sorted(model_rows):
            tops = ", ".join(f"{p}({c}/{n})" for p, c in common)
            print(f"  {model:28s} {mean_tells:4.1f} tells/page (n={n})  top: {tops}")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"sizes": sizes, "rows": rows}, indent=1, default=float))
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
