"""Build the gallery: every generated page, compared brief by brief.

One section per brief (title, full brief, type), then one card per design
skill showing a large screenshot with a seed switcher (1 · 2 · 3), the heading
font, how many brief requirements it met, and the giveaways found (plain
names). Click a screenshot for a full-size view and a link to the live page.

Only pages that were scored are listed (same set as the stats and dataset).
A skill gets a column only if it has pages for at least half the briefs.

Usage:
  .venv/bin/python -m judge.gallery                      -> gallery.html (local, all briefs)
  .venv/bin/python -m judge.gallery --public-site site   -> site/gallery.html + pages/ + shots/
"""
from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / "data/phase1/gen"
SCAN = ROOT / "data/phase1/scan"
ASSERT = ROOT / "data/phase1/assertions"
BRIEFS = ROOT / "data/briefs/all-briefs.jsonl"
TELLS = ROOT / "tells/tells-2026.12.json"
ARMS = ["bare", "openai-guide-prompt", "impeccable", "anthropic-frontend-design", "hallmark"]
ARM_LABEL = {"bare": "No skill", "anthropic-frontend-design": "Anthropic skill",
             "impeccable": "impeccable", "openai-guide-prompt": "OpenAI guide", "hallmark": "Hallmark"}
TYPE_LABEL = {"neutral": "Plain brief", "standard": "Brief with direction",
              "pair": "Paired brief", "antislop": "Brief that bans clichés"}
TYPE_HELP = {"neutral": "no style words, so default taste shows",
             "standard": "the client describes the look they want",
             "pair": "same kind of page as another brief, different industry",
             "antislop": "the client explicitly bans common AI clichés"}
TELL_NAME = {
    "all_caps_headings": "ALL-CAPS labels", "hero_eyebrow_pill": "Pill above headline",
    "colored_glows": "Glow shadows", "hero_font_mix": "Italic word in headline",
    "icon_card_grid": "Icon card grid", "gradients": "Gradients", "accent_stripe": "Stripe on cards",
    "perma_dark_mode": "Dark by default", "faq_accordion": "FAQ accordion",
}
e = html.escape


def main(public: bool = False, out_dir: Path | None = None) -> None:
    briefs = [json.loads(l) for l in BRIEFS.read_text().splitlines() if l.strip()]
    if public:  # never publish held-out briefs or their outputs
        briefs = [b for b in briefs if b.get("split") == "public"]
    gen_prefix = "pages" if public else "data/phase1/gen"
    shot_prefix = "shots" if public else "data/phase1/scan/screenshots"
    pack = json.loads(TELLS.read_text())
    validated = {t["id"] for t in pack["tells"] if t["status"] == "validated"}

    def page_info(slug: str) -> dict | None:
        raw_f = SCAN / "raw" / f"{slug}.json"
        if not (GEN / f"{slug}.html").exists() or not raw_f.exists():
            return None  # only pages that were scored (same set as stats + dataset)
        if not (SCAN / "screenshots" / f"{slug}.png").exists():
            return None
        raw = json.loads(raw_f.read_text())
        tells = [TELL_NAME.get(p["id"], p["id"]) for p in raw.get("patterns", [])
                 if p["triggered"] and p["id"] in validated]
        a_f = ASSERT / f"{slug}.json"
        adh = json.loads(a_f.read_text()) if a_f.exists() else {}
        return {"img": f"{shot_prefix}/{slug}.png", "href": f"{gen_prefix}/{slug}.html",
                "font": (raw.get("fonts") or {}).get("headingFont") or "unknown",
                "met": adh.get("passed"), "of": adh.get("checked"), "tells": tells}

    order = {"neutral": 0, "standard": 1, "pair": 2, "antislop": 3}
    briefs.sort(key=lambda b: (order.get(b["group"], 9), b["id"]))

    # which skills get a column: pages for at least half the briefs
    coverage = {a: sum(1 for b in briefs if any(page_info(f"{b['id']}__{a}__s{s}") for s in (1, 2, 3)))
                for a in ARMS}
    arms = [a for a in ARMS if coverage[a] >= len(briefs) / 2]
    left_out = [a for a in ARMS if a not in arms and coverage[a] > 0]

    sections, n_pages = [], 0
    for b in briefs:
        cards = []
        for arm in arms:
            seeds = [page_info(f"{b['id']}__{arm}__s{s}") for s in (1, 2, 3)]
            seeds = [s for s in seeds if s]
            n_pages += len(seeds)
            if not seeds:
                cards.append(f'<div class="card empty"><h3>{e(ARM_LABEL[arm])}</h3><p class="none">Not generated</p></div>')
                continue
            first = seeds[0]
            data = e(json.dumps(seeds))
            switch = "".join(f'<button type="button" data-i="{i}"{" aria-pressed=\"true\"" if i == 0 else ""}>{i + 1}</button>'
                             for i in range(len(seeds))) if len(seeds) > 1 else ""
            tell_txt = ", ".join(first["tells"]) if first["tells"] else "None found"
            met = f'{first["met"]} of {first["of"]}' if first["met"] is not None else "n/a"
            cards.append(
                f'<div class="card" data-seeds="{data}" data-tells="{len(first["tells"])}">'
                f'<div class="cardhead"><h3>{e(ARM_LABEL[arm])}</h3>'
                f'{"<span class=\"switch\" aria-label=\"Attempt\">" + switch + "</span>" if switch else ""}</div>'
                f'<button type="button" class="shot" aria-label="View {e(ARM_LABEL[arm])} page larger">'
                f'<img loading="lazy" src="{first["img"]}" alt="{e(b["title"])}, {e(ARM_LABEL[arm])}"></button>'
                f'<dl><dt>Heading font</dt><dd class="f">{e(first["font"])}</dd>'
                f'<dt>Brief requirements met</dt><dd class="m">{met}</dd>'
                f'<dt>Giveaways</dt><dd class="t{"" if first["tells"] else " clean"}">{e(tell_txt)}</dd></dl>'
                f'<a class="open" href="{first["href"]}" target="_blank" rel="noopener">Open the page</a></div>')
        sections.append(
            f'<section class="brief" data-type="{b["group"]}" id="{b["id"]}">'
            f'<div class="briefhead"><h2>{e(b["title"])}</h2>'
            f'<p class="type">{TYPE_LABEL.get(b["group"], b["group"])} · {e(b["sector"])}</p>'
            f'<p class="text">{e(b["brief"])}</p></div>'
            f'<div class="cards" style="--n:{len(arms)}">{"".join(cards)}</div></section>')

    note = ""
    if left_out:
        names = ", ".join(f"{ARM_LABEL[a]} ({coverage[a]} briefs)" for a in left_out)
        note = f'<p class="note">Not shown because they cover too few briefs: {e(names)}.</p>'

    filters = "".join(f'<button type="button" data-f="{k}">{v}</button>' for k, v in TYPE_LABEL.items())
    legend = "".join(f"<li><b>{v}</b>: {TYPE_HELP[k]}</li>" for k, v in TYPE_LABEL.items())

    out = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>design-bench: every page, brief by brief</title>
<meta name="description" content="Every page one AI model built for 24 website briefs under four sets of design instructions, side by side.">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=IBM+Plex+Sans:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {{ color-scheme: light; --bg:#fcfcfb; --ink:#141413; --ink2:#52514e; --ink3:#77766f; --line:#e4e2dc; --soft:#f3f2ee; --card:#ffffff; --link:#1c5cab; --warn:#a34a1f; --ok:#2f6b3a; }}
@media (prefers-color-scheme: dark) {{ :root:where(:not([data-theme="light"])) {{ color-scheme: dark; --bg:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --ink3:#9a988f; --line:#34332f; --soft:#232321; --card:#21211f; --link:#86b6ef; --warn:#e8946b; --ok:#8fc59a; }} }}
:root[data-theme="dark"] {{ color-scheme: dark; --bg:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --ink3:#9a988f; --line:#34332f; --soft:#232321; --card:#21211f; --link:#86b6ef; --warn:#e8946b; --ok:#8fc59a; }}
* {{ box-sizing:border-box; }}
html {{ -webkit-text-size-adjust:100%; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:17px/1.6 "Source Serif 4", Georgia, serif; }}
.top {{ max-width:760px; margin:0 auto; padding:48px 20px 8px; }}
.back {{ font:15px/1.4 "IBM Plex Sans", system-ui, sans-serif; margin:0 0 22px; }}
a {{ color:var(--link); }}
h1 {{ font-size:38px; line-height:1.15; margin:0 0 12px; font-weight:600; }}
.dek {{ font-size:20px; line-height:1.5; color:var(--ink2); margin:0 0 18px; }}
.howto {{ font:15px/1.6 "IBM Plex Sans", system-ui, sans-serif; color:var(--ink2); margin:0 0 6px; }}
.howto ul {{ margin:6px 0 0; padding-left:20px; }}
.note {{ font:14px/1.5 "IBM Plex Sans", system-ui, sans-serif; color:var(--ink3); }}
.bar {{ position:sticky; top:0; z-index:5; background:var(--bg); border-bottom:1px solid var(--line); }}
.barin {{ max-width:1280px; margin:0 auto; padding:12px 20px; display:flex; flex-wrap:wrap; gap:8px; align-items:center; font:14px/1 "IBM Plex Sans", system-ui, sans-serif; }}
.barin button {{ font:inherit; color:var(--ink); background:var(--card); border:1px solid var(--line); border-radius:4px; padding:8px 12px; cursor:pointer; }}
.barin button[aria-pressed="true"] {{ border-color:var(--ink); background:var(--soft); }}
.barin .sep {{ width:1px; height:22px; background:var(--line); margin:0 4px; }}
.count {{ color:var(--ink3); margin-left:auto; }}
main {{ max-width:1280px; margin:0 auto; padding:8px 20px 80px; }}
section.brief {{ padding:40px 0 8px; border-bottom:1px solid var(--line); scroll-margin-top:64px; }}
.briefhead {{ max-width:760px; }}
h2 {{ font-size:26px; line-height:1.25; margin:0 0 4px; font-weight:600; }}
.type {{ font:14px/1.5 "IBM Plex Sans", system-ui, sans-serif; color:var(--ink3); margin:0 0 10px; }}
.text {{ font-size:16px; color:var(--ink2); margin:0 0 22px; }}
.cards {{ display:grid; grid-template-columns:repeat(var(--n), minmax(0, 1fr)); gap:18px; margin-bottom:32px; }}
.card {{ font:14px/1.45 "IBM Plex Sans", system-ui, sans-serif; min-width:0; }}
.cardhead {{ display:flex; justify-content:space-between; align-items:baseline; margin:0 0 8px; }}
h3 {{ font:500 15px/1.3 "IBM Plex Sans", system-ui, sans-serif; margin:0; }}
.switch {{ display:flex; gap:4px; }}
.switch button {{ font:13px/1 "IBM Plex Sans", system-ui, sans-serif; color:var(--ink2); background:none; border:1px solid var(--line); border-radius:3px; width:26px; height:24px; cursor:pointer; }}
.switch button[aria-pressed="true"] {{ color:var(--ink); border-color:var(--ink2); }}
.shot {{ display:block; width:100%; padding:0; border:1px solid var(--line); border-radius:4px; overflow:hidden; background:var(--soft); cursor:zoom-in; }}
.shot:hover {{ border-color:var(--ink2); }}
.shot img {{ display:block; width:100%; aspect-ratio:1440/900; object-fit:cover; object-position:top; }}
dl {{ display:grid; grid-template-columns:auto 1fr; gap:2px 10px; margin:10px 0 6px; }}
dt {{ color:var(--ink3); }} dd {{ margin:0; color:var(--ink); }}
dd.t {{ color:var(--warn); }} dd.t.clean {{ color:var(--ok); }}
.open {{ font-size:14px; }}
.card.empty .none {{ color:var(--ink3); border:1px dashed var(--line); border-radius:4px; aspect-ratio:1440/900; display:flex; align-items:center; justify-content:center; margin:0; }}
.dim .card[data-tells="0"] {{ opacity:.25; }}
dialog {{ border:0; padding:0; max-width:min(1200px, 94vw); background:var(--card); color:var(--ink); border-radius:6px; }}
dialog::backdrop {{ background:rgba(0,0,0,.7); }}
dialog img {{ display:block; width:100%; height:auto; }}
.dlgbar {{ display:flex; justify-content:space-between; gap:12px; padding:12px 16px; font:14px/1.4 "IBM Plex Sans", system-ui, sans-serif; }}
.dlgbar button {{ font:inherit; color:var(--ink); background:none; border:1px solid var(--line); border-radius:4px; padding:6px 10px; cursor:pointer; }}
@media (max-width: 1000px) {{ .cards {{ grid-template-columns:repeat(2, minmax(0, 1fr)); }} }}
@media (max-width: 560px) {{ .cards {{ grid-template-columns:1fr; }} h1 {{ font-size:30px; }} .dek {{ font-size:18px; }}
  .barin {{ flex-wrap:nowrap; overflow-x:auto; padding:10px 16px; }} .barin button {{ flex:0 0 auto; white-space:nowrap; }} .count {{ flex:0 0 auto; margin-left:8px; }} .barin .sep {{ flex:0 0 1px; }} }}
</style></head>
<body>
<div class="top">
<p class="back"><a href="./">← Findings and method</a></p>
<h1>Every page, brief by brief</h1>
<p class="dek">One model built each website three times under each set of design instructions. Pick a brief and compare what each skill produced.</p>
<div class="howto">Use the number buttons to switch between the three attempts, and click a screenshot to see it full size. Giveaways are the AI-design habits our detectors found on that page. The briefs come in four kinds:
<ul>{legend}</ul></div>
{note}
</div>
<div class="bar"><div class="barin" role="toolbar" aria-label="Filter briefs">
<button type="button" data-f="all" aria-pressed="true">All briefs</button>{filters}
<span class="sep"></span><button type="button" id="dim" aria-pressed="false">Fade pages without giveaways</button>
<span class="count" id="count"></span></div></div>
<main>{''.join(sections)}</main>
<dialog id="dlg"><img id="dlgimg" alt=""><div class="dlgbar"><a id="dlgopen" href="#" target="_blank" rel="noopener">Open the live page</a><button type="button" id="dlgclose">Close</button></div></dialog>
<script>
const secs=[...document.querySelectorAll('section.brief')], count=document.getElementById('count');
function upd(){{const v=secs.filter(s=>!s.hidden).length;count.textContent=v+' of '+secs.length+' briefs';}}
document.querySelectorAll('.barin button[data-f]').forEach(b=>b.addEventListener('click',()=>{{
 document.querySelectorAll('.barin button[data-f]').forEach(x=>x.setAttribute('aria-pressed',x===b));
 secs.forEach(s=>s.hidden=!(b.dataset.f==='all'||s.dataset.type===b.dataset.f));upd();}}));
const dim=document.getElementById('dim');dim.addEventListener('click',()=>{{const on=dim.getAttribute('aria-pressed')!=='true';
 dim.setAttribute('aria-pressed',on);document.querySelector('main').classList.toggle('dim',on);}});
document.querySelectorAll('.card[data-seeds]').forEach(c=>{{const seeds=JSON.parse(c.dataset.seeds);
 const show=i=>{{const s=seeds[i];c.querySelector('img').src=s.img;c.querySelector('.open').href=s.href;
  c.querySelector('dd.f').textContent=s.font;c.querySelector('dd.m').textContent=s.met==null?'n/a':s.met+' of '+s.of;
  const t=c.querySelector('dd.t');t.textContent=s.tells.length?s.tells.join(', '):'None found';t.classList.toggle('clean',!s.tells.length);
  c.dataset.tells=s.tells.length;c.querySelectorAll('.switch button').forEach(x=>x.setAttribute('aria-pressed',+x.dataset.i===i));c.dataset.cur=i;}};
 c.querySelectorAll('.switch button').forEach(x=>x.addEventListener('click',()=>show(+x.dataset.i)));
 c.querySelector('.shot').addEventListener('click',()=>{{const s=seeds[+(c.dataset.cur||0)];
  document.getElementById('dlgimg').src=s.img;document.getElementById('dlgimg').alt=c.querySelector('img').alt;
  document.getElementById('dlgopen').href=s.href;document.getElementById('dlg').showModal();}});}});
document.getElementById('dlgclose').addEventListener('click',()=>document.getElementById('dlg').close());
document.getElementById('dlg').addEventListener('click',ev=>{{if(ev.target.id==='dlg')ev.target.close();}});
upd();
</script>
</body></html>"""
    target = (out_dir / "gallery.html") if out_dir else (ROOT / "gallery.html")
    target.write_text(out)
    print(f"gallery.html: {len(briefs)} briefs x {len(arms)} skills, {n_pages} pages; left out: {left_out}")


if __name__ == "__main__":
    import argparse
    import shutil
    ap = argparse.ArgumentParser()
    ap.add_argument("--public-site", help="build a deployable public site into this dir")
    a = ap.parse_args()
    if a.public_site:
        site = Path(a.public_site)
        (site / "pages").mkdir(parents=True, exist_ok=True)
        (site / "shots").mkdir(parents=True, exist_ok=True)
        pub = {json.loads(l)["id"] for l in BRIEFS.read_text().splitlines() if l.strip()
               and json.loads(l).get("split") == "public"}
        n = 0
        for f in GEN.glob("*.html"):
            s = SCAN / "screenshots" / f"{f.stem}.png"
            if f.stem.split("__")[0] in pub and s.exists() and (SCAN / "raw" / f"{f.stem}.json").exists():
                shutil.copyfile(f, site / "pages" / f.name)
                shutil.copyfile(s, site / "shots" / s.name)
                n += 1
        main(public=True, out_dir=site)
        print(f"public site: {n} pages")
    else:
        main()
