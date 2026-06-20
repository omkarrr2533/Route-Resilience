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
from app.data import loaders


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


def clear_caches():
    get_graph.cache_clear()
    get_analysis.cache_clear()
