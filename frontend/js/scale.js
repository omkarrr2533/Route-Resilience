// Scale Lab — the "how does this scale to all of India?" answer, made interactive.
//
// Unlike the console and the Repair Lab, this page talks to the *gateway* (:8080), because the
// async job API is the gateway's job, not the compute service's. Submit an approximate-
// betweenness analysis, watch the gateway stream Monte Carlo batches with ε ticking down toward
// the target, then see the estimate measured against exact Brandes — same ranking, a fraction
// of the work at scale.

const GATEWAY = localStorage.getItem("rr_gateway") || "http://localhost:8080";

const state = { source: "sample:koramangala", jobId: null, polling: false };
const $ = sel => document.querySelector(sel);

// ── gateway API ──────────────────────────────────────────────────────────────
const Api = {
  async _get(path) {
    const r = await fetch(`${GATEWAY}/api${path}`);
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  },
  health() { return this._get("/health"); },
  samples() { return this._get("/samples"); },
  job(id) { return this._get(`/jobs/${id}`); },
  criticality(source) { return this._get(`/criticality?source=${encodeURIComponent(source)}&weight=length`); },
  async submit(body) {
    const r = await fetch(`${GATEWAY}/api/jobs/approx-betweenness`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  },
};

// ── Leaflet heatmap (approx betweenness joined with geometry) ─────────────────
const Map_ = (() => {
  let map, layer;
  function init() {
    map = L.map("map", { zoomControl: false, preferCanvas: true }).setView([12.9352, 77.6245], 15);
    L.control.zoom({ position: "bottomright" }).addTo(map);
    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png", {
      attribution: "© OpenStreetMap · © CARTO", subdomains: "abcd", maxZoom: 20,
    }).addTo(map);
    layer = L.layerGroup().addTo(map);
  }
  function heatmap(features, approx) {
    layer.clearLayers();
    const vals = [...approx.values()];
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const bounds = [];
    for (const f of features) {
      const k = key(f.properties.u, f.properties.v);
      const b = approx.get(k); if (b == null) continue;
      const t = hi > lo ? (b - lo) / (hi - lo) : 0;
      const ll = f.geometry.coordinates.map(([x, y]) => [y, x]);
      bounds.push(...ll);
      L.polyline(ll, { color: Palette.color(t), weight: 2 + t * 5, opacity: 0.5 + t * 0.5, lineCap: "round" })
        .bindTooltip(`${f.properties.u}–${f.properties.v} · b̂ ${b.toFixed(3)}`, { sticky: true, className: "rr-tip" })
        .addTo(layer);
    }
    if (bounds.length) map.fitBounds(bounds, { padding: [50, 50] });
  }
  return { init, heatmap };
})();

const key = (u, v) => (u < v ? `${u}-${v}` : `${v}-${u}`);

// ── flow ──────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", init);

async function init() {
  Map_.init();
  $("#run").addEventListener("click", run);
  $("#source").addEventListener("change", e => (state.source = e.target.value));
  await checkGateway();
}

async function checkGateway() {
  // Health is the only thing that decides live-vs-down; the source list is best-effort.
  try {
    await Api.health();
    $("#gwStatus").textContent = "gateway · live";
    $("#gwStatus").style.color = "var(--accent-2)";
  } catch {
    $("#gwStatus").textContent = "gateway · down";
    $("#gwStatus").style.color = "var(--critical)";
    $("#gwBanner").hidden = false;
    $("#run").disabled = true;
    $("#run").textContent = "gateway offline";
    return;
  }
  try {
    const { samples } = await Api.samples();
    $("#source").innerHTML = samples.map(n => `<option value="sample:${n}">${titleCase(n)} (sample)</option>`).join("");
  } catch {
    $("#source").innerHTML = `<option value="sample:koramangala">Koramangala (sample)</option>`;
  }
  state.source = $("#source").value || state.source;
}

async function run() {
  const body = {
    source: state.source,
    eps: parseFloat($("#eps").value),
    delta: parseFloat($("#delta").value),
    batchSamples: parseInt($("#batch").value, 10),
  };
  $("#run").disabled = true;
  $("#metrics").classList.add("is-empty");
  $("#job").hidden = false;
  $("#stageSub").textContent = "running…";

  try {
    const job = await Api.submit(body);
    state.jobId = job.id;
    $("#jobId").textContent = `job ${job.id}`;
    poll();
  } catch (err) {
    $("#run").disabled = false;
    $("#stageSub").textContent = "submit failed";
    alert(`Could not submit the job:\n${err.message}\n\nIs the gateway running on :8080?`);
  }
}

function poll() {
  state.polling = true;
  const tick = async () => {
    if (!state.polling) return;
    try {
      const v = await Api.job(state.jobId);
      renderJob(v);
      if (v.status === "succeeded") { state.polling = false; await onDone(v); return; }
      if (v.status === "failed") { state.polling = false; onFailed(v); return; }
    } catch (err) {
      state.polling = false; onFailed({ error: err.message }); return;
    }
    setTimeout(tick, 300);
  };
  tick();
}

function renderJob(v) {
  const pill = $("#jobPill");
  pill.textContent = v.status;
  pill.className = `pill pill--${v.status}`;
  $("#progFill").style.width = `${Math.round((v.progress || 0) * 100)}%`;

  const d = v.detail;
  if (d) {
    $("#samplesDone").textContent = d.samplesDone;
    $("#targetSamples").textContent = d.targetSamples;
    $("#batchCount").textContent = d.batches;
    $("#epsNow").textContent = d.currentEpsilon.toFixed(4);
    // ε bar: full at ε=1, target marked as a tick; current shrinks left as ε drops
    $("#epsFill").style.width = `${Math.min(100, d.currentEpsilon * 100)}%`;
    $("#epsTick").style.left = `${Math.min(100, d.targetEpsilon * 100)}%`;
  }
}

async function onFailed(v) {
  $("#run").disabled = false;
  $("#stageSub").textContent = "job failed";
  alert(`The job failed:\n${v.error || "unknown error"}`);
}

async function onDone(v) {
  $("#run").disabled = false;
  const m = v.result.meta;
  $("#stageSub").textContent = `${m.samples} sources · ε≈${m.epsilon}`;

  // headline: cost + honest scale projection
  $("#costSamples").textContent = m.samples.toLocaleString();
  const projected = Math.max(1, Math.round(100000 / m.samples));
  const cheaper = m.exactSources < m.samples;
  $("#costNote").innerHTML = cheaper
    ? `On this <b>${m.n}</b>-node graph, exact (<b>${m.exactSources}</b> shortest-path trees) is
       actually cheaper — k is fixed by ε and δ, <i>not</i> by n. Project to a metro graph of
       <b>100,000</b> junctions and exact needs 100k trees while this still needs ~${m.samples.toLocaleString()}:
       a <b>~${projected}×</b> saving where it matters.`
    : `<b>${m.samples.toLocaleString()}</b> sampled trees vs <b>${m.exactSources.toLocaleString()}</b>
       for exact Brandes — and k doesn't grow with the city.`;

  // measure the estimate against exact Brandes (geometry + exact betweenness from the gateway)
  let rho = null, worst = null, features = null;
  try {
    const crit = await Api.criticality(state.source);
    features = crit.edges.features;
    const exact = new Map(features.map(f => [key(f.properties.u, f.properties.v), f.properties.betweenness ?? 0]));
    const approx = new Map(v.result.edges.map(e => [key(e.u, e.v), e.b]));
    const shared = [...approx.keys()].filter(k => exact.has(k));
    rho = spearman(shared.map(k => exact.get(k)), shared.map(k => approx.get(k)));
    worst = Math.max(...shared.map(k => Math.abs(approx.get(k) - exact.get(k))));
    Map_.heatmap(features, approx);
  } catch { /* gateway has no exact handy — metrics still stand on their own */ }

  renderKvs(m, rho, worst);
  renderTops(v.result.top);
  $("#metrics").classList.remove("is-empty");
}

function renderKvs(m, rho, worst) {
  const rows = [
    ["ε achieved", `${m.epsilon} ≤ ${m.targetEpsilon}`, true],
    ["confidence", `${Math.round((1 - m.delta) * 100)}%`, false],
    ["batches", `${m.batches}`, false],
    ["exact would run", `${m.exactSources.toLocaleString()} SSSP trees`, false],
  ];
  if (rho != null) rows.push(["ranking vs exact (ρ)", rho.toFixed(3), rho > 0.95]);
  if (worst != null) rows.push(["worst edge error", `${worst.toFixed(4)} ≤ ${m.targetEpsilon}`, worst <= m.targetEpsilon]);
  $("#kvs").innerHTML = rows.map(([k, val, good]) =>
    `<div class="kvrow"><span class="k">${k}</span><span class="v ${good ? "good" : ""}">${val}</span></div>`).join("");
}

function renderTops(top) {
  $("#toplist").innerHTML = top.map(e =>
    `<li><span class="seg">${e.u}–${e.v}</span><span class="b">${e.b.toFixed(3)}</span></li>`).join("");
}

// ── client-side Spearman (rank, then Pearson on ranks) ────────────────────────
function spearman(xs, ys) {
  if (xs.length < 2) return 0;
  return pearson(ranks(xs), ranks(ys));
}
function ranks(v) {
  const idx = v.map((_, i) => i).sort((a, b) => v[a] - v[b]);
  const r = new Array(v.length);
  let i = 0;
  while (i < idx.length) {
    let j = i;
    while (j + 1 < idx.length && v[idx[j + 1]] === v[idx[i]]) j++;
    const avg = (i + j) / 2 + 1;
    for (let k = i; k <= j; k++) r[idx[k]] = avg;
    i = j + 1;
  }
  return r;
}
function pearson(a, b) {
  const n = a.length, ma = mean(a), mb = mean(b);
  let cov = 0, va = 0, vb = 0;
  for (let i = 0; i < n; i++) { cov += (a[i] - ma) * (b[i] - mb); va += (a[i] - ma) ** 2; vb += (b[i] - mb) ** 2; }
  return (va && vb) ? cov / Math.sqrt(va * vb) : 0;
}
const mean = a => a.reduce((s, x) => s + x, 0) / a.length;
const titleCase = s => s.replace(/(^|[\s-])\w/g, m => m.toUpperCase());
