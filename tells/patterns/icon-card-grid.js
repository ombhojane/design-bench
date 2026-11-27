// Icon card grid — three or more sibling cards, each leading with a small
// icon above a heading and a short blurb. The canonical AI feature section.
// OB-Design-Slop original; id matches design-slop-cop's labeled
// `icon_card_grid` so existing labels validate it.

export default {
  id: 'icon_card_grid',
  label: 'Icon feature-card grid',
  shortLabel: 'Icon card grid',
  description: 'A grid of 3+ matching cards, each with an icon, heading and blurb.',
  category: 'layout',
  thresholds: {
    minCards: 3,
    minCardRadius: 6,     // px — card look: rounded or elevated or own bg
    maxIconSize: 72       // px — "icon", not an illustration
  },

  extract: function (ctx) {
    const { visible, thresholds: T, parseColor, effectiveBg } = ctx;
    const visSet = new Set(visible);

    function isIconish(el) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) return false;
      if (r.width > T.maxIconSize || r.height > T.maxIconSize) return false;
      const tag = el.tagName;
      if (tag === 'SVG' || tag === 'svg') return true;
      if (tag === 'IMG') return true;
      if (tag === 'I' || tag === 'SPAN') {
        const cls = ((el.className || '') + '').toLowerCase();
        if (/icon|lucide|feather|fa-/.test(cls)) return true;
      }
      return false;
    }

    function cardLike(el) {
      const cs = getComputedStyle(el);
      const radius = parseFloat(cs.borderRadius) || 0;
      const hasShadow = cs.boxShadow && cs.boxShadow !== 'none';
      const bg = parseColor(cs.backgroundColor);
      const ownBg = bg && bg.a > 0.02;
      const hasBorder = parseFloat(cs.borderWidth) > 0 && cs.borderStyle !== 'none';
      return (radius >= T.minCardRadius && (hasShadow || ownBg || hasBorder)) ||
             (hasShadow && ownBg);
    }

    function isCard(el) {
      if (!cardLike(el)) return false;
      const r = el.getBoundingClientRect();
      if (r.width < 120 || r.height < 80 || r.width > 700) return false;
      const icon = Array.from(el.querySelectorAll('svg, img, i, span')).some(isIconish);
      if (!icon) return false;
      const heading = el.querySelector('h2,h3,h4,h5,strong,b,[class*="title"]');
      if (!heading) return false;
      const text = (el.textContent || '').trim();
      return text.length >= 15 && text.length <= 600;
    }

    let grids = 0;
    let maxCards = 0;
    let sample = null;
    const counted = new Set();
    for (const parent of visible) {
      const kids = Array.from(parent.children).filter(k => visSet.has(k));
      if (kids.length < T.minCards) continue;
      const cards = kids.filter(isCard);
      if (cards.length >= T.minCards) {
        if (cards.some(c => counted.has(c))) continue;  // nested duplicate
        cards.forEach(c => counted.add(c));
        grids++;
        if (cards.length > maxCards) {
          maxCards = cards.length;
          const h = cards[0].querySelector('h2,h3,h4,h5,strong,b');
          sample = h ? (h.textContent || '').trim().slice(0, 50) : null;
        }
      }
    }
    return { grids, maxCards, sample };
  },

  score: function (signal, T) {
    if (!signal || signal.grids < 1) return { triggered: false };
    return { triggered: true, evidence: { grids: signal.grids, maxCards: signal.maxCards, sample: signal.sample } };
  }
};
