"""Scan URLs or local HTML files with the in-page tell detector.

Mirrors design-slop-cop's src/run.js page lifecycle (MIT, Adrian Krebs):
domcontentloaded gate -> bounded networkidle -> fonts.ready -> lazy-load
scroll sweep -> back to top -> evaluate detector. Adds: viewport screenshot,
run manifest, JSON results compatible with the labels eval.

Usage:
  .venv/bin/python -m harness.scan --urls data/phase0/pilot-urls.txt --out data/phase0/results
  .venv/bin/python -m harness.scan --url https://example.com --out /tmp/x
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.bundle import build_detector_source  # noqa: E402

VIEWPORT = {"width": 1440, "height": 900}
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def slug_from_url(u: str) -> str:
    """Exact port of run.js slugFromUrl so results join with labels.jsonl."""
    try:
        from urllib.parse import urlparse
        p = urlparse(u)
        if p.scheme == "file":
            # Local corpora: basename (sans .html) is the stable, collision-free id.
            slug = (p.path or "").rsplit("/", 1)[-1]
            slug = re.sub(r"\.html?$", "", slug, flags=re.I)
        else:
            host = re.sub(r"^www\.", "", p.hostname or "")
            path = (p.path or "").rstrip("/").replace("/", "_")
            slug = host + path
    except Exception:
        slug = u
    return re.sub(r"[^a-z0-9._-]", "_", slug, flags=re.I)[:80]


async def analyze_page(browser, url: str, detector_source: str, out_dir: Path,
                       shot: bool = True) -> dict:
    context = await browser.new_context(
        viewport=VIEWPORT, user_agent=UA, device_scale_factor=1,
        color_scheme="light", locale="en-US",
    )
    page = await context.new_page()
    page.set_default_timeout(20000)
    started = time.time()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
    except Exception as e:
        await context.close()
        return {"url": url, "slug": slug_from_url(url), "error": str(e).split("\n")[0],
                "elapsedMs": int((time.time() - started) * 1000)}
    try:
        await page.wait_for_load_state("networkidle", timeout=2000)
    except Exception:
        pass
    try:
        await page.evaluate("document.fonts && document.fonts.ready")
    except Exception:
        pass
    await page.wait_for_timeout(500)
    try:
        await page.add_style_tag(content="html, body { scroll-behavior: auto !important; }")
    except Exception:
        pass
    try:
        await page.evaluate(
            """async () => { await new Promise(res => {
                 let y = 0, i = 0; const step = 900, maxSteps = 12;
                 const id = setInterval(() => { window.scrollTo(0, y); y += step; i++;
                   if (i >= maxSteps || y > document.documentElement.scrollHeight) { clearInterval(id); res(); }
                 }, 60); }); }"""
        )
    except Exception:
        pass
    await page.wait_for_timeout(250)
    try:
        await page.evaluate("window.scrollTo(0,0); document.documentElement.scrollTop=0; document.body.scrollTop=0;")
    except Exception:
        pass
    await page.wait_for_timeout(250)

    slug = slug_from_url(url)
    try:
        raw = await page.evaluate(detector_source)
    except Exception as e:
        await context.close()
        return {"url": url, "slug": slug, "error": "detector failed: " + str(e).split("\n")[0],
                "elapsedMs": int((time.time() - started) * 1000)}

    if shot:
        try:
            await page.screenshot(path=str(out_dir / "screenshots" / f"{slug}.png"))
        except Exception:
            pass
    await context.close()

    flagged = sum(1 for p in raw["patterns"] if p["triggered"])
    total = len(raw["patterns"])
    return {
        "url": url, "slug": slug, "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "elapsedMs": int((time.time() - started) * 1000),
        "score": round(100 * flagged / total) if total else 0,
        "patternsFlagged": flagged, "patternsTotal": total,
        **raw,
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--urls", help="file with one URL per line")
    ap.add_argument("--url", help="single URL")
    ap.add_argument("--out", required=True)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--no-screenshots", action="store_true")
    args = ap.parse_args()

    urls: list[str] = []
    if args.url:
        urls = [args.url]
    elif args.urls:
        urls = [l.strip() for l in Path(args.urls).read_text().splitlines()
                if l.strip() and not l.startswith("#")]
    else:
        ap.error("need --url or --urls")

    out = Path(args.out)
    (out / "raw").mkdir(parents=True, exist_ok=True)
    (out / "screenshots").mkdir(parents=True, exist_ok=True)
    detector = build_detector_source()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        sem = asyncio.Semaphore(args.concurrency)
        results = []

        async def run_one(u: str):
            async with sem:
                r = await analyze_page(browser, u, detector, out, shot=not args.no_screenshots)
                (out / "raw" / f"{r['slug']}.json").write_text(json.dumps(r, indent=1))
                status = r.get("error") or f"{r.get('patternsFlagged', '?')}/{r.get('patternsTotal', '?')} tells"
                print(f"  {r['slug'][:40]:42s} {status}", flush=True)
                results.append(r)

        await asyncio.gather(*(run_one(u) for u in urls))
        await browser.close()

    ok = [r for r in results if not r.get("error")]
    manifest = {
        "ranAt": datetime.now(timezone.utc).isoformat(),
        "urls": len(urls), "ok": len(ok), "errors": len(results) - len(ok),
        "viewport": VIEWPORT, "colorScheme": "light",
        "detectorSha": __import__("hashlib").sha256(detector.encode()).hexdigest()[:16],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(json.dumps(manifest))


if __name__ == "__main__":
    asyncio.run(main())
