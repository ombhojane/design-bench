// shadcn/ui left on factory settings — the design-token names, default
// radius variable and utility-class pairs that ship with `npx shadcn init`.
// Using shadcn isn't slop; shipping its unthemed defaults is the tell.
// OB-Design-Slop original; id matches design-slop-cop's labeled
// `shadcn_signature` so existing labels validate it.

export default {
  id: 'shadcn_signature',
  label: 'shadcn/ui factory defaults',
  shortLabel: 'shadcn defaults',
  description: 'shadcn/ui token names and default utility pairs left unthemed.',
  category: 'layout',
  thresholds: {
    minTokens: 5,      // shadcn-convention CSS custom properties on :root
    minClassHits: 2,   // signature utility-class pairs in the DOM
    minDataSlots: 4    // data-slot attributes (newer shadcn components)
  },

  extract: function (ctx) {
    const rootCs = getComputedStyle(document.documentElement);
    const TOKENS = ['--background', '--foreground', '--card', '--card-foreground',
                    '--primary', '--primary-foreground', '--secondary', '--muted',
                    '--muted-foreground', '--accent', '--destructive', '--border',
                    '--input', '--ring', '--radius'];
    const found = TOKENS.filter(t => (rootCs.getPropertyValue(t) || '').trim() !== '');

    const PAIRS = ['bg-background', 'text-foreground', 'bg-card', 'text-card-foreground',
                   'text-muted-foreground', 'bg-primary text-primary-foreground',
                   'ring-offset-background', 'bg-muted', 'border-border'];
    let classHits = 0;
    const hitSamples = [];
    const html = document.body ? document.body.innerHTML.slice(0, 400000) : '';
    for (const p of PAIRS) {
      if (html.indexOf(p) !== -1) { classHits++; if (hitSamples.length < 4) hitSamples.push(p); }
    }
    const dataSlots = document.querySelectorAll('[data-slot]').length;
    const radiusVar = (rootCs.getPropertyValue('--radius') || '').trim();

    return { tokenCount: found.length, tokens: found.slice(0, 8), classHits,
             hitSamples, dataSlots, radiusVar };
  },

  score: function (signal, T) {
    if (!signal) return { triggered: false };
    const hits = (signal.tokenCount >= T.minTokens ? 1 : 0) +
                 (signal.classHits >= T.minClassHits ? 1 : 0) +
                 (signal.dataSlots >= T.minDataSlots ? 1 : 0);
    if (hits < 1) return { triggered: false };
    // Token names alone can be any hand-rolled theme; require either the
    // utility-class pairs, data-slots, or default radius alongside tokens.
    if (hits === 1 && signal.tokenCount >= T.minTokens &&
        signal.classHits === 0 && signal.dataSlots === 0 &&
        signal.radiusVar !== '0.5rem' && signal.radiusVar !== '0.625rem') {
      return { triggered: false };
    }
    return { triggered: true, evidence: {
      tokenCount: signal.tokenCount, classHits: signal.classHits,
      hitSamples: signal.hitSamples, dataSlots: signal.dataSlots,
      radiusVar: signal.radiusVar || null } };
  }
};
