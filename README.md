# Route Resilience

**Graph-theoretic criticality analysis for urban road networks — built so that graph
reasoning, not a fragile CV model, carries the project.**

Which roads in a city are *load-bearing*? Which single segment, if it floods or closes,
strands a neighbourhood or quietly doubles everyone's travel time? Route Resilience answers
that with classical graph theory — betweenness, current-flow centrality, articulation
points, max-flow bottlenecks, impact simulation — served through a polyglot architecture
that keeps the expensive maths cached and the UI responsive.

The longer-term thesis: *a criticality ranking is only as trustworthy as the network's
topology, and occlusion (tree canopy, shadows, flyovers) silently breaks topology.* So the
headline research contribution (Tier 3, see [Roadmap](#roadmap)) is a **topological-repair**
layer that fixes occlusion damage in an extracted graph before any analysis runs. The core
engine, though, stands entirely on OpenStreetMap data and is what's built and running today.

---

## What works right now

A complete **Tier-1 vertical slice**, end to end, verified running:

- **Criticality engine** (Python) — edge betweenness (Brandes), current-flow betweenness,
  articulation points & bridges (Tarjan), single-edge removal impact, and a blended,
  explainable 0–100 resilience score per segment.
- **Robustness simulation** — targeted-vs-random attack curves with area-under-curve.
- **Bottleneck analysis** *(first Tier-2 feature)* — max-flow / min-cut between zones via
  Dinic's algorithm; the min-cut edges (the literal bottleneck) are drawn on the map.
- **Spring Boot gateway** — caches the expensive results (Caffeine; Redis-ready) and fronts
  the compute service.
- **Dashboard** — a dark "criticality console": Leaflet map with the score heatmap,
  pulsing articulation markers, a network inspector, click-a-segment-to-simulate-removal,
  and the robustness chart.

It runs with **zero external services** on plain Windows/macOS/Linux — the engine falls back
to a bundled sample neighbourhood when the geospatial stack (osmnx/GDAL) isn't installed, so
nothing about the demo depends on a painful native install.

---

## Architecture

```
        ┌───────────────────────────┐
        │  Dashboard (vanilla JS)    │   Leaflet heatmap · inspector
        │  Leaflet · Chart.js        │   what-if removal · robustness curves
        └─────────────┬─────────────┘
                      │  REST (GeoJSON)
        ┌─────────────▼─────────────┐
        │  Spring Boot gateway       │   ← Java showcase
        │  · result caching          │     (Caffeine in-proc / Redis clustered)
        │  · request validation      │
        │  · (async jobs — Tier 2)   │
        └─────────────┬─────────────┘
                      │  internal REST
        ┌─────────────▼─────────────┐
        │  Compute service (FastAPI) │   ← the science
        │  · graph construction      │     (osmnx / bundled GeoJSON)
        │  · criticality engine  ★   │
        │  · scenario simulator  ★   │
        │  · topological repair  ★   │     (Tier 3 — the differentiator)
        └─────────────┬─────────────┘
                      │
         ┌────────────┼────────────┐
         ▼            ▼            ▼
    PostGIS        Redis      object store
   (graphs,      (cache,       (raster tiles,
   criticality)   job queue)    model weights)

★ = the owned, high-value modules
```

**Why two services instead of one Python app?** Computing betweenness on a full city graph
takes minutes. The Spring layer absorbs that: it caches results (static until the graph
changes), shields the browser from long computations, and is where async job orchestration
lands in Tier 2. "Right tool per layer" — Java for orchestration/concurrency, Python where
the geospatial-graph science lives — is the architecture, not an accident.

---

## Quickstart

### The fast path (what's verified — no Docker, no GDAL)

```bash
cd compute
python -m venv .venv
.venv/Scripts/activate            # Windows;  source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
python data/make_sample.py        # writes the bundled Koramangala sample
uvicorn app.main:app --port 8000
```

Open **http://localhost:8000/** — the compute service serves the dashboard too, so the whole
slice runs from one process. Click any road to see its criticality breakdown; hit **Simulate
removal** to recompute the network without it.

Run the tests (they cross-check the hand-written Brandes/Tarjan against NetworkX):

```bash
cd compute && .venv/Scripts/python -m pytest -q
```

### The full stack (gateway + infra)

```bash
docker compose up --build         # dashboard → http://localhost:8088 (via nginx → gateway → compute)
```

This brings up PostGIS, Redis, the compute service (with the full geospatial stack, so
`place:` live-OSM sources work), the Spring Boot gateway, and nginx serving the dashboard.
To run just the gateway against a local compute service:

```bash
cd backend && mvn spring-boot:run    # needs JAVA_HOME → a JDK 21
```

---

## The criticality engine

Each measure answers a different question; comparing them is itself a result.

| Measure | Question it answers | Implementation |
|---|---|---|
| **Edge betweenness** | how many shortest routes ride this segment? | Brandes, by hand — BFS/Dijkstra SSSP + dependency accumulation ([`betweenness.py`](compute/app/criticality/betweenness.py)) |
| **Current-flow betweenness** | how much *spread-out* traffic leans on it? | Laplacian pseudoinverse + sorted-differences trick ([`currentflow.py`](compute/app/criticality/currentflow.py)) |
| **Articulation points / bridges** | is it a literal single point of failure? | Tarjan low-link DFS, iterative ([`connectivity.py`](compute/app/criticality/connectivity.py)) |
| **Removal impact** | what actually breaks if it's gone? | global-efficiency drop + fragmentation ([`impact.py`](compute/app/criticality/impact.py)) |
| **Resilience score** | one explainable number, 0–100 | weighted blend + structural bonus ([`score.py`](compute/app/criticality/score.py)) |
| **Max-flow / min-cut** | how many veh/h cross between two zones, and where's the wall? | Dinic's algorithm, by hand ([`flow.py`](compute/app/criticality/flow.py)) |

The algorithms are written out rather than pulled from NetworkX one-liners — partly because
the correctness of Brandes' path-counting is load-bearing (a subtle bug silently corrupts
every score, which is exactly what `test_algorithms.py` guards against), and partly because
this is the part of the project worth being able to defend line by line.

**Current-flow** gets first-class treatment because real traffic doesn't only take shortest
paths; modelling the network as a resistor grid and measuring the current each edge carries
tracks observed road-disruption better than shortest-path centrality
([Messina et al.](https://doi.org/10.1016/j.physa.2019.123097)).

A concrete result from the bundled sample: removing the one bridge into the east pocket drops
global network efficiency **8.8%** and cuts off **4 nodes / 336 origin-destination pairs** —
which is why that segment, and only that segment, scores 100.

---

## API

All endpoints are identical on the compute service (`:8000`) and the gateway (`:8080`); the
gateway adds caching and validation.

| Endpoint | Returns |
|---|---|
| `GET /api/criticality?source=sample:koramangala&weight=length` | scored edges (GeoJSON) + articulation points + summary |
| `GET /api/impact?u=27&v=100&source=...` | efficiency drop & fragmentation for removing one edge |
| `GET /api/bottleneck?origin=north&dest=south&source=...` | max-flow between two zones + the min-cut edges |
| `GET /api/robustness?source=...&steps=16` | targeted & random attack curves + AUC |
| `GET /api/samples` | available bundled networks |
| `GET /api/health` | service + osmnx availability |

`source` is `sample:<name>` (offline) or `place:<osm query>` (live, needs the geospatial
stack). `weight` is `length` (distance) or `travel_time_s` (free-flow time by road class).

---

## Design decisions

- **Decouple the two halves.** The criticality engine runs purely on OSM graphs — it always
  works and is fully under control. Road extraction + repair (Tier 3) is a separable module
  demonstrated on a few sample tiles. CV fragility can never sink the project.
- **Haversine lengths, not degree-space.** OSM coordinates are WGS84 degrees; measuring path
  lengths in degrees is the classic geospatial bug that makes every travel time garbage. We
  compute true ground distance with haversine — sub-metre-equivalent to a UTM reprojection at
  city scale, and it needs no GDAL, which keeps the core installable anywhere.
- **Undirected projection for the heatmap.** Betweenness, current-flow, and bridges all key
  on one canonical undirected edge, so the four measures never disagree about identity.
  One-way-aware *directed* betweenness exists in the code for later, but mixing directed and
  undirected keys in a single heatmap is a quiet correctness trap, so the pipeline commits.
- **Honest degradation under load.** Per-edge removal impact is an all-pairs shortest-path
  run; above an edge budget the engine scores only the betweenness front-runners rather than
  hanging. The cache (gateway) is what keeps the *typical* request instant.
- **Vanilla JS frontend, on purpose.** A map with coloured roads, a few controls and a chart
  needs no framework; the project's depth is in the backend and the graph engine, and that's
  where the effort went (plan §10).

---

## Roadmap

The project is tiered so there's always something demo-able.

- **Tier 1 — MVP spine** ✅ *(this repo)* — betweenness heatmap, articulation/bridges,
  removal impact, gateway + cache, dashboard.
- **Tier 2 — depth & scenarios** *(in progress)* — ✅ max-flow/min-cut bottleneck analysis
  (Dinic) and the capacity/BPR model are done; next: flood scenario via CartoDEM with
  **accessibility-to-services** loss (not just connectivity), async job orchestration, and
  PostGIS spatial indexing.
- **Tier 3 — the differentiator** — road extraction on Bhuvan sample tiles, mask→graph
  vectorization, and the **topological-repair** layer (occluder-conditioned bridging +
  flyover disambiguation), validated by: APLS/TOPO before-vs-after, *and* the rank
  correlation of criticality scores on repaired-vs-ground-truth graphs.

The `compute/app/extraction/` and `compute/app/repair/` packages are stubbed with the plan
references so the shape is visible.

---

## Stack

Python · FastAPI · NetworkX · NumPy · osmnx · Java 21 · Spring Boot 3 · Caffeine/Redis ·
Leaflet · Chart.js · PostGIS · Docker. See [`docs/DESIGN_NOTES.md`](docs/DESIGN_NOTES.md)
for the engineering rationale.
