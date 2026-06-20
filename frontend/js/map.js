// Leaflet view. Owns the basemap, the edge polylines, the articulation/bridge overlays and
// all map-side interaction. State lives in app.js; this module just draws what it's told and
// reports clicks back through a callback.
const MapView = (() => {
  let map, edgeLayer, bridgeLayer, articLayer;
  const edgeLines = new Map();          // edgeKey -> polyline, for highlight/lookup
  let onEdgeClick = () => {};
  let selectedKey = null;

  const key = (u, v) => [u, v].sort((a, b) => a - b).join("–");

  function init(elId) {
    map = L.map(elId, { zoomControl: false, attributionControl: true, preferCanvas: true })
           .setView([12.9352, 77.6245], 15);
    L.control.zoom({ position: "bottomright" }).addTo(map);   // keep top-left clear for the HUD

    // CARTO dark basemap — labels off so road criticality, not city names, is the story.
    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png", {
      attribution: '© OpenStreetMap · © CARTO',
      subdomains: "abcd", maxZoom: 20,
    }).addTo(map);

    edgeLayer = L.layerGroup().addTo(map);
    bridgeLayer = L.layerGroup().addTo(map);
    articLayer = L.layerGroup().addTo(map);

    const coords = document.getElementById("coords");
    map.on("mousemove", e =>
      coords.textContent = `${e.latlng.lat.toFixed(4)}, ${e.latlng.lng.toFixed(4)}`);
  }

  function setEdgeClick(cb) { onEdgeClick = cb; }

  // Draw all edges, coloured by the normalised value of `measure` stored on each feature.
  // `fit` re-frames the viewport — true on a fresh network, false on a mere restyle.
  function drawEdges(features, measure, fit = true) {
    edgeLayer.clearLayers();
    edgeLines.clear();
    selectedKey = null;
    const bounds = [];

    for (const f of features) {
      const p = f.properties;
      const t = p._norm[measure] ?? 0;
      const latlngs = f.geometry.coordinates.map(([x, y]) => [y, x]);
      bounds.push(...latlngs);

      const line = L.polyline(latlngs, {
        color: Palette.color(t),
        weight: 2 + t * 5,
        opacity: 0.5 + t * 0.5,
        lineCap: "round",
      });

      const k = key(p.u, p.v);
      line.on("mouseover", () => line.setStyle({ weight: 2 + t * 5 + 3, opacity: 1 }));
      line.on("mouseout", () => { if (k !== selectedKey) line.setStyle({ weight: 2 + t * 5, opacity: 0.5 + t * 0.5 }); });
      line.on("click", () => onEdgeClick(p));
      line.bindTooltip(tooltip(p, measure), { sticky: true, className: "rr-tip" });

      line.addTo(edgeLayer);
      edgeLines.set(k, { line, t });
    }

    if (fit && bounds.length) map.fitBounds(bounds, { padding: [40, 40] });
  }

  // Bridge underlays + articulation markers. Drawn on top of edges, independent of measure,
  // because a single point of failure is critical no matter which centrality you're viewing.
  function drawStructure(edgeFeatures, articFeatures, visible) {
    bridgeLayer.clearLayers();
    articLayer.clearLayers();
    if (!visible) return;

    for (const f of edgeFeatures) {
      if (!f.properties.is_bridge) continue;
      const latlngs = f.geometry.coordinates.map(([x, y]) => [y, x]);
      L.polyline(latlngs, { color: "#ff4d5e", weight: 9, opacity: 0.18, lineCap: "round" })
        .addTo(bridgeLayer);
    }

    for (const f of articFeatures) {
      const [x, y] = f.geometry.coordinates;
      L.marker([y, x], {
        icon: L.divIcon({ className: "artic-icon", html: '<span></span>', iconSize: [16, 16] }),
        interactive: false,
      }).addTo(articLayer);
    }
  }

  function highlight(k) {
    if (selectedKey && edgeLines.has(selectedKey)) {
      const prev = edgeLines.get(selectedKey);
      prev.line.setStyle({ weight: 2 + prev.t * 5, opacity: 0.5 + prev.t * 0.5 });
    }
    selectedKey = k;
    const cur = edgeLines.get(k);
    if (cur) {
      cur.line.setStyle({ weight: 2 + cur.t * 5 + 4, opacity: 1, color: "#ffffff" });
      map.panInsideBounds(cur.line.getBounds(), { animate: true });
    }
  }

  function tooltip(p, measure) {
    const v = measure === "score" ? p.score?.toFixed(0)
            : (p[measure] ?? 0).toPrecision(3);
    return `<b>${p.u}–${p.v}</b> · ${p.highway || "road"}<br>${labelFor(measure)}: ${v}`
         + (p.is_bridge ? "<br><i>bridge — single point of failure</i>" : "");
  }

  function labelFor(m) {
    return { score: "score", betweenness: "betweenness",
             current_flow: "current-flow", impact: "impact" }[m] || m;
  }

  return { init, setEdgeClick, drawEdges, drawStructure, highlight, key };
})();
