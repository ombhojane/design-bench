"""Assemble the in-page detector script from vendored design-slop-cop sources.

Port of design-slop-cop's src/detector.js buildDetectorSource() (MIT, Adrian
Krebs — see tells/vendor/slopcop/ATTRIBUTION.md), with one change: the
patterns' score() functions also run IN PAGE (they are pure threshold logic),
so the Python side receives finished verdicts and needs no per-pattern port.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "tells" / "vendor" / "slopcop"
OURS = ROOT / "tells" / "patterns"
SKIP = {"_template.js", "index.js"}


def pattern_files() -> list[Path]:
    """Vendored detectors first (canonical order), then our own."""
    out = [f for f in sorted((VENDOR / "patterns").glob("*.js")) if f.name not in SKIP]
    if OURS.exists():
        out += [f for f in sorted(OURS.glob("*.js")) if f.name not in SKIP]
    return out


def _strip_exports(src: str) -> str:
    """Remove ES module `export ` prefixes so the code runs as a plain script."""
    return re.sub(r"^export\s+", "", src, flags=re.M)


def _pattern_literal(src: str) -> str:
    """Turn a pattern module into a self-contained IIFE expression.

    Pattern files may define module-scope helpers ABOVE the `export default`
    (e.g. slop-fonts.js's isTemplatedFont, centered-hero.js's GENERIC_FONTS)
    that extract()/score() reference. Keep that prelude inside a closure so
    helpers from different patterns cannot collide in the shared page scope.
    """
    idx = src.find("export default")
    if idx < 0:
        raise ValueError("no `export default` found")
    prelude = _strip_exports(src[:idx])
    body = src[idx + len("export default"):].strip().rstrip()
    if body.endswith(";"):
        body = body[:-1].rstrip()
    return "(() => {\n" + prelude + "\nreturn " + body + ";\n})()"


def build_detector_source() -> str:
    lib = VENDOR / "lib"
    helpers = "\n".join(
        _strip_exports((lib / name).read_text())
        for name in ("color.js", "visibility.js", "emoji.js", "slop-fonts.js")
    )
    patterns = [_pattern_literal(f.read_text()) for f in pattern_files()]
    patterns_js = ",\n".join(patterns)

    # In-page body below is adapted from design-slop-cop src/detector.js (MIT).
    return (
        "(() => {\n"
        + helpers
        + "\nconst PATTERNS = [\n" + patterns_js + "\n];\n"
        + """
    const colors = createColorHelpers();
    const visHelpers = createVisibilityHelpers(colors.parseColor);

    const all = Array.from(document.querySelectorAll('*'));
    const visible = all.filter(visHelpers.isVisible);
    const bodyBg = visHelpers.effectiveBg(document.body);
    const bodyLuminance = colors.relativeLuminance(bodyBg);
    const isDarkMode = bodyLuminance < 0.2;
    const h1 = document.querySelector('h1');

    const fontCharCounts = new Map();
    const headingFontChars = new Map();
    let totalTextChars = 0;
    for (const el of visible) {
      const hasText = Array.from(el.childNodes).some(n => n.nodeType === 3 && n.textContent.trim().length > 0);
      if (!hasText) continue;
      const cs = getComputedStyle(el);
      const fam = (cs.fontFamily || '').split(',')[0].trim().replace(/^['"]|['"]$/g, '');
      if (!fam) continue;
      const txt = Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim();
      const chars = txt.length;
      fontCharCounts.set(fam, (fontCharCounts.get(fam) || 0) + chars);
      totalTextChars += chars;
      if (/^H[1-3]$/.test(el.tagName)) {
        headingFontChars.set(fam, (headingFontChars.get(fam) || 0) + chars);
      }
    }
    const sortedFonts = [...fontCharCounts.entries()].sort((a, b) => b[1] - a[1]);
    const topFonts = sortedFonts.slice(0, 6).map(([name, chars]) => ({
      name, chars, pct: totalTextChars ? +(100 * chars / totalTextChars).toFixed(1) : 0
    }));
    const slopFontsDetected = sortedFonts
      .filter(([name]) => isSlopFont(name))
      .map(([name, chars]) => ({ name, chars, pct: totalTextChars ? +(100 * chars / totalTextChars).toFixed(1) : 0 }));
    const headingFont = ([...headingFontChars.entries()].sort((a, b) => b[1] - a[1])[0] || [null])[0];

    const ctxBase = {
      parseColor: colors.parseColor,
      rgbToHsl: colors.rgbToHsl,
      relativeLuminance: colors.relativeLuminance,
      contrastRatio: colors.contrastRatio,
      isPurple: colors.isPurple,
      isVisible: visHelpers.isVisible,
      effectiveBg: visHelpers.effectiveBg,
      countEmoji,
      visible,
      bodyBg,
      bodyLuminance,
      isDarkMode,
      h1,
      fonts: { topFonts, slopFontsDetected, headingFont, totalTextChars }
    };

    const signals = {};
    const verdicts = {};
    for (const p of PATTERNS) {
      const T = p.thresholds || {};
      try {
        signals[p.id] = p.extract({ ...ctxBase, thresholds: T });
      } catch (e) {
        signals[p.id] = null;
      }
      try {
        const v = signals[p.id] == null ? { triggered: false } : (p.score(signals[p.id], T, ctxBase.fonts) || { triggered: false });
        verdicts[p.id] = { id: p.id, label: p.label, category: p.category, triggered: !!v.triggered, evidence: v.evidence || null };
      } catch (e) {
        verdicts[p.id] = { id: p.id, label: p.label, category: p.category, triggered: false, error: String(e) };
      }
    }

    return {
      meta: {
        url: location.href,
        title: document.title,
        bodyBg: 'rgb(' + (bodyBg.r|0) + ',' + (bodyBg.g|0) + ',' + (bodyBg.b|0) + ')',
        bodyLuminance: +bodyLuminance.toFixed(3),
        isDarkMode,
        visibleElements: visible.length,
        textChars: totalTextChars
      },
      fonts: { topFonts, slopFontsDetected, headingFont, hasSlopFonts: slopFontsDetected.length > 0 },
      signals,
      patterns: Object.values(verdicts)
    };
  })()"""
    )


if __name__ == "__main__":
    src = build_detector_source()
    print(f"bundle: {len(src)} chars, {src.count('PATTERNS.push') or src.count('id:')} ids")
