// Topological Repair Lab — the Tier 3 differentiator, made visible.
//
// One screen, one story: flip between the raw occlusion-damaged extraction and the repaired
// graph and watch the false breaks close, the flyover lift back onto its own grade, and the
// decoy gap stay (correctly) open — while the metrics panel shows the criticality ranking snap
// back to ground truth. Procedural on purpose, like the console: one data flow, no framework.

const state = {
  stage: "raw",
  data: null,
  layers: { occluders: true, diff: true, ghost: false },
};

const $ = sel => document.querySelector(sel);

const STAGE_COPY = {
  raw: {
    title: "Raw extraction",
    sub: "occlusion-blind · 2 false breaks · 1 false junction",
    note: "What an occlusion-blind vectorizer emits: tree canopy and building shadow each sever " +
          "a through-road into dangling dead-ends, and the flyover is fused into a 4-way that " +
          "invents a turn the concrete never allowed.",
  },
  repaired: {
    title: "Repaired topology",
    sub: "ground-truth topology recovered",
    note: "Gaps under an occluder are closed along the incident heading; the flyover is lifted " +
          "back onto its own grade; the decoy gap — no occluder over it — is deliberately left " +
          "open. No road is invented without evidence.",
  },
};

// ── Leaflet view ────────────────────────────────────────────────────────────
const RMap = (() => {
  let map, occLayer, ghostLayer, baseLayer, diffLayer, markLayer;

  function init(elId) {
    map = L.map(elId, { zoomControl: false, preferCanvas: true }).setView([12.937, 77.627], 16);
    L.control.zoom({ position: "bottomright" }).addTo(map);
    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png", {
      attribution: "© OpenStreetMap · © CARTO", subdomains: "abcd", maxZoom: 20,
    }).addTo(map);
    // bottom → top
    occLayer = L.layerGroup().addTo(map);
    ghostLayer = L.layerGroup().addTo(map);
    baseLayer = L.layerGroup().addTo(map);
    diffLayer = L.layerGroup().addTo(map);
    markLayer = L.layerGroup().addTo(map);
  }

  const lls = f => f.geometry.coordinates.map(([x, y]) => [y, x]);

  function fit(gt) {
    const pts = gt.features.flatMap(lls);
    if (pts.length) map.fitBounds(pts, { padding: [60, 60] });
  }

  function draw(data, stage, layers) {
    [occLayer, ghostLayer, baseLayer, diffLayer, markLayer].forEach(l => l.clearLayers());

    if (layers.occluders) drawOccluders(data.occluders);
    if (layers.ghost) drawGhost(data.graphs.ground_truth);

    drawBase(data.graphs[stage]);
    if (layers.diff) drawDiff(data.overlays, stage);
  }

  function drawOccluders(occluders) {
    for (const o of occluders) {
      const fill = o.type === "canopy" ? "#59c08a" : "#7e8cc4";
      L.polygon(o.polygon.map(([x, y]) => [y, x]), {
        color: fill, weight: 1, opacity: 0.5, fillColor: fill, fillOpacity: 0.16,
      }).bindTooltip(`${o.type} occluder`, { sticky: true, className: "rr-tip" }).addTo(occLayer);
    }
  }

  function drawGhost(gt) {
    for (const f of gt.features) {
      L.polyline(lls(f), { color: "#e7eef0", weight: 1, opacity: 0.18 }).addTo(ghostLayer);
    }
  }

  function drawBase(graph) {
    for (const f of graph.features) {
      const p = f.properties;
      const repaired = p.repaired, bridge = p.bridge;
      L.polyline(lls(f), {
        color: repaired ? "#36d6c3" : (bridge ? "#caa24a" : "#7aa4aa"),
        weight: repaired ? 3.5 : (bridge ? 3 : 2),
        opacity: repaired ? 0.95 : (bridge ? 0.85 : 0.45),
        lineCap: "round",
      }).addTo(baseLayer);
    }
  }

  function drawDiff(ov, stage) {
    if (stage === "raw") {
      // the gaps that *are* there: missing roads under occluders, drawn as the break
      for (const f of ov.bridged.features) {
        glow(lls(f), "#ff4d5e");
        L.polyline(lls(f), { color: "#ff4d5e", weight: 2, opacity: 0.95, dashArray: "2 7", lineCap: "round" })
          .bindTooltip(`false break · hidden by ${f.properties.occluder}`, { sticky: true, className: "rr-tip" })
          .addTo(diffLayer);
      }
      // the fused crossing that invents a turn
      for (const f of ov.splits.features) marker(f, "false-icon", "!", "false junction — invented turn");
      // the decoy: a candidate gap we'll look at but must refuse
      for (const f of ov.rejected.features) {
        L.polyline(lls(f), { color: "#879198", weight: 1.5, opacity: 0.6, dashArray: "1 6" })
          .bindTooltip("candidate gap — no occluder here", { sticky: true, className: "rr-tip" })
          .addTo(diffLayer);
      }
    } else {
      // closed gaps, lit up
      for (const f of ov.bridged.features) {
        glow(lls(f), "#36d6c3");
        L.polyline(lls(f), { color: "#36d6c3", weight: 3.5, opacity: 1, lineCap: "round" })
          .bindTooltip(`bridged · was hidden by ${f.properties.occluder}`, { sticky: true, className: "rr-tip" })
          .addTo(diffLayer);
      }
      // the flyover, lifted back onto its grade
      for (const f of ov.splits.features) marker(f, "fly-icon", "⤴", "grade separation restored");
      // the decoy, correctly left open
      for (const f of ov.rejected.features) {
        L.polyline(lls(f), { color: "#879198", weight: 1.5, opacity: 0.5, dashArray: "1 6" }).addTo(diffLayer);
        const mid = midpoint(f);
        L.marker(mid, { icon: L.divIcon({ className: "ok-icon", html: "<span>✓</span>", iconSize: [18, 18] }), interactive: false })
          .bindTooltip("correctly left open — no occluder evidence", { sticky: true, className: "rr-tip" })
          .addTo(markLayer);
      }
      // the honest crossroads we did NOT split
      for (const f of ov.kept.features) {
        const [x, y] = f.geometry.coordinates;
        L.circleMarker([y, x], { radius: 3, color: "#7aa4aa", weight: 1, fillColor: "#0a0d0e", fillOpacity: 1 })
          .bindTooltip("at-grade crossing kept — no overpass cue", { sticky: true, className: "rr-tip" })
          .addTo(markLayer);
      }
    }
  }

  function glow(latlngs, color) {
    L.polyline(latlngs, { color, weight: 9, opacity: 0.18, lineCap: "round" }).addTo(diffLayer);
  }

  function marker(f, cls, glyph, tip) {
    const [x, y] = f.geometry.coordinates;
    L.marker([y, x], { icon: L.divIcon({ className: cls, html: `<span>${glyph}</span>`, iconSize: [18, 18] }), interactive: false })
      .bindTooltip(tip, { sticky: true, className: "rr-tip" })
      .addTo(markLayer);
  }

  function midpoint(f) {
    const cs = f.geometry.coordinates;
    const a = cs[0], b = cs[cs.length - 1];
    return [(a[1] + b[1]) / 2, (a[0] + b[0]) / 2];
  }

  return { init, draw, fit };
})();

// ── controller ───────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", init);

async function init() {
  RMap.init("map");
  wire();
  await checkHealth();
  await load();
}

async function load() {
  show(true);
  try {
    state.data = await Api.repair();
    renderMetrics(state.data.metrics);
    renderLog(state.data.decisions);
    renderMapLegend();
    apply();
    RMap.fit(state.data.graphs.ground_truth);
  } catch (err) {
    $("#stageTitle").textContent = "error";
    console.error(err);
    alert(`Could not run the repair demo:\n${err.message}`);
  } finally {
    show(false);
  }
}

function apply() {
  RMap.draw(state.data, state.stage, state.layers);
  const c = STAGE_COPY[state.stage];
  $("#stageTitle").textContent = c.title;
  $("#stageSub").textContent = c.sub;
  $("#stageNote").textContent = c.note;
}

function renderMetrics(m) {
  const f2 = x => x.toFixed(2);
  $("#rhoRaw").textContent = f2(m.spearman_raw);
  $("#rhoRep").textContent = f2(m.spearman_repaired);
  $("#valRhoRaw").textContent = f2(m.spearman_raw);
  $("#valRhoRep").textContent = f2(m.spearman_repaired);
  $("#barRhoRaw").style.width = pct(m.spearman_raw);
  $("#barRhoRep").style.width = pct(m.spearman_repaired);
  $("#aplsRaw").textContent = f2(m.apls_raw);
  $("#aplsRep").textContent = f2(m.apls_repaired);

  const c = m.counts;
  const chips = [
    { ok: true, html: `<b>${c.breaks_bridged}/${c.breaks_total}</b>&nbsp;breaks closed` },
    { ok: true, html: `flyover split · <b>${c.crossings_kept}</b>&nbsp;crossroads kept` },
    { ok: m.decoys_rejected, html: `decoy refused` },
    { ok: true, html: `precision <b>${pct(m.precision)}</b> · recall <b>${pct(m.recall)}</b>` },
  ];
  $("#verdicts").innerHTML = chips.map(ch =>
    `<span class="chip ${ch.ok ? "chip--ok" : ""}">${ch.html}</span>`).join("");
}

const VERB = { bridged: "↔", split: "×", kept: "•", rejected: "✕" };

function renderLog(decisions) {
  $("#decisionCount").textContent = `${decisions.length} examined`;
  $("#log").innerHTML = decisions.map(d => {
    const target = d.kind === "break"
      ? `${d.ends[0]}–${d.ends[1]}${d.occluder ? ` · ${d.occluder}` : ""}`
      : `junction ${d.node}`;
    return `
      <div class="log-item log-item--${d.decision}">
        <span class="tick">${VERB[d.decision] || "•"}</span>
        <div>
          <div class="log-head"><span class="verb">${d.decision}</span><span>${target}</span></div>
          <div class="log-reason">${d.reason}</div>
        </div>
      </div>`;
  }).join("");
}

function renderMapLegend() {
  const rows = [
    ["#36d6c3", "bridged gap"],
    ["#ff4d5e", "false break / junction"],
    ["#caa24a", "flyover span"],
    ["#7aa4aa", "road network"],
  ];
  $("#maplegend").innerHTML = rows.map(([c, l]) =>
    `<div class="ml-row"><span class="ml-key" style="background:${c}"></span>${l}</div>`).join("");
}

function wire() {
  $("#stage").addEventListener("click", e => {
    const btn = e.target.closest("[data-stage]"); if (!btn) return;
    document.querySelectorAll("#stage button").forEach(b => b.classList.remove("is-active"));
    btn.classList.add("is-active");
    state.stage = btn.dataset.stage;
    apply();
  });

  $("#layers").addEventListener("change", e => {
    const row = e.target.closest("[data-layer]"); if (!row) return;
    const key = row.dataset.layer;
    state.layers[key] = e.target.checked;
    row.classList.toggle("is-off", !e.target.checked);
    apply();
  });
}

async function checkHealth() {
  const el = $("#apiStatus");
  try {
    const h = await Api.health();
    el.textContent = h.osmnx ? "live · osm ready" : "live · samples";
    el.style.color = "var(--accent-2)";
  } catch {
    el.textContent = "offline";
    el.style.color = "var(--critical)";
  }
}

function show(on) { $("#loading").classList.toggle("is-hidden", !on); }
function pct(x) { return `${Math.round(Math.max(0, Math.min(1, x)) * 100)}%`; }
