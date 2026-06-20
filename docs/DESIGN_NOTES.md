# Design notes

Working notes on *why* the system is shaped the way it is — the decisions an interviewer
tends to dig into. The high-level plan lives outside the repo; this is the engineering
rationale that survives contact with the code.

## The core bet: decouple the two halves

Road extraction from satellite imagery is a computer-vision problem, and CV is the part of
this project most likely to eat a month and still be fragile. So it's quarantined. The
criticality engine — the actual subject of the project — runs on OpenStreetMap graphs, which
`osmnx` hands over clean and connected. That half always works, ships independently, and is
fully under control. Extraction + topological repair is a separate module proven on a handful
of sample tiles, never a dependency of the core. No single hard part can sink the whole.

## Why a Python + Java split

A single Python service would have been less code. Two services earns its keep because the
two layers have genuinely different jobs:

- **Compute (Python/FastAPI)** — geospatial + graph science. NetworkX, NumPy, osmnx, and
  eventually PyTorch live here because that ecosystem is Python's.
- **Gateway (Java/Spring Boot)** — orchestration. Betweenness on a city graph is a
  minutes-long computation; the gateway caches the result (static until the graph changes),
  keeps the browser off the critical path, validates input, and is where async job submission
  and progress tracking land in Tier 2.

The caching boundary is the point. A criticality result is expensive to produce and cheap to
reuse, which is the textbook shape for a cache sitting in front of a compute worker.

## Correctness traps that are easy to get wrong

- **Distance in degrees.** WGS84 coordinates are degrees; a "length" computed in degree-space
  is meaningless and latitude-dependent. Lengths come from haversine (true ground distance),
  which is what makes travel times trustworthy. At city scale this matches a UTM reprojection
  to sub-metre — without dragging in GDAL.
- **Edge identity across measures.** Betweenness, current-flow, and the bridge set must agree
  on what "an edge" is, or the heatmap and the structural flags contradict each other. Every
  measure keys on the canonical sorted-tuple undirected edge.
- **Path counting in Brandes.** A subtle bug in shortest-path counting produces no error — it
  just silently returns wrong centralities. That's why the hand-written Brandes is pinned
  against NetworkX on weighted, unweighted, and directed graphs in the test suite.
- **Impact that doesn't blow up.** The moment one OD pair disconnects, *mean* shortest-path
  distance jumps to infinity. Global efficiency (mean of `1/distance`) degrades gracefully
  instead, which is why removal impact is measured on efficiency, not average travel time.

## Where the novelty is (Tier 3)

The research claim is downstream-validated: a topological-repair layer that closes
occlusion-induced breaks in an extracted graph, gated on occluder evidence so it doesn't
hallucinate roads, and careful to *not* connect grade-separated flyover crossings. The
experiment that matters isn't "APLS went up" — it's "criticality rankings on the repaired
graph correlate with ground-truth rankings far better than rankings on the raw extracted
graph." That ties the repair to real decision-making, not a prettier map.

## Deliberate non-goals

- **No frontend framework.** One map, a few controls, one chart. A framework would be
  ceremony; the depth is in the engine.
- **No SOTA segmentation model.** A known encoder-decoder with published weights on a few
  tiles is enough — the repair layer, not a marginally better mask, is the contribution.
- **No nationwide scale yet.** Exact betweenness is fine per city; approximate betweenness
  with error bounds is a Tier-3 concern, flagged where it belongs rather than over-built now.
