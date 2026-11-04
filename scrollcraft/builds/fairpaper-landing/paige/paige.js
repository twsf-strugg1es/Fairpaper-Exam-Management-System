// Paige, Fairpaper's mascot: a folded exam sheet with answer bubbles and a pencil.
// One source for every pose. Works as a browser script (window.Paige) and in Node (module.exports),
// so the landing page draws her inline and build.mjs writes the same poses as SVG files for the app.
// When an illustrator delivers final artwork, replace the files build.mjs writes; the names stay.
(function (root) {
  const G = '#0B6E4F', INK = '#161614', CREAM = '#F5EFE2', FOLD = '#E7DDC8', RED = '#B3261E', YEL = '#F2B84B', PINK = '#F28B82';
  const SW = 3.2; // one line weight for the whole character

  const limb = (d, cls = '') => `<path class="${cls}" d="${d}" fill="none" stroke="${INK}" stroke-width="${SW}" stroke-linecap="round" stroke-linejoin="round"/>`;
  const hand = (x, y) => `<circle cx="${x}" cy="${y}" r="4.2" fill="${CREAM}" stroke="${INK}" stroke-width="2.4"/>`;
  const pencil = (x, y, rot, s = 1) => `<g transform="translate(${x} ${y}) rotate(${rot}) scale(${s})">
    <rect x="-4" y="-30" width="8" height="38" rx="2" fill="${YEL}" stroke="${INK}" stroke-width="2"/>
    <path d="M-4 -24 h8" stroke="${INK}" stroke-width="1.4" opacity="0.4"/>
    <rect x="-4" y="-36" width="8" height="7" rx="2" fill="${PINK}" stroke="${INK}" stroke-width="2"/>
    <path d="M-4 8 L0 18 L4 8 Z" fill="#EAD7B1" stroke="${INK}" stroke-width="2" stroke-linejoin="round"/>
    <path d="M-1.4 14.4 L0 18 L1.4 14.4 Z" fill="${INK}"/></g>`;
  const eyes = (mood, look = [0, 0]) => {
    const [lx, ly] = look;
    if (mood === 'happy') return `<path d="M60 70 q6 -7 12 0 M88 70 q6 -7 12 0" fill="none" stroke="${INK}" stroke-width="3" stroke-linecap="round"/>`;
    if (mood === 'sleep') return `<path d="M60 72 q6 5 12 0 M88 72 q6 5 12 0" fill="none" stroke="${INK}" stroke-width="3" stroke-linecap="round"/>`;
    return `<g class="paige-lids"><ellipse cx="66" cy="70" rx="6.2" ry="7.4" fill="#fff" stroke="${INK}" stroke-width="2.2"/><ellipse cx="94" cy="70" rx="6.2" ry="7.4" fill="#fff" stroke="${INK}" stroke-width="2.2"/>
      <g class="paige-pupils" transform="translate(${lx} ${ly})"><circle cx="66" cy="71" r="3.6" fill="${INK}"/><circle cx="94" cy="71" r="3.6" fill="${INK}"/>
      <circle cx="67.2" cy="69.6" r="1.2" fill="#fff"/><circle cx="95.2" cy="69.6" r="1.2" fill="#fff"/></g></g>`;
  };
  const brows = (kind) => ({
    worried: `<path d="M58 58 q7 -4 13 1 M102 58 q-7 -4 -13 1" fill="none" stroke="${INK}" stroke-width="2.6" stroke-linecap="round"/>`,
    up: `<path d="M59 57 q6 -5 12 -1 M89 56 q6 -5 12 -1" fill="none" stroke="${INK}" stroke-width="2.4" stroke-linecap="round"/>`,
  }[kind] || '');
  const mouth = (kind) => ({
    smile: `<path d="M73 84 q7 7 14 0" fill="none" stroke="${INK}" stroke-width="3" stroke-linecap="round"/>`,
    grin: `<path d="M70 82 q10 13 20 0 z" fill="${INK}" stroke="${INK}" stroke-width="2" stroke-linejoin="round"/><path d="M75 88 q5 3 10 0" fill="${PINK}"/>`,
    flat: `<path d="M75 85 h9" stroke="${INK}" stroke-width="3" stroke-linecap="round"/>`,
    o: `<ellipse cx="80" cy="86" rx="3.4" ry="4.4" fill="${INK}"/>`,
    side: `<path d="M74 85 q6 3 11 -2" fill="none" stroke="${INK}" stroke-width="3" stroke-linecap="round"/>`,
  }[kind]);
  const cheeks = `<ellipse cx="57" cy="80" rx="5.4" ry="3.2" fill="${PINK}" opacity="0.5"/><ellipse cx="103" cy="80" rx="5.4" ry="3.2" fill="${PINK}" opacity="0.5"/>`;
  const sparkle = (x, y, s, c = G) => `<path class="paige-spark" d="M${x} ${y - s} Q${x + s * 0.18} ${y - s * 0.18} ${x + s} ${y} Q${x + s * 0.18} ${y + s * 0.18} ${x} ${y + s} Q${x - s * 0.18} ${y + s * 0.18} ${x - s} ${y} Q${x - s * 0.18} ${y - s * 0.18} ${x} ${y - s} Z" fill="${c}"/>`;
  const warnSign = (x, y) => `<g transform="translate(${x} ${y})"><path d="M11 0 L22 19 H0 Z" fill="${RED}" stroke="${RED}" stroke-width="2" stroke-linejoin="round"/><path d="M11 6.5 v6" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/><circle cx="11" cy="15.6" r="1.4" fill="#fff"/></g>`;

  // `light` adds a pale outline to the legs and arms so they still show on dark backgrounds
  const body = ({ tick = false, tilt = 0, inner = '' } = {}) => `
    <g class="paige-body" transform="rotate(${tilt} 80 132)">
      <path d="M64 128 v12 M96 128 v12" stroke="${INK}" stroke-width="${SW}" stroke-linecap="round"/>
      <ellipse cx="60" cy="142" rx="7" ry="3.6" fill="${INK}"/><ellipse cx="100" cy="142" rx="7" ry="3.6" fill="${INK}"/>
      <path d="M42 32 Q42 26 48 26 H102 L120 44 V124 Q120 130 114 130 H48 Q42 130 42 124 Z" fill="${CREAM}" stroke="${INK}" stroke-width="${SW}" stroke-linejoin="round"/>
      <path d="M102 26 V40 Q102 44 106 44 H120" fill="${FOLD}" stroke="${INK}" stroke-width="${SW}" stroke-linejoin="round"/>
      <circle cx="54" cy="38" r="3.8" fill="none" stroke="${G}" stroke-width="2"/><circle cx="65" cy="38" r="3.8" fill="${G}"/>
      <path d="M54 102 H106 M54 111 H96 M54 120 H102" stroke="${INK}" stroke-width="1.8" stroke-linecap="round" opacity="0.16"/>
      ${tick ? `<path d="M57 107 l7 7 l14 -15" stroke="${G}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" fill="none"/>` : ''}
      ${inner}
    </g>`;
  const face = (e, m, b = '', look) => `${eyes(e, look)}${brows(b)}${mouth(m)}${cheeks}`;
  const shadow = `<ellipse class="paige-shadow" cx="80" cy="146" rx="40" ry="5" fill="${INK}" opacity="0.07"/>`;

  const POSES = {
    hello: () => `${body({ inner: face('open', 'smile') })}
      <g class="paige-wave">${limb('M43 92 Q26 84 24 64')}${hand(24, 62)}</g>
      ${limb('M119 94 Q130 100 130 112')}${pencil(132, 116, 18)}`,
    submitted: () => `${sparkle(24, 30, 8)}${sparkle(140, 26, 7, YEL)}${sparkle(136, 76, 5)}${sparkle(22, 78, 5, YEL)}
      ${body({ tick: true, inner: face('happy', 'grin') })}
      ${limb('M43 84 Q28 66 30 44')}${hand(30, 42)}${limb('M119 84 Q134 66 132 44')}${pencil(134, 40, 24)}`,
    thinking: () => `<text x="120" y="22" font-family="Geist, system-ui, sans-serif" font-weight="700" font-size="22" fill="${G}">?</text>
      <circle cx="112" cy="34" r="2.4" fill="${G}" opacity="0.5"/><circle cx="118" cy="28" r="3" fill="${G}" opacity="0.7"/>
      ${body({ inner: face('open', 'side', 'up', [-2.4, -2.6]) })}
      ${limb('M43 98 Q32 104 32 116')}${hand(32, 118)}${limb('M119 100 Q134 98 134 84')}${pencil(138, 78, 14, 0.9)}`,
    careful: () => `${warnSign(124, 6)}
      ${body({ inner: face('open', 'o', 'worried') })}
      ${limb('M43 90 Q30 84 28 70')}${hand(28, 68)}${limb('M119 90 Q132 84 134 70')}${hand(134, 68)}`,
    marking: () => `${body({ tilt: -4, inner: face('open', 'side', 'up', [2, 2.6]) })}
      <g transform="translate(110 104) rotate(6)"><rect width="34" height="40" rx="4" fill="#fff" stroke="${INK}" stroke-width="2.4"/>
        <path d="M7 12 h20 M7 20 h14 M7 28 h18" stroke="${INK}" stroke-width="1.6" opacity="0.25" stroke-linecap="round"/>
        <path d="M8 31 l4 4 l9 -9" stroke="${G}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" fill="none"/></g>
      ${limb('M43 96 Q32 102 30 114')}${hand(30, 116)}${limb('M117 96 Q122 104 126 112')}${pencil(128, 118, 30, 0.85)}`,
    sleeping: () => `<text class="paige-z" x="114" y="30" font-family="Geist, system-ui, sans-serif" font-weight="700" font-size="16" fill="${G}" opacity="0.55">z</text><text class="paige-z" x="126" y="18" font-family="Geist, system-ui, sans-serif" font-weight="700" font-size="21" fill="${G}">z</text>
      ${body({ tilt: 6, inner: face('sleep', 'flat') })}
      ${limb('M45 104 Q36 110 38 120')}${hand(38, 122)}${limb('M119 104 Q128 112 126 122')}${hand(126, 124)}`,
    pointing: () => `${body({ tilt: -3, inner: face('open', 'smile', 'up', [3, 0]) })}
      ${limb('M119 88 Q136 86 148 80')}${hand(149, 79)}${limb('M43 96 Q34 104 36 116')}${pencil(36, 122, -16, 0.85)}`,
    join: () => `${body({ inner: face('open', 'grin') })}
      <g transform="translate(4 2) rotate(-8)"><rect width="56" height="30" rx="7" fill="${G}" stroke="${INK}" stroke-width="2.4"/>
        <text x="28" y="20" text-anchor="middle" font-family="Geist, system-ui, sans-serif" font-weight="700" font-size="13" fill="#fff">Join!</text></g>
      ${limb('M43 88 Q30 62 30 36')}${hand(30, 34)}${limb('M119 92 Q130 98 130 110')}${hand(130, 112)}`,
  };

  // Idle motion that travels with the SVG file: a gentle bob, a blink, the wave. Off for reduced motion.
  const MOTION = `<style>@media (prefers-reduced-motion: no-preference){
    .paige-body{animation:paige-bob 3.2s ease-in-out infinite}
    .paige-lids{animation:paige-blink 4.6s infinite;transform-box:fill-box;transform-origin:center}
    .paige-wave{animation:paige-wave 1.4s ease-in-out infinite;transform-origin:43px 92px}
    .paige-spark{animation:paige-twinkle 1.8s ease-in-out infinite;transform-box:fill-box;transform-origin:center}
    .paige-z{animation:paige-float 2.6s ease-in-out infinite}
    @keyframes paige-bob{50%{transform:translateY(-4px)}}
    @keyframes paige-blink{0%,92%,100%{transform:scaleY(1)}95%{transform:scaleY(.1)}}
    @keyframes paige-wave{50%{transform:rotate(-14deg)}}
    @keyframes paige-twinkle{50%{transform:scale(.6);opacity:.6}}
    @keyframes paige-float{50%{transform:translateY(-3px);opacity:.4}}}</style>`;

  const svg = (pose, { motion = true, title } = {}) => {
    if (!POSES[pose]) throw new Error(`Paige has no pose "${pose}"`);
    const label = title ? `role="img" aria-label="${title}"` : 'aria-hidden="true"';
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160" class="paige paige--${pose}" ${label}>${motion ? MOTION : ''}${shadow}${POSES[pose]()}</svg>`;
  };

  const api = { svg, poses: Object.keys(POSES) };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Paige = api;
})(typeof window !== 'undefined' ? window : globalThis);
