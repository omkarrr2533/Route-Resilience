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
layer that fixes occlusion damage in an extracted graph before any analysis runs — now built,
and shown to lift the criticality-ranking correlation against ground truth from **0.49 to 1.00**
on a controlled scenario. The core engine, meanwhile, stands entirely on OpenStreetMap data and
needs no satellite imagery at all.

---

## What works right now

**Tiers 1–2 end to end, plus the Tier-3 differentiators** — all verified running:

- **Criticality engine** (Python) — edge betweenness (Brandes), current-flow betweenness,
  articulation points & bridges (Tarjan), single-edge removal impact, and a blended,
  explainable 0–100 resilience score per segment.
- **Robustness simulation** — targeted-vs-random attack curves with area-under-curve.
- **Bottleneck analysis** *(Tier 2)* — max-flow / min-cut between zones via Dinic's
  algorithm; the min-cut edges (the literal bottleneck) are drawn on the map.
- **Flood scenario** *(Tier 2)* — framed around **access to services**, not bare
  connectivity: at a given water level, which roads submerge, how many junctions lose all
  road access to a hospital, and a greedy **restoration-priority** list (which roads to clear
  first). Synthetic terrain offline; rasterio/CartoDEM hook for real DEMs.
- **Topological repair** *(Tier 3 — the differentiator)* — the headline contribution, now
  demonstrated end to end on a controlled occlusion scenario with held-out ground truth:
  occluder-conditioned **gap closure** for false breaks and **flyover disambiguation** for the
  false junctions a 2D extractor invents at overpasses. Every decision is evidence-gated and
  reasoned. Validated against ground truth: APLS path-agreement **0.87 → 1.00** and — the claim
  that matters — the criticality-ranking correlation (Spearman ρ) **0.49 → 1.00**. A prettier
  map is incidental; recovering the *ranking* is the point.
- **Scale & async** *(Tier 3 — the engineering layer)* — **approximate betweenness** by source
  sampling with a *guaranteed* additive error bound: `k ≥ ln(2m/δ)/(2ε²)` sources put every
  edge within ε at confidence 1−δ. On the sample, ε=0.05 needs ~1,460 sources for a worst-edge
  error of 0.005 and a rank correlation against exact Brandes of **0.997** — and k doesn't grow
  with the city, which is the whole scalability point. The **Spring Boot gateway** runs it as a
  proper **async job**: submit returns a job id immediately (202), a bounded worker pool streams
  Monte Carlo batches from compute and aggregates a running estimate, and ε ticks down toward
  the target while the browser polls progress. Jobs are idempotent (identical requests dedupe).
- **Spring Boot gateway** — the orchestration layer: caches the expensive results (Caffeine;
  Redis-ready), validates requests, and owns the async job pool (submit / poll / dedupe, bounded
  concurrency so a burst queues instead of OOM-ing).
- **Dashboard** — three views. A dark **criticality console** (score heatmap, articulation
  markers, network inspector, click-to-simulate-removal, robustness chart); a **Topological
  Repair Lab** (before/after toggle, occluder layer, per-decision overlays, validation metrics);
  and a **Scale Lab** (submit an approximate-betweenness job, watch ε converge, then see the
  estimate measured against exact — rank correlation and worst-edge error, with the heatmap).

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
        │  · async job pool      ★   │     (submit / poll / dedupe, bounded)
        └─────────────┬─────────────┘
                      │  internal REST
        ┌─────────────▼─────────────┐
        │  Compute service (FastAPI) │   ← the science
        │  · graph construction      │     (osmnx / bundled GeoJSON)
        │  · criticality engine  ★   │     (exact + sampled w/ ε-bound)
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
changes), shields the browser from long computations, and runs long analyses as async jobs on
a bounded worker pool (submit → poll → result, never a blocked request thread). "Right tool per
layer" — Java for orchestration/concurrency, Python where
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

The console and Repair Lab run against the compute service alone; the **Scale Lab** (`/scale.html`)
drives the async job API, so it needs the gateway running on `:8080`.

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
| **Approximate betweenness** | the same ranking on a graph too big for exact, *with a proof* | source sampling + Hoeffding/union error bound ([`approx_betweenness.py`](compute/app/criticality/approx_betweenness.py)) |

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

The read endpoints are identical on the compute service (`:8000`) and the gateway (`:8080`); the
gateway adds caching and validation. The **async job API is gateway-only** — it's the
orchestration the Spring layer exists for.

| Endpoint | Returns |
|---|---|
| `GET /api/criticality?source=sample:koramangala&weight=length` | scored edges (GeoJSON) + articulation points + summary |
| `GET /api/impact?u=27&v=100&source=...` | efficiency drop & fragmentation for removing one edge |
| `GET /api/bottleneck?origin=north&dest=south&source=...` | max-flow between two zones + the min-cut edges |
| `GET /api/flood?level=14&source=...` | submerged roads, junctions that lose hospital access, restoration priority |
| `GET /api/robustness?source=...&steps=16` | targeted & random attack curves + AUC |
| `GET /api/repair` | the Tier-3 repair demo: ground-truth / raw / repaired graphs, occluders, per-decision overlays, and validation metrics |
| `GET /api/criticality/approx?eps=0.05&delta=0.1&source=...` | approximate betweenness sized to the ε-bound, one shot |
| `GET /api/criticality/sample-batch?samples=150&seed=0&source=...` | one Monte Carlo batch — the unit the gateway aggregates |
| `GET /api/samples` · `GET /api/health` | bundled networks · service + osmnx availability |
| **`POST /api/jobs/approx-betweenness`** *(gateway)* | submit an async job → `202` + job id |
| **`GET /api/jobs/{id}`** *(gateway)* | live status, progress, current ε, and the result when done |

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
  (Dinic), the capacity/BPR model, the **flood + accessibility-to-services** scenario (with
  restoration prioritization), and ✅ **async job orchestration** (the gateway's bounded worker
  pool, submit/poll/dedupe) are done; next: PostGIS spatial indexing.
- **Tier 3 — the differentiator** *(in progress)* — ✅ the **topological-repair** layer
  (occluder-conditioned gap closure + flyover disambiguation) and its **validation experiment**
  (APLS before-vs-after *and* the criticality-ranking rank correlation on
  repaired-vs-ground-truth) are built and demonstrated on a controlled occlusion scenario with
  known ground truth — exactly the methodology §8 calls for. Live in [`compute/app/repair/`](compute/app/repair/)
  and the **Repair Lab** (`/repair.html`). ✅ **Scalability** is in too: approximate betweenness
  with a guaranteed ε-bound (§9), orchestrated as an async job and shown in the **Scale Lab**
  (`/scale.html`). Next: close the loop on *real* imagery — road extraction on Bhuvan sample
  tiles and mask→graph vectorization — so the repair runs on a genuinely-extracted graph.

The `compute/app/extraction/` package is stubbed with the plan references so the shape is
visible; the repair scenario stands in for it offline, the way the bundled OSM sample stands in
for live osmnx.

---

## Stack

Python · FastAPI · NetworkX · NumPy · osmnx · Java 21 · Spring Boot 3 · Caffeine/Redis ·
Leaflet · Chart.js · PostGIS · Docker. See [`docs/DESIGN_NOTES.md`](docs/DESIGN_NOTES.md)
for the engineering rationale.
