"""Re-run pattern score() over stored signals without re-scanning sites.

Mirrors design-slop-cop's rescore.js idea: extract() results are cached in
each raw JSON; score() is pure, so threshold/logic changes apply offline.
score() is JS, so we evaluate it in a blank Chromium page in one batch.

Usage:
  .venv/bin/python -m harness.rescore --raw data/phase0/results/raw
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.bundle import pattern_files, _pattern_literal  # noqa: E402


def build_score_source() -> str:
    patterns = [_pattern_literal(f.read_text()) for f in pattern_files()]
    return (
        "(data) => {\n"
        "  const PATTERNS = [\n" + ",\n".join(patterns) + "\n];\n"
        """
  const out = {};
  for (const [slug, site] of Object.entries(data)) {
    const verdicts = [];
    for (const p of PATTERNS) {
      const T = p.thresholds || {};
      const sig = (site.signals || {})[p.id];
      let v;
      try {
        v = sig == null ? { triggered: false } : (p.score(sig, T, site.fonts || {}) || { triggered: false });
      } catch (e) {
        v = { triggered: false, error: String(e) };
      }
      verdicts.push({ id: p.id, label: p.label, category: p.category,
                      triggered: !!v.triggered, evidence: v.evidence || null,
                      ...(v.error ? { error: v.error } : {}) });
    }
    out[slug] = verdicts;
  }
  return out;
}"""
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    args = ap.parse_args()
    raw_dir = Path(args.raw)

    data = {}
    files = {}
    for f in raw_dir.glob("*.json"):
        r = json.loads(f.read_text())
        if r.get("error") or "signals" not in r:
            continue
        data[r["slug"]] = {"signals": r["signals"], "fonts": r.get("fonts") or {}}
        files[r["slug"]] = (f, r)

    src = build_score_source()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("about:blank")
        verdicts = page.evaluate(src, data)
        browser.close()

    changed = 0
    for slug, pats in verdicts.items():
        f, r = files[slug]
        old = {p["id"]: p["triggered"] for p in r.get("patterns", [])}
        new = {p["id"]: p["triggered"] for p in pats}
        if old != new:
            changed += 1
        r["patterns"] = pats
        flagged = sum(1 for p in pats if p["triggered"])
        r["patternsFlagged"] = flagged
        r["score"] = round(100 * flagged / len(pats)) if pats else 0
        f.write_text(json.dumps(r, indent=1))
    errs = sum(1 for pats in verdicts.values() for p in pats if p.get("error"))
    print(f"rescored {len(verdicts)} sites, {changed} changed, {errs} score() errors")


if __name__ == "__main__":
    main()
