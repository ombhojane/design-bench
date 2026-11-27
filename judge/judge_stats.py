"""Score LLM-judge ratings against the blind keys.

  kg     known-groups validity: mean G per group, AI-vs-human AUC, null rate.
  retest test-retest agreement between two ratings files on the same tiles.
  pairs  pairwise skill verdicts: win/tie/loss vs bare with order-flip control.
  abs    absolute G per arm on Phase-1 neutral briefs (seed-averaged per brief).
  distinct sameness per arm sheet.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
J = ROOT / "data" / "judge"


def load(p: Path) -> dict:
    return json.loads(p.read_text())


def auc(pos: list[float], neg: list[float]) -> float:
    wins = 0.0
    for a in pos:
        for b in neg:
            wins += 1.0 if a > b else 0.5 if a == b else 0.0
    return wins / (len(pos) * len(neg)) if pos and neg else float("nan")


def kg(ratings_file: str = "ratings.json") -> None:
    key = load(J / "kg" / "key.json")
    r = load(J / "kg" / ratings_file)["ratings"]
    by = defaultdict(list)
    nulls = defaultdict(int)
    for k, v in r.items():
        g = key[k]["truth"]
        if v is None:
            nulls[g] += 1
        else:
            by[g].append(v)
    for g in ("ai", "ordinary", "ceiling"):
        xs = by[g]
        print(f"{g:9s} n={len(xs):2d} nulls={nulls[g]}  mean G={sum(xs) / len(xs):.2f}  values={sorted(xs)}")
    human = by["ordinary"] + by["ceiling"]
    a = auc(by["ai"], human)
    order = (sum(by['ai']) / len(by['ai']) > sum(by['ordinary']) / len(by['ordinary'])
             > sum(by['ceiling']) / len(by['ceiling']))
    print(f"AUC (AI vs all human) = {a:.3f}   AUC (AI vs ceiling) = {auc(by['ai'], by['ceiling']):.3f}"
          f"   AUC (AI vs ordinary) = {auc(by['ai'], by['ordinary']):.3f}")
    print(f"gate: ordering AI > ordinary > ceiling: {order};  AUC >= 0.70: {a >= 0.70}")
    (J / "kg" / "result.json").write_text(json.dumps({
        "means": {g: sum(v) / len(v) for g, v in by.items()}, "n": {g: len(v) for g, v in by.items()},
        "nulls": dict(nulls), "auc_ai_vs_human": a,
        "auc_ai_vs_ceiling": auc(by["ai"], by["ceiling"]),
        "auc_ai_vs_ordinary": auc(by["ai"], by["ordinary"]), "ordering_ok": order}, indent=1))


def retest(a_file: str, b_file: str, setname: str) -> None:
    a = load(J / setname / a_file)["ratings"]
    b = load(J / setname / b_file)["ratings"]
    common = [k for k in a if k in b and a[k] is not None and b[k] is not None]
    within1 = sum(abs(a[k] - b[k]) <= 1 for k in common)
    exact = sum(a[k] == b[k] for k in common)
    print(f"test-retest on {len(common)} tiles: exact {exact / len(common):.0%}, within ±1 {within1 / len(common):.0%}")


def pairs() -> None:
    key = load(J / "pairs" / "key.json")
    r = load(J / "pairs" / "ratings.json")["ratings"]
    # collapse both orders: verdict expressed as skill/bare/tie
    per = defaultdict(list)
    for pid, v in r.items():
        k = key[pid]
        if v == "tie":
            w = "tie"
        else:
            skill_side = "B" if k["order"] == "bare_left" else "A"
            w = "skill" if v == skill_side else "bare"
        per[(k["brief"], k["skill"])].append(w)
    agg = defaultdict(lambda: {"skill": 0, "bare": 0, "tie": 0})
    flips = total = 0
    for (brief, skill), ws in per.items():
        total += 1
        if len(ws) == 2 and ws[0] == ws[1]:
            agg[skill][ws[0]] += 1
        else:
            agg[skill]["tie"] += 1
            if len(ws) == 2 and "tie" not in ws:
                flips += 1
    print(f"position-flip rate: {flips}/{total} pairs flipped with order")
    print(f"{'skill':28s} {'skill wins':>10s} {'bare wins':>10s} {'ties':>6s}")
    for s, d in agg.items():
        print(f"{s:28s} {d['skill']:>10d} {d['bare']:>10d} {d['tie']:>6d}")
    (J / "pairs" / "result.json").write_text(json.dumps({"agg": agg, "flips": flips, "pairs": total}, indent=1))


def absolute() -> None:
    key = load(J / "abs" / "key.json")
    r = load(J / "abs" / "ratings.json")["ratings"]
    cell = defaultdict(lambda: defaultdict(list))
    for k, v in r.items():
        if v is None:
            continue
        brief, arm, _ = key[k]["truth"].split("|")
        cell[arm][brief].append(v)
    means = {a: {b: sum(v) / len(v) for b, v in bs.items()} for a, bs in cell.items()}
    print(f"{'arm':28s} mean G (brief-level)   n briefs")
    for a, bs in sorted(means.items(), key=lambda x: sum(x[1].values()) / len(x[1])):
        print(f"{a:28s} {sum(bs.values()) / len(bs):.2f}                  {len(bs)}")
    # paired vs bare
    import math
    import itertools
    out = {}
    for a, bs in means.items():
        if a == "bare":
            continue
        common = [b for b in bs if b in means.get("bare", {})]
        d = [bs[b] - means["bare"][b] for b in common]
        if not d:
            continue
        obs = sum(d) / len(d)
        hits = tot = 0
        for signs in itertools.product((1, -1), repeat=len(d)):
            s = sum(x * y for x, y in zip(d, signs)) / len(d)
            hits += abs(s) >= abs(obs) - 1e-12
            tot += 1
        out[a] = {"diff": obs, "p": hits / tot, "n": len(d)}
        print(f"  {a:26s} vs bare: diff {obs:+.2f} G  p={hits / tot:.3f}  (n={len(d)})")
    (J / "abs" / "result.json").write_text(json.dumps({"means": means, "vs_bare": out}, indent=1))


def distinct() -> None:
    key = load(J / "distinct" / "key.json")
    r = load(J / "distinct" / "ratings.json")["ratings"]
    for sid, v in sorted(r.items(), key=lambda x: x[1]["S"]):
        print(f"{key[sid]['arm']:28s} sameness S={v['S']}  devices: {v.get('devices')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["kg", "retest", "pairs", "abs", "distinct"])
    ap.add_argument("--a")
    ap.add_argument("--b")
    ap.add_argument("--set", default="kg")
    x = ap.parse_args()
    if x.mode == "kg":
        kg(x.a or "ratings.json")
    elif x.mode == "retest":
        retest(x.a, x.b, x.set)
    elif x.mode == "pairs":
        pairs()
    elif x.mode == "abs":
        absolute()
    else:
        distinct()
