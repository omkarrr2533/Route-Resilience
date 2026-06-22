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

## Where the novelty is (Tier 3) — built

The topological-repair layer ([`compute/app/repair/`](../compute/app/repair/)) is implemented
and downstream-validated. Four decisions an interviewer tends to dig into:

- **Derive the damage from ground truth.** The scenario starts from a true graph and *applies*
  the two failure modes — hide a segment under an occluder (false break), fuse a flyover onto
  the road below (false junction). Synthesizing the damage rather than hand-authoring a separate
  "extracted" graph hands you a perfect answer key for free: you know exactly which gaps are real
  breaks, which only look like one, and which crossing is the flyover. That's what makes
  precision/recall meaningful (plan §8). It's the same move as the bundled OSM sample standing in
  for live osmnx — an offline stand-in for a real Bhuvan tile.
- **The occluder gate is the safeguard, not the geometry.** Two collinear dead-ends a short hop
  apart are bridgeable *geometrically* whether or not a road was ever there. The thing that stops
  the repair from inventing a road across a park is evidence: a bridge is closed only when an
  occluder (canopy/shadow) covers the gap. The demo includes a decoy gap with no occluder
  precisely to show the repair refusing it.
- **A flyover can't be told from a crossroads by geometry alone.** Both show two roads passing
  through with continuous heading. So the disambiguator splits a 4-way *only* when the through-
  geometry is corroborated by an overpass cue (a bridge/layer tag — in imagery, the elevation
  step). The scenario plants one flyover and four honest at-grade crossings; the repair splits
  the one and leaves the four connected. Splitting every crossing would be worse than doing
  nothing.
- **The experiment that matters isn't "APLS went up."** On the bundled scenario APLS does climb
  (0.87 → 1.00), but the headline is the criticality-ranking correlation against ground truth:
  Spearman ρ **0.49 → 1.00**. The false breaks and the invented flyover-turn scramble which
  junctions look load-bearing; the repair pulls that ranking back. That ties the repair to a
  decision a planner would actually make, not to a prettier map.

## Scaling, on a bounded budget (Tier 3 engineering)

"How does this scale to all of India?" has two halves, and the project answers both.

- **The algorithm: a bound, not a vibe.** Exact Brandes is O(V·E) — fine per city, hopeless
  nationally. Source sampling estimates betweenness from `k` random sources, and because each
  normalized per-source contribution sits in [0,1], Hoeffding plus a union bound over the `m`
  edges gives `k ≥ ln(2m/δ)/(2ε²)` for "every edge within ε, with probability ≥ 1−δ." The
  payoff is that **k doesn't depend on n**: a 46-node sample and a 100k-node metro need roughly
  the same ~1,500 sources for ε=0.05. (Riondato–Kornaropoulos give a tighter, m-free bound via
  the vertex-diameter VC dimension — noted in the code as the upgrade; the union bound is looser
  but self-contained and exact to *state*, which is the honest trade for a portfolio.) Measured
  on the sample: worst-edge error 0.005 and rank correlation 0.997 against exact — the
  approximation keeps the *ranking*, which is the only thing criticality is for.
- **The orchestration: where the JVM earns its place.** A long analysis can't block an HTTP
  thread, so the Spring gateway runs it as an async job: submit returns a job id (202), a
  *bounded* worker pool (concurrency capped so a burst queues instead of OOM-ing — plan §7)
  pulls Monte Carlo batches from the compute service and folds them into one running estimate,
  and ε ticks down toward the target while the browser polls. Two design choices worth defending:
  jobs are **idempotent** (an identical request returns the in-flight job rather than recomputing
  — the cache instinct, one level up), and the gateway does real work (weighted aggregation of
  independent batches + convergence tracking), not just proxying. The registry is in-memory by
  design; the clustered version moves it and the queue into Redis (already a dependency) with the
  same control flow. That batch-aggregation shape is also the seam for a future cuGraph/igraph
  backend: the gateway wouldn't change, only who computes a batch.

## Closing the loop: pixels → graph (Tier 3 extraction)

The synthetic Repair Lab made a fair objection easy to raise: *the breaks are removed from a
graph by hand — would the repair survive a real extraction?* So the loop is closed. A road mask
goes through a genuine vectorizer and the repair runs on the graph that falls out.

- **The pipeline is the standard one, written by hand.** `clean → skeletonize → trace → prune →
  georeference`, in pure NumPy — Bresenham rasterization, **Zhang–Suen** thinning (vectorized,
  whole-image per iteration), centreline tracing (pixels with ≠2 neighbours are nodes; the
  degree-2 runs between them are edges; adjacent node-pixels collapse to one junction), spur
  pruning, and an affine georeference. No scikit-image, no GDAL — the same "installs anywhere"
  discipline as the rest of the core, and the same reason Brandes is written out: it's worth
  being able to defend.
- **The breaks are emergent, not authored.** An occluder erases the road's pixels; the
  centreline there simply isn't traced, so two dangling endpoints appear across the gap — a
  false break that *fell out of the image*. That's the honest input the repair was built for,
  and it bridges them under the same occluder gate.
- **Validation has to be geometric.** The extractor invents its own nodes at its own pixel
  positions — there's no shared id to join on — which is exactly why APLS exists. We match
  ground-truth junctions to the nearest extracted node and score path-length agreement and the
  criticality ranking over those matches. The numbers are honestly lower than the synthetic case
  (APLS 0.83→0.98, ranking 0.43→0.78): real extraction adds geometric noise on top of the
  breaks, and the repair fixes the breaks — the catastrophic part — leaving the benign residual.
- **What's mocked, stated plainly.** Only the *imagery* is synthesized (a mask rasterized from
  OSM geometry, then occluded and speckled), because a Bhuvan tile can't be bundled and a GPU
  segmentation net shouldn't be. `segment.predict_mask` is the documented seam: a real tile and a
  pretrained D-LinkNet/U-Net checkpoint plug in there, and `vectorize` onward is byte-for-byte
  identical. Mask-to-a-Bhuvan-tile is what bundled-GeoJSON-to-live-osmnx already is.

## Deliberate non-goals

- **No frontend framework.** Three small pages — a map, some controls, a chart. A framework
  would be ceremony; the depth is in the engine and the orchestration.
- **No trained segmentation net in-repo.** The *vectorizer* (mask→graph) is built and tested;
  the upstream net is the one piece left as a documented hook. A pretrained encoder-decoder on a
  Bhuvan tile is enough when it's wired — the repair layer, not a marginally better mask, is the
  contribution, and a good-enough mask plus repair beats a better mask with none.
- **Nationwide scale: the algorithm, not the deployment.** Approximate betweenness with a
  guaranteed ε-bound and the async pool that runs it are built; regional sharding and a
  Redis-backed distributed queue are deliberately left as the deployment story, not over-built
  on a single box now.
