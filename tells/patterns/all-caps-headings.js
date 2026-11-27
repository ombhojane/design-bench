// Tracked all-caps "eyebrow" labels — small uppercase, letter-spaced section
// kickers (THE PROBLEM · HOW IT WORKS · NOW IN BETA). Nav links, buttons and
// table headers in caps are ordinary typography; a site set consistently in
// caps is a style. The tell is the small scattered section label.
// OB-Design-Slop original (v2: rich per-element signal, score-side filters);
// id matches design-slop-cop's labeled `all_caps_headings`.

export default {
  id: 'all_caps_headings',
  label: 'Tracked all-caps eyebrow labels',
  shortLabel: 'ALL-CAPS labels',
  description: 'Small uppercase, letter-spaced section labels used as a recurring device.',
  category: 'fonts',
  thresholds: {
    minCount: 3,
    minLetterSpacingPx: 0.5,
    maxFontSizePx: 15,     // eyebrow labels are small; big caps headlines are a different choice
    minChars: 3,
    maxChars: 40,
    maxTotal: 40           // more than this = site-wide caps style, not scattered labels
  },

  extract: function (ctx) {
    const { visible, thresholds: T } = ctx;
    const els = [];
    for (const el of visible) {
      if (els.length >= 220) break;
      const cs = getComputedStyle(el);
      if (cs.textTransform !== 'uppercase') continue;
      const ownText = Array.from(el.childNodes)
        .filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim();
      if (ownText.length < 2) continue;
      const nav = !!el.closest('nav, header, footer, button, a, th, table, select, [role="navigation"]');
      els.push({
        t: el.tagName,
        fs: parseFloat(cs.fontSize) || 0,
        ls: parseFloat(cs.letterSpacing) || 0,
        n: ownText.length,
        nav,
        s: ownText.slice(0, 30)
      });
    }
    return { total: els.length, els };
  },

  score: function (signal, T) {
    if (!signal || !signal.els) return { triggered: false };
    // A site saturated in caps is a deliberate style, not the scattered-label tell.
    if (signal.total > T.maxTotal) return { triggered: false };
    const eyebrows = signal.els.filter(e =>
      !e.nav &&
      e.fs > 0 && e.fs <= T.maxFontSizePx &&
      e.ls >= T.minLetterSpacingPx &&
      e.n >= T.minChars && e.n <= T.maxChars);
    if (eyebrows.length < T.minCount) return { triggered: false };
    return { triggered: true, evidence: {
      count: eyebrows.length, total: signal.total,
      samples: eyebrows.slice(0, 5).map(e => e.s) } };
  }
};
