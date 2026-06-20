"""Graph resolution + an in-process result cache.

Criticality is expensive and, crucially, *static* until the graph changes — so we never want
to compute the same city twice. There are two cache layers in the full architecture: this
one (so a single compute worker doesn't redo work), and Redis behind the Spring Boot gateway
(shared across workers, survives a restart). This module owns the first.

A source is a small string so it's a clean cache key and trivially passed through the API:
    sample:<name>        -> bundled offline GeoJSON
    place:<osm query>    -> live OSM pull via osmnx
"""

from __future__ import annotations

from functools import lru_cache

from app.criticality.analyze import analyze
from app.criticality.flow import min_cut_between
from app.data import loaders
from app.graph.build import undirected_view
from app.graph.serialize import cut_edges_to_geojson, nodes_to_geojson, segments_to_geojson
from app.graph.terrain import attach_elevation
from app.graph.zones import resolve_zone
from app.scenarios.flood import flood_impact, restoration_priority


def parse_source(source):
    kind, _, value = source.partition(":")
    return kind, value


@lru_cache(maxsize=16)
def get_graph(source):
    kind, value = parse_source(source)
    if kind == "sample":
        return loaders.load_sample(value or "koramangala")
    if kind == "place":
        if not loaders.osmnx_available():
            raise RuntimeError(
                "osmnx isn't installed in this environment — use a sample: source, "
                "or run the compute service in Docker where the geospatial stack lives."
            )
        return loaders.load_place(value)
    raise ValueError(f"Unknown source kind '{kind}'. Expected 'sample' or 'place'.")


# The analysis is keyed on (source, weight). lru_cache gives us memoization + a bounded size
# for free; it's the in-process stand-in for "precompute per city, recompute only on change".
@lru_cache(maxsize=32)
def get_analysis(source, weight="length"):
    G = get_graph(source)
    return analyze(G, weight=weight)


@lru_cache(maxsize=64)
def get_bottleneck(source, origin="west", dest="east", weight="length"):
    """Max-flow value and the min-cut (the bottleneck) between two zones, map-ready."""
    G = get_graph(source)
    U = undirected_view(G, weight=weight)

    src_nodes = resolve_zone(U, origin)
    dst_nodes = resolve_zone(U, dest)
    result = min_cut_between(U, src_nodes, dst_nodes)

    return {
        "max_flow": result["max_flow"],
        "unit": "veh/h",
        "origin": origin,
        "dest": dest,
        "cut_size": result.get("cut_size", 0),
        "min_cut": cut_edges_to_geojson(U, result.get("cut_edges", [])),
        "origin_nodes": nodes_to_geojson(U, src_nodes, "origin"),
        "dest_nodes": nodes_to_geojson(U, dst_nodes, "dest"),
    }


@lru_cache(maxsize=64)
def get_flood(source, level=12.0, weight="length"):
    """Flood at a given water level: submerged roads, who loses hospital access, and the
    restoration priority list — all map-ready."""
    G = get_graph(source)
    attach_elevation(G)                     # mutates the cached graph once; idempotent
    U = undirected_view(G, weight=weight)

    impact = flood_impact(U, level)
    priority = restoration_priority(U, level, impact["hospitals"], k=5)

    return {
        "level": level,
        "lost_access_count": impact["lost_access_count"],
        "lost_access_fraction": impact["lost_access_fraction"],
        "with_access_after": impact["with_access_after"],
        "nodes_total": impact["nodes_total"],
        "submerged_count": impact["submerged_count"],
        "submerged": segments_to_geojson(U, impact["submerged"], "submerged"),
        "lost_access": nodes_to_geojson(U, impact["lost_access_nodes"], "lost_access"),
        "hospitals": nodes_to_geojson(U, impact["hospitals"], "hospital"),
        "restoration": segments_to_geojson(U, priority, "restore"),
    }


def clear_caches():
    get_graph.cache_clear()
    get_analysis.cache_clear()
    get_bottleneck.cache_clear()
    get_flood.cache_clear()
