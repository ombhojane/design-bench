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

    rows, n_pages = [], 0
    for b in briefs:
        cells = []
        for arm in arms:
            seeds = [page_info(f"{b['id']}__{arm}__s{s}") for s in (1, 2, 3)]
            seeds = [s for s in seeds if s]
            n_pages += len(seeds)
            if not seeds:
                cells.append('<td class="empty"><span>Not generated</span></td>')
                continue
            f = seeds[0]
            nt = len(f["tells"])
            gv = "no giveaways" if nt == 0 else f"{nt} giveaway{'s' if nt > 1 else ''}"
            cells.append(
                f'<td data-tells="{nt}"><button type="button" class="th" data-seeds="{e(json.dumps(seeds))}" '
                f'data-title="{e(b["title"])}" data-arm="{e(ARM_LABEL[arm])}" aria-label="{e(b["title"])}, {e(ARM_LABEL[arm])}">'
                f'<img loading="lazy" src="{f["img"]}" alt=""></button>'
                f'<span class="m">{e(f["font"])} · <span class="{"ok" if nt == 0 else "bad"}">{gv}</span></span></td>')
        rows.append(
            f'<tr data-type="{b["group"]}"><th scope="row"><span class="bt" title="{e(b["brief"])}">{e(b["title"])}</span>'
            f'<span class="ty">{TYPE_LABEL.get(b["group"], b["group"])}</span></th>{"".join(cells)}</tr>')

    note = ""
    if left_out:
        names = ", ".join(f"{ARM_LABEL[a]} ({coverage[a]} briefs)" for a in left_out)
        note = f" Not shown, too few pages: {e(names)}."
    filters = "".join(f'<button type="button" data-f="{k}">{v}</button>' for k, v in TYPE_LABEL.items())
    head = "".join(f"<th scope=\"col\">{e(ARM_LABEL[a])}</th>" for a in arms)

    out = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>design-bench: every page</title>
<meta name="description" content="Every page one AI model built for 24 website briefs under four sets of design instructions.">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,600&family=IBM+Plex+Sans:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {{ color-scheme: light; --bg:#fcfcfb; --ink:#141413; --ink2:#52514e; --ink3:#77766f; --line:#e4e2dc; --soft:#f3f2ee; --card:#ffffff; --link:#1c5cab; --bad:#a34a1f; --ok:#2f6b3a; }}
@media (prefers-color-scheme: dark) {{ :root:where(:not([data-theme="light"])) {{ color-scheme: dark; --bg:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --ink3:#9a988f; --line:#34332f; --soft:#232321; --card:#21211f; --link:#86b6ef; --bad:#e8946b; --ok:#8fc59a; }} }}
:root[data-theme="dark"] {{ color-scheme: dark; --bg:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --ink3:#9a988f; --line:#34332f; --soft:#232321; --card:#21211f; --link:#86b6ef; --bad:#e8946b; --ok:#8fc59a; }}
* {{ box-sizing:border-box; }}
html {{ -webkit-text-size-adjust:100%; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:14px/1.45 "IBM Plex Sans", system-ui, sans-serif; }}
header {{ max-width:1400px; margin:0 auto; padding:28px 20px 14px; }}
a {{ color:var(--link); }}
h1 {{ font:600 28px/1.2 "Source Serif 4", Georgia, serif; margin:6px 0 6px; }}
.lede {{ color:var(--ink2); margin:0 0 14px; max-width:860px; }}
.filters {{ display:flex; flex-wrap:wrap; gap:6px; align-items:center; }}
.filters button {{ font:inherit; font-size:13px; color:var(--ink); background:var(--card); border:1px solid var(--line); border-radius:4px; padding:6px 10px; cursor:pointer; }}
.filters button[aria-pressed="true"] {{ border-color:var(--ink); background:var(--soft); }}
.wrap {{ overflow-x:auto; padding:0 20px 60px; max-width:1400px; margin:0 auto; }}
table {{ border-collapse:separate; border-spacing:10px 0; min-width:900px; width:100%; table-layout:fixed; }}
thead th {{ position:sticky; top:0; z-index:2; background:var(--bg); text-align:left; font-weight:500; color:var(--ink2); padding:10px 0 8px; border-bottom:1px solid var(--line); }}
thead th:first-child {{ width:170px; }}
tbody th {{ text-align:left; vertical-align:top; font-weight:normal; padding:12px 0; }}
.bt {{ display:block; font-weight:500; color:var(--ink); cursor:help; }}
.ty {{ display:block; color:var(--ink3); font-size:12px; margin-top:2px; }}
td {{ vertical-align:top; padding:12px 0; }}
.th {{ display:block; width:100%; padding:0; border:1px solid var(--line); border-radius:3px; overflow:hidden; background:var(--soft); cursor:zoom-in; }}
.th:hover {{ border-color:var(--ink2); }}
.th img {{ display:block; width:100%; aspect-ratio:1440/900; object-fit:cover; object-position:top; }}
.m {{ display:block; font-size:12px; color:var(--ink3); margin-top:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.ok {{ color:var(--ok); }} .bad {{ color:var(--bad); }}
td.empty span {{ display:flex; align-items:center; justify-content:center; aspect-ratio:1440/900; border:1px dashed var(--line); border-radius:3px; color:var(--ink3); font-size:12px; }}
.dim td[data-tells="0"] {{ opacity:.2; }}
dialog {{ border:0; padding:0; width:min(1200px, 94vw); background:var(--card); color:var(--ink); border-radius:6px; }}
dialog::backdrop {{ background:rgba(0,0,0,.72); }}
dialog img {{ display:block; width:100%; height:auto; }}
.dbar {{ display:flex; flex-wrap:wrap; gap:8px 16px; align-items:center; padding:12px 16px; font-size:14px; }}
.dbar .t {{ font-weight:500; margin-right:auto; }}
.dbar button {{ font:inherit; color:var(--ink); background:none; border:1px solid var(--line); border-radius:4px; padding:5px 10px; cursor:pointer; }}
.dbar button[aria-pressed="true"] {{ border-color:var(--ink2); background:var(--soft); }}
.dmeta {{ padding:0 16px 14px; font-size:13px; color:var(--ink2); }}
</style></head>
<body>
<header>
<a href="./">← Findings and method</a>
<h1>Every page</h1>
<p class="lede">Each row is one website brief and each column one set of design instructions. Thumbnails show the first of three attempts; click one to see it full size and flip through all three. Hover a brief's name to read it.{note}</p>
<div class="filters" role="toolbar" aria-label="Filter"><button type="button" data-f="all" aria-pressed="true">All briefs</button>{filters}<button type="button" id="dim" aria-pressed="false">Fade pages with no giveaways</button></div>
</header>
<div class="wrap"><table><thead><tr><th scope="col">Brief</th>{head}</tr></thead><tbody>
{''.join(rows)}
</tbody></table></div>
<dialog id="dlg"><img id="dimg" alt=""><div class="dbar"><span class="t" id="dt"></span><span id="dseeds"></span><a id="dopen" href="#" target="_blank" rel="noopener">Open the page</a><button type="button" id="dclose">Close</button></div><div class="dmeta" id="dmeta"></div></dialog>
<script>
const rows=[...document.querySelectorAll('tbody tr')];
document.querySelectorAll('.filters button[data-f]').forEach(b=>b.addEventListener('click',()=>{{
 document.querySelectorAll('.filters button[data-f]').forEach(x=>x.setAttribute('aria-pressed',x===b));
 rows.forEach(r=>r.hidden=!(b.dataset.f==='all'||r.dataset.type===b.dataset.f));}}));
const dim=document.getElementById('dim');dim.addEventListener('click',()=>{{const on=dim.getAttribute('aria-pressed')!=='true';dim.setAttribute('aria-pressed',on);document.querySelector('table').classList.toggle('dim',on);}});
const dlg=document.getElementById('dlg');let cur=null,ci=0;
function show(i){{const s=cur.seeds[i];ci=i;document.getElementById('dimg').src=s.img;document.getElementById('dopen').href=s.href;
 document.getElementById('dmeta').textContent='Heading font: '+s.font+' · Brief requirements met: '+(s.met==null?'n/a':s.met+' of '+s.of)+' · Giveaways: '+(s.tells.length?s.tells.join(', '):'none');
 document.querySelectorAll('#dseeds button').forEach(b=>b.setAttribute('aria-pressed',+b.dataset.i===i));}}
document.querySelectorAll('.th').forEach(t=>t.addEventListener('click',()=>{{cur={{seeds:JSON.parse(t.dataset.seeds)}};
 document.getElementById('dt').textContent=t.dataset.title+' · '+t.dataset.arm;document.getElementById('dimg').alt=t.dataset.title+', '+t.dataset.arm;
 document.getElementById('dseeds').innerHTML=cur.seeds.length>1?cur.seeds.map((_,i)=>'<button type="button" data-i="'+i+'">Attempt '+(i+1)+'</button>').join(' '):'';
 document.querySelectorAll('#dseeds button').forEach(b=>b.addEventListener('click',()=>show(+b.dataset.i)));show(0);dlg.showModal();}}));
document.getElementById('dclose').addEventListener('click',()=>dlg.close());
dlg.addEventListener('click',ev=>{{if(ev.target===dlg)dlg.close();}});
document.addEventListener('keydown',ev=>{{if(!dlg.open||!cur)return;const n=cur.seeds.length;
 if(ev.key==='ArrowRight')show((ci+1)%n);if(ev.key==='ArrowLeft')show((ci+n-1)%n);}});
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
