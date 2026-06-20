// Orchestration: holds the dashboard state, talks to the API, and drives MapView /
// RobustChart / the inspector. Kept procedural on purpose — there's one screen and one
// data flow, so a framework would be ceremony with no payoff (see plan §10).

const state = {
  source: "sample:koramangala",
  weight: "length",
  measure: "score",
  showArtic: true,
  analysis: null,
  edgeIndex: new Map(),     // edgeKey -> edge properties
  selected: null,
};

const $ = sel => document.querySelector(sel);
const loading = $("#loading");

document.addEventListener("DOMContentLoaded", init);

async function init() {
  MapView.init("map");
  MapView.setEdgeClick(selectEdge);
  $("#legendBar").style.background = Palette.cssGradient();

  wireControls();
  await populateSources();
  await checkHealth();
  await load();
}

// ── data flow ────────────────────────────────────────────────────────────
async function load(fit = true) {
  showLoading(true);
  try {
    state.analysis = await Api.criticality(state.source, state.weight);
    indexEdges();
    normalize();
    draw(fit);
    MapView.clearCut();                 // a new network invalidates any drawn overlays
    MapView.clearFlood();
    $("#flowResult").hidden = true;
    $("#floodStat").hidden = true;
    $("#restoreList").innerHTML = "";
    renderStats();
    renderRanklist();
    $("#placeName").textContent = prettySource(state.source);
    await loadRobustness();
  } catch (err) {
    $("#placeName").textContent = "error";
    console.error(err);
    alert(`Could not load network:\n${err.message}`);
  } finally {
    showLoading(false);
  }
}

function draw(fit) {
  const features = state.analysis.edges.features;
  MapView.drawEdges(features, state.measure, fit);
  MapView.drawStructure(features, state.analysis.articulation_points.features, state.showArtic);
}

function indexEdges() {
  state.edgeIndex.clear();
  for (const f of state.analysis.edges.features) {
    state.edgeIndex.set(MapView.key(f.properties.u, f.properties.v), f.properties);
  }
}

// Per-measure min-max so every measure gets the full colour range. Score is already 0-100,
// so it's just /100 — a fixed scale, which keeps the legend meaningful across cities.
function normalize() {
  const features = state.analysis.edges.features;
  const measures = ["betweenness", "current_flow", "impact"];
  const range = {};
  for (const m of measures) {
    const vals = features.map(f => f.properties[m] ?? 0);
    range[m] = [Math.min(...vals), Math.max(...vals)];
  }
  for (const f of features) {
    const p = f.properties;
    p._norm = { score: (p.score ?? 0) / 100 };
    for (const m of measures) {
      const [lo, hi] = range[m];
      p._norm[m] = hi > lo ? ((p[m] ?? 0) - lo) / (hi - lo) : 0;
    }
  }
}

async function loadRobustness() {
  try {
    const data = await Api.robustness(state.source, state.weight, 16);
    RobustChart.render("robustChart", data);
    $("#aucTargeted").textContent = data.targeted.auc.toFixed(3);
    $("#aucRandom").textContent = data.random.auc.toFixed(3);
  } catch (err) {
    console.warn("robustness unavailable", err);
  }
}

// ── inspector rendering ──────────────────────────────────────────────────
function renderStats() {
  const s = state.analysis.summary;
  const tiles = [
    ["nodes", s.nodes], ["segments", s.edges],
    ["components", s.connected_components],
    ["articulation", s.articulation_points, s.articulation_points > 0],
    ["bridges", s.bridges, s.bridges > 0],
    ["largest CC", s.largest_component],
  ];
  $("#stats").innerHTML = tiles.map(([lbl, num, warn]) => `
    <div class="stat">
      <div class="stat__num ${warn ? "is-warn" : ""}">${num}</div>
      <div class="stat__lbl">${lbl}</div>
    </div>`).join("");
}

function renderRanklist() {
  const list = $("#ranklist");
  list.innerHTML = state.analysis.summary.top_segments.map(t => `
    <li data-key="${MapView.key(t.u, t.v)}">
      <span class="seg-id">${t.u}–${t.v}</span>
      ${t.is_bridge ? '<span class="badge-bridge">bridge</span>' : ""}
      <span class="seg-score">${t.score.toFixed(0)}</span>
    </li>`).join("");
  list.querySelectorAll("li").forEach(li =>
    li.addEventListener("click", () => {
      const p = state.edgeIndex.get(li.dataset.key);
      if (p) selectEdge(p);
    }));
}

function selectEdge(props) {
  state.selected = props;
  MapView.highlight(MapView.key(props.u, props.v));
  $("#selected").hidden = false;
  $("#impactResult").hidden = true;

  const c = props.components || {};
  const bar = (lbl, v) => `
    <div class="bar-row"><span class="lbl">${lbl}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${(v * 100).toFixed(0)}%"></div></div></div>`;

  $("#selectedBody").innerHTML = `
    <div class="kv"><span>segment</span><span>${props.u}–${props.v}</span></div>
    <div class="kv"><span>class</span><span>${props.highway || "—"}</span></div>
    <div class="kv"><span>length</span><span>${props.length_m} m</span></div>
    <div class="kv"><span>score</span><span>${props.score?.toFixed(1)} ${props.is_bridge ? "· bridge" : ""}</span></div>
    <div class="bars">
      ${bar("between", c.betweenness ?? 0)}
      ${bar("curr-flow", c.current_flow ?? 0)}
      ${bar("impact", c.impact ?? 0)}
    </div>`;
}

let floodTimer = null;

function onFloodInput(e) {
  const level = parseFloat(e.target.value);
  $("#floodLabel").textContent = level.toFixed(1) + " m";
  clearTimeout(floodTimer);
  floodTimer = setTimeout(() => runFlood(level), 220);   // debounce the slider drag
}

async function runFlood(level) {
  try {
    const r = await Api.flood(state.source, level, state.weight);
    MapView.clearCut();                          // flood and bottleneck overlays are mutually exclusive
    $("#flowResult").hidden = true;
    MapView.drawFlood(r.submerged, r.lost_access, r.hospitals, r.restoration);

    $("#floodStat").hidden = false;
    $("#floodLost").textContent = `${r.lost_access_count} junctions (${Math.round(r.lost_access_fraction * 100)}%)`;
    $("#floodSubmerged").textContent = r.submerged_count;
    $("#floodAccess").textContent = `${r.with_access_after}/${r.nodes_total}`;
    renderRestore(r.restoration);
  } catch (err) {
    console.warn("flood failed", err);
  }
}

function renderRestore(restoration) {
  const feats = restoration.features || [];
  $("#restoreList").innerHTML = feats.length
    ? `<div class="restore__head">Clear first → restore access</div>` + feats.map((f, i) =>
        `<div class="restore__row">
           <span class="restore__rank">${i + 1}</span>
           <span class="restore__seg">${f.properties.u}–${f.properties.v}</span>
           <span class="restore__gain">+${f.properties.restores}</span>
         </div>`).join("")
    : "";
}

async function runBottleneck() {
  const origin = $("#origin").value;
  const dest = $("#dest").value;
  const btn = $("#runFlow");
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = "computing…";
  try {
    const r = await Api.bottleneck(state.source, origin, dest, state.weight);
    MapView.clearFlood();                        // clear the flood overlay when showing a cut
    $("#floodStat").hidden = true;
    MapView.drawCut(r.min_cut, r.origin_nodes, r.dest_nodes);
    $("#flowResult").hidden = false;
    $("#maxFlow").textContent = Math.round(r.max_flow).toLocaleString();
    $("#cutSize").textContent = r.cut_size;
  } catch (err) {
    alert(`Bottleneck analysis failed:\n${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = label;
  }
}

async function simulate() {
  if (!state.selected) return;
  const { u, v } = state.selected;
  const box = $("#impactResult");
  box.hidden = false;
  box.innerHTML = '<span class="mono">computing…</span>';
  try {
    const r = await Api.impact(u, v, state.source, state.weight);
    const pct = (r.relative_drop * 100).toFixed(1);
    box.innerHTML = `Removing this segment drops network efficiency by
      <b>${pct}%</b>.` + (r.fragmented
        ? ` It <b>fragments</b> the network: ${r.lcc_before - r.lcc_after} nodes are cut off
            (${r.newly_disconnected_pairs} OD pairs lose their route).`
        : ` The network stays connected; traffic reroutes.`);
  } catch (err) {
    box.innerHTML = `<span class="mono">error: ${err.message}</span>`;
  }
}

// ── controls ───────────────────────────────────────────────────────────────
function wireControls() {
  $("#source").addEventListener("change", e => { state.source = e.target.value; load(true); });

  $("#weight").addEventListener("click", e => {
    const btn = e.target.closest("[data-weight]"); if (!btn) return;
    setActive("#weight .seg__btn", btn);
    state.weight = btn.dataset.weight; load(false);
  });

  $("#measure").addEventListener("click", e => {
    const btn = e.target.closest("[data-measure]"); if (!btn) return;
    setActive("#measure .opt", btn);
    state.measure = btn.dataset.measure;
    draw(false);                       // restyle only — don't refit the viewport
  });

  $("#toggleArtic").addEventListener("change", e => {
    state.showArtic = e.target.checked; draw(false);
  });

  $("#simulate").addEventListener("click", simulate);
  $("#runRobust").addEventListener("click", loadRobustness);
  $("#runFlow").addEventListener("click", runBottleneck);
  $("#floodLevel").addEventListener("input", onFloodInput);
}

function setActive(selector, active) {
  document.querySelectorAll(selector).forEach(el => el.classList.remove("is-active"));
  active.classList.add("is-active");
}

// ── misc ─────────────────────────────────────────────────────────────────
async function populateSources() {
  const sel = $("#source");
  try {
    const { samples } = await Api.samples();
    sel.innerHTML = samples.map(n =>
      `<option value="sample:${n}">${titleCase(n)} (sample)</option>`).join("");
    sel.value = state.source;
  } catch {
    sel.innerHTML = `<option value="${state.source}">${prettySource(state.source)}</option>`;
  }
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

function showLoading(on) { loading.classList.toggle("is-hidden", !on); }
function titleCase(s) { return s.replace(/(^|[\s-])\w/g, m => m.toUpperCase()); }
function prettySource(src) {
  const [, val] = src.split(":");
  return titleCase((val || src).replace(/,.*$/, ""));
}
