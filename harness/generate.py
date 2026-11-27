"""Generate pages: briefs × skill arms × seeds on Groq (round-robin keys).

Resume-safe (skips existing outputs), records usage/latency/pack-sha per run.
The output contract is identical across arms; only the system prompt varies.

Usage:
  .venv/bin/python -m harness.generate --briefs data/briefs/public.jsonl \
      --out data/phase1/gen [--arms bare,hallmark] [--seeds 3] [--limit 10] \
      [--model openai/gpt-oss-120b] [--concurrency 3]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARMS_DIR = ROOT / "data" / "arms"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

CONTRACT = """
Build this as ONE complete, self-contained index.html:
- All CSS inline in one <style> tag; any JavaScript inline in one <script> tag (optional).
- No external scripts, stylesheets or images. Google Fonts via <link> IS allowed.
- Where a photo or illustration would go, use a styled placeholder block with a real alt/aria-label.
- Write real copy appropriate to the brief — no lorem ipsum, no [placeholder].
- Return exactly ONE fenced ```html code block containing the full document from <!doctype html> to </html>, and nothing after the block."""


def load_keys() -> list[str]:
    keys = []
    for line in (ROOT.parent / ".env").read_text().splitlines():
        line = line.strip()
        if re.match(r"^groq\d+=", line):
            keys.append(line.split("=", 1)[1].strip().strip('"'))
    if not keys:
        raise SystemExit("no groq keys in ../.env")
    return keys


class KeyRing:
    def __init__(self, keys: list[str]):
        self.keys = keys
        self.i = 0
        self.lock = threading.Lock()

    def next(self) -> str:
        with self.lock:
            k = self.keys[self.i % len(self.keys)]
            self.i += 1
            return k


def extract_html(text: str) -> str | None:
    blocks = re.findall(r"```(?:html)?\s*\n(.*?)```", text, flags=re.S)
    for b in reversed(blocks):
        if "<html" in b.lower() or "<!doctype" in b.lower():
            return b.strip()
    t = text.strip()
    if t.lower().startswith("<!doctype") or t.lower().startswith("<html"):
        return t
    return None


def call_groq(ring: KeyRing, model: str, system: str, user: str,
              temperature: float, max_retries: int = 6) -> dict:
    body = {
        "model": model,
        "temperature": temperature,
        "max_completion_tokens": max(2000, 7900 - (len(system) + len(user)) // 4),  # Groq free tier: prompt+cap <= 8k TPM
        "stream": True,  # the filtering proxy truncates big buffered bodies; SSE passes
        "stream_options": {"include_usage": True},
        "messages": ([{"role": "system", "content": system}] if system else [])
                    + [{"role": "user", "content": user}],
    }
    last = None
    for attempt in range(max_retries):
        key = ring.next()
        req = urllib.request.Request(
            GROQ_URL, data=json.dumps(body).encode(),
            headers={"Authorization": "Bearer " + key,
                     "Content-Type": "application/json",
                     "Accept": "text/event-stream",
                     "User-Agent": "Mozilla/5.0"})
        t0 = time.time()
        try:
            content, finish, usage, served = [], None, None, None
            with urllib.request.urlopen(req, timeout=600) as r:
                for raw in r:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload == "[DONE]":
                        break
                    chunk = json.loads(payload)
                    served = chunk.get("model") or served
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    for ch in chunk.get("choices") or []:
                        delta = (ch.get("delta") or {}).get("content")
                        if delta:
                            content.append(delta)
                        if ch.get("finish_reason"):
                            finish = ch["finish_reason"]
            if not content:
                raise OSError("stream returned no content")
            return {"choices": [{"message": {"content": "".join(content)},
                                 "finish_reason": finish}],
                    "usage": usage, "model": served,
                    "_latency_s": round(time.time() - t0, 2)}
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read()[:200]!r}"
            if e.code in (429, 498, 499, 500, 502, 503):
                time.sleep(min(60, 2 ** attempt + random.random() * 3))
                continue
            break
        except Exception as e:  # noqa: BLE001
            last = str(e)[:200]
            time.sleep(min(30, 2 ** attempt))
    return {"_error": last}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--briefs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--arms", default="bare,anthropic-frontend-design,hallmark,impeccable,openai-guide-prompt")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--model", default="openai/gpt-oss-120b")
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--limit", type=int, help="max generations this run (pilot)")
    ap.add_argument("--concurrency", type=int, default=3)
    args = ap.parse_args()

    briefs = [json.loads(l) for l in Path(args.briefs).read_text().splitlines() if l.strip()]
    arms = args.arms.split(",")
    packs = {a: (ARMS_DIR / f"{a}.txt").read_text() for a in arms}
    pack_manifest = json.loads((ARMS_DIR / "manifest.json").read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ring = KeyRing(load_keys())

    jobs = []
    for b in briefs:
        for arm in arms:
            for seed in range(1, args.seeds + 1):
                name = f"{b['id']}__{arm}__s{seed}"
                if (out / f"{name}.html").exists():
                    continue
                jobs.append((b, arm, seed, name))
    if args.limit:
        jobs = jobs[: args.limit]
    print(f"{len(jobs)} generations to run (model {args.model})")

    model_slug = re.sub(r"[^a-z0-9.-]", "-", args.model.split("/")[-1].lower())

    def run(job):
        b, arm, seed, name = job
        user = f"Client brief — {b['title']} ({b['sector']}):\n\n{b['brief']}\n{CONTRACT}"
        d = call_groq(ring, args.model, packs[arm], user, args.temperature)
        meta = {"name": name, "brief": b["id"], "arm": arm, "seed": seed,
                "model": args.model,
                "pack_sha": pack_manifest.get(arm, {}).get("sha256"),
                "temperature": args.temperature}
        if "_error" in d:
            meta["error"] = d["_error"]
        else:
            content = d["choices"][0]["message"].get("content") or ""
            html = extract_html(content)
            meta.update({
                "latency_s": d.get("_latency_s"),
                "usage": d.get("usage"),
                "finish_reason": d["choices"][0].get("finish_reason") or (d["choices"][0].get("message") or {}).get("finish_reason"),
                "extracted": bool(html),
                "model_served": d.get("model"), "generated_by": model_slug,
            })
            if html:
                (out / f"{name}.html").write_text(html)
            else:
                meta["error"] = "no html block"
                meta["raw_head"] = content[:300]
        (out / f"{name}.json").write_text(json.dumps(meta, indent=1))
        ok = "OK " if not meta.get("error") else "ERR"
        print(f"  {ok} {name} ({meta.get('latency_s', '-')}s)", flush=True)
        return meta

    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        results = list(ex.map(run, jobs))

    errs = [r for r in results if r.get("error")]
    print(f"done: {len(results) - len(errs)} ok, {len(errs)} errors")
    if errs[:3]:
        for e in errs[:3]:
            print("  err:", e["name"], str(e.get("error"))[:120])


if __name__ == "__main__":
    main()
