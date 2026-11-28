"""Phase-1 analysis: do anti-slop skills work?

Inputs: detector scan of generated pages, adherence results, briefs, tells pack.
Per METHOD.md: unit = brief (seeds averaged first); paired skill-vs-bare
differences; exact-style sign-flip permutation test (200k draws, seeded);
Holm–Bonferroni over the 4 primary contrasts; per-tier breakdowns; mode-
relocation entropy (heading-font + scheme distributions per arm); MDE.

Usage:
  .venv/bin/python -m judge.matrix_stats --scan data/phase1/scan/raw \
      --assertions data/phase1/assertions --briefs data/briefs/all-briefs.jsonl \
      --tells tells/tells-2026.12.json --out board/phase1-skill-board.json
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def paired_test(diffs: list[float], draws: int = 200_000, seed: int = 20261127):
    """Sign-flip permutation on per-brief differences; two-sided p."""
    n = len(diffs)
    obs = mean(diffs)
    rng = random.Random(seed)
    if n <= 20:
        hits = total = 0
        for mask in range(1 << n):
            s = sum(d if (mask >> i) & 1 else -d for i, d in enumerate(diffs)) / n
            hits += abs(s) >= abs(obs) - 1e-12
            total += 1
        return obs, hits / total
    hits = 0
    for _ in range(draws):
        s = sum(d if rng.random() < 0.5 else -d for d in diffs) / n
        hits += abs(s) >= abs(obs) - 1e-12
    return obs, (hits + 1) / (draws + 1)


def holm(pvals: dict[str, float]) -> dict[str, float]:
    items = sorted(pvals.items(), key=lambda x: x[1])
    m = len(items)
    adj, prev = {}, 0.0
    for i, (k, p) in enumerate(items):
        a = min(1.0, max(prev, (m - i) * p))
        adj[k] = a
        prev = a
    return adj


def entropy(counter: dict) -> float:
    total = sum(counter.values())
    if not total:
        return 0.0
    return -sum((c / total) * math.log2(c / total) for c in counter.values() if c)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", required=True)
    ap.add_argument("--assertions", required=True)
    ap.add_argument("--briefs", required=True)
    ap.add_argument("--tells", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--gen", default="data/phase1/gen", help="generation metadata dir (for the model filter)")
    ap.add_argument("--model", default="openai/gpt-oss-120b",
                    help="only score pages made by this model; 'any' disables the filter")
    args = ap.parse_args()

    briefs = {b["id"]: b for b in
              (json.loads(l) for l in Path(args.briefs).read_text().splitlines() if l.strip())}
    pack = json.loads(Path(args.tells).read_text())
    weights = {t["id"]: t["weight"] for t in pack["tells"] if t["status"] == "validated"}

    # page-level records
    pages = []
    for f in Path(args.scan).glob("*.json"):
        r = json.loads(f.read_text())
        if r.get("error") or "__" not in r.get("slug", ""):
            continue
        brief_id, arm, seed = r["slug"].split("__")
        if brief_id not in briefs:
            continue
        if args.model != "any":
            mf = Path(args.gen) / f"{r['slug']}.json"
            made_by = json.loads(mf.read_text()).get("model") if mf.exists() else None
            if made_by != args.model:
                continue
        trig = [p["id"] for p in r["patterns"] if p["triggered"] and p["id"] in weights]
        af = Path(args.assertions) / f"{r['slug']}.json"
        adh = json.loads(af.read_text())["adherence"] if af.exists() else None
        pages.append({
            "brief": brief_id, "arm": arm, "seed": seed,
            "group": briefs[brief_id]["group"], "split": briefs[brief_id]["split"],
            "weighted": sum(weights[t] for t in trig), "count": len(trig),
            "tells": trig, "adherence": adh,
            "headingFont": (r.get("fonts") or {}).get("headingFont"),
            "dark": (r.get("meta") or {}).get("isDarkMode"),
        })
    print(f"{len(pages)} scored pages")

    # brief-level (seeds averaged) per arm
    cell = defaultdict(lambda: defaultdict(list))  # arm -> brief -> [page]
    for p in pages:
        cell[p["arm"]][p["brief"]].append(p)
    arms = sorted(cell)
    brief_means = {a: {b: {"weighted": mean(x["weighted"] for x in v),
                           "adherence": mean([x["adherence"] for x in v if x["adherence"] is not None] or [float("nan")])}
                       for b, v in cell[a].items()} for a in arms}

    # per-arm per-tier summary
    tiers = ["neutral", "standard", "pair", "antislop"]
    summary = {}
    for a in arms:
        s = {"overall_weighted": mean(v["weighted"] for v in brief_means[a].values()),
             "overall_adherence": mean(v["adherence"] for v in brief_means[a].values()
                                       if not math.isnan(v["adherence"]))}
        for t in tiers:
            bs = [b for b in brief_means[a] if briefs[b]["group"] == t]
            s[f"weighted_{t}"] = mean(brief_means[a][b]["weighted"] for b in bs)
            s[f"adherence_{t}"] = mean(brief_means[a][b]["adherence"] for b in bs
                                       if not math.isnan(brief_means[a][b]["adherence"]))
        # mode relocation: heading-font + scheme entropy over this arm's pages
        fonts = defaultdict(int)
        dark = defaultdict(int)
        for p in pages:
            if p["arm"] != a:
                continue
            fonts[(p["headingFont"] or "?").lower()] += 1
            dark[bool(p["dark"])] += 1
        s["font_entropy_bits"] = round(entropy(fonts), 2)
        s["distinct_fonts"] = len(fonts)
        s["top_fonts"] = sorted(fonts.items(), key=lambda x: -x[1])[:3]
        s["dark_rate"] = round(dark[True] / max(1, sum(dark.values())), 3)
        summary[a] = s

    # primary contrasts: skill vs bare on NEUTRAL briefs (weighted tells) + overall
    contrasts = {}
    base = "bare"
    for metric, tier in (("weighted", "neutral"), ("weighted", None), ("adherence", None)):
        pv = {}
        eff = {}
        for a in arms:
            if a == base:
                continue
            common = [b for b in brief_means[a] if b in brief_means[base]
                      and (tier is None or briefs[b]["group"] == tier)]
            diffs = [brief_means[a][b][metric] - brief_means[base][b][metric]
                     for b in common
                     if not (math.isnan(brief_means[a][b][metric]) or math.isnan(brief_means[base][b][metric]))]
            if len(diffs) < 5:
                continue
            obs, p = paired_test(diffs)
            d_mean = obs
            sd = math.sqrt(sum((d - d_mean) ** 2 for d in diffs) / (len(diffs) - 1))
            se = sd / math.sqrt(len(diffs))
            eff[a] = {"diff": round(obs, 3), "se": round(se, 3), "n": len(diffs), "p": round(p, 5)}
            pv[a] = p
        adj = holm(pv)
        for a in eff:
            eff[a]["p_holm"] = round(adj[a], 5)
            eff[a]["sig"] = adj[a] < 0.05
        key = f"{metric}_{tier or 'all'}_vs_bare"
        contrasts[key] = eff

    # MDE for the neutral-tier weighted contrast (paired, alpha=0.0125, power=0.8)
    sds = []
    for a in arms:
        if a == base:
            continue
        common = [b for b in brief_means[a] if b in brief_means[base] and briefs[b]["group"] == "neutral"]
        diffs = [brief_means[a][b]["weighted"] - brief_means[base][b]["weighted"] for b in common]
        if len(diffs) > 2:
            m = mean(diffs)
            sds.append(math.sqrt(sum((d - m) ** 2 for d in diffs) / (len(diffs) - 1)))
    if sds:
        sd_typ = mean(sds)
        n_b = 8  # neutral briefs
        mde = (2.5 + 0.84) * sd_typ / math.sqrt(n_b)  # z_{.00625}≈2.5 (Holm), z_.8=0.84
    else:
        mde = float("nan")

    print(f"\n{'arm':28s} {'wtd(neutral)':>12s} {'wtd(all)':>9s} {'adher':>7s} {'fontH':>6s} {'dark':>5s}  top heading fonts")
    for a in sorted(arms, key=lambda x: summary[x].get("weighted_neutral", 9)):
        s = summary[a]
        tops = ", ".join(f"{f}({c})" for f, c in s["top_fonts"])
        print(f"{a:28s} {s.get('weighted_neutral', float('nan')):>12.2f} {s['overall_weighted']:>9.2f}"
              f" {100 * s['overall_adherence']:>6.1f}% {s['font_entropy_bits']:>6.2f} {s['dark_rate']:>5.0%}  {tops}")

    print("\nSkill vs bare (weighted tells, NEUTRAL briefs; negative = skill reduces slop):")
    for a, e in sorted(contrasts.get("weighted_neutral_vs_bare", {}).items(), key=lambda x: x[1]["diff"]):
        star = " *" if e["sig"] else "  "
        print(f"  {a:28s} diff {e['diff']:+.2f} ± {e['se']:.2f}  p={e['p']:.4f} holm={e['p_holm']:.4f}{star} (n={e['n']})")
    print(f"\nMDE (neutral tier, paired, Holm α, power .8): {mde:.2f} weighted points")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({
        "summary": summary, "contrasts": contrasts, "mde_neutral_weighted": mde,
        "tells_pack": pack["version"], "n_pages": len(pages),
    }, indent=1, default=str))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
