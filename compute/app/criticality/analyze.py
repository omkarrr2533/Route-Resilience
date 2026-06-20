"""The criticality pipeline: one graph in, a fully-scored, map-ready result out.

This is the function the API calls. It runs the four measures, folds them into the blended
score, and packages everything as GeoJSON plus a summary. Keeping the orchestration in one
place (rather than scattered across route handlers) means the Spring Boot gateway is caching
a single well-defined artifact, and the validation notebooks can call the exact same code
path the live service uses.

Measures run on the *undirected* projection so every edge has one canonical key shared
across betweenness, current-flow, and the bridge set. One-way-aware directed betweenness is
available in betweenness.py for later, but mixing directed and undirected keys in one heatmap
would be a quiet correctness trap, so the pipeline commits to undirected here.
"""

from __future__ import annotations

import networkx as nx

from app.criticality.betweenness import edge_betweenness
from app.criticality.connectivity import articulation_points_and_bridges
from app.criticality.currentflow import current_flow_edge_betweenness
from app.criticality.impact import global_efficiency, removal_impact
from app.criticality.score import resilience_scores
from app.graph.build import directed_simple, undirected_view
from app.graph.serialize import edges_to_geojson, nodes_to_geojson

# Above this edge count we stop computing per-edge removal impact for everything (each one
# is an all-pairs shortest-path run) and only score the betweenness front-runners. The rest
# keep their flow-based score. Honest degradation beats a request that never returns.
IMPACT_BUDGET_EDGES = 400


def analyze(G, weight="length"):
    U = undirected_view(G, weight=weight)

    betweenness = edge_betweenness(U, weight=weight, normalized=True)
    current_flow = current_flow_edge_betweenness(U, weight=weight, normalized=True)
    articulation, bridges = articulation_points_and_bridges(U)

    impact_rel = _impact_scores(U, betweenness, weight)

    scored = resilience_scores(betweenness, current_flow, impact_rel, bridges)

    per_edge = {}
    for e in U.edges():
        key = tuple(sorted(e))
        s = scored.get(key, {})
        per_edge[key] = {
            "score": s.get("score", 0.0),
            "betweenness": round(betweenness.get(key, 0.0), 6),
            "current_flow": round(current_flow.get(key, 0.0), 6),
            "impact": round(impact_rel.get(key, 0.0), 6),
            "is_bridge": s.get("is_bridge", False),
            "components": s.get("components", {}),
        }

    return {
        "summary": _summary(U, articulation, bridges, scored),
        "edges": edges_to_geojson(U, per_edge),
        "articulation_points": nodes_to_geojson(U, articulation, "articulation_point"),
    }


def _impact_scores(U, betweenness, weight):
    """Relative efficiency drop per edge, within the impact budget."""
    baseline = global_efficiency(U, weight=weight)

    if U.number_of_edges() <= IMPACT_BUDGET_EDGES:
        candidates = list(U.edges())
    else:
        ranked = sorted(betweenness, key=betweenness.get, reverse=True)
        candidates = ranked[:IMPACT_BUDGET_EDGES]

    out = {}
    for u, v in candidates:
        report = removal_impact(U, u, v, weight=weight, baseline_efficiency=baseline)
        out[tuple(sorted((u, v)))] = report["relative_drop"]
    return out


def _summary(U, articulation, bridges, scored):
    components = list(nx.connected_components(U))
    top = sorted(scored.items(), key=lambda kv: kv[1]["score"], reverse=True)[:5]
    return {
        "nodes": U.number_of_nodes(),
        "edges": U.number_of_edges(),
        "connected_components": len(components),
        "largest_component": max((len(c) for c in components), default=0),
        "articulation_points": len(articulation),
        "bridges": len(bridges),
        "top_segments": [
            {"u": e[0], "v": e[1], "score": meta["score"], "is_bridge": meta["is_bridge"]}
            for e, meta in top
        ],
    }
