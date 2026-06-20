// Criticality color ramp. Low edges sit dim and recede into the dark basemap; critical
// edges climb in brightness and heat so the eye lands on them first. Stops are tuned for a
// dark map specifically — a ramp that works on white would wash out here.
const Palette = (() => {
  const stops = [
    [0.00, [26, 64, 72]],    // deep teal, almost background
    [0.30, [47, 143, 134]],  // muted teal
    [0.55, [216, 177, 74]],  // amber
    [0.78, [242, 116, 45]],  // orange
    [1.00, [255, 77, 94]],   // hot coral — single points of failure
  ];

  function lerp(a, b, f) { return a + (b - a) * f; }

  function color(t) {
    t = Math.max(0, Math.min(1, t));
    for (let i = 1; i < stops.length; i++) {
      if (t <= stops[i][0]) {
        const [t0, c0] = stops[i - 1];
        const [t1, c1] = stops[i];
        const f = (t - t0) / (t1 - t0 || 1);
        const c = [0, 1, 2].map(k => Math.round(lerp(c0[k], c1[k], f)));
        return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
      }
    }
    return `rgb(${stops.at(-1)[1].join(',')})`;
  }

  // CSS gradient string for the legend bar — same stops, so legend and map never disagree.
  function cssGradient() {
    const parts = stops.map(([t, c]) => `rgb(${c.join(',')}) ${(t * 100).toFixed(0)}%`);
    return `linear-gradient(90deg, ${parts.join(', ')})`;
  }

  return { color, cssGradient };
})();
