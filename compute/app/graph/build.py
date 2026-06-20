"""Turn raw road data into the weighted graph the criticality engine runs on.

Two correctness concerns live here, both flagged in the project plan as the ones that
quietly ruin geospatial work:

  1. Lengths must be in metres, not degrees. OSM coordinates are WGS84 (lat/lon in degrees);
     measuring a path in degree-space gives nonsense distances that vary with latitude. We
     compute true ground distance with the haversine formula straight from lat/lon — for
     city-scale edges this is identical (to sub-metre) to reprojecting onto a UTM zone, and
     it needs no GDAL/pyproj, which keeps the service installable on plain Windows.

  2. The algorithms want different views of the same network. Betweenness runs on a directed
     simple graph (one-ways matter; parallel edges collapse to their cheapest representative);
     articulation/bridge analysis runs on the undirected projection (connectivity has no
     direction). We derive both from one MultiDiGraph so they never drift out of sync.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

import networkx as nx

EARTH_RADIUS_M = 6_371_000.0

# Free-flow speeds (km/h) by OSM highway class. Deliberately conservative for Indian urban
# arterials — these aren't German autobahns, and travel-time weighting should reflect that.
SPEED_KMH = {
    "motorway": 70, "trunk": 55, "primary": 45, "secondary": 38,
    "tertiary": 32, "residential": 24, "living_street": 12,
    "service": 16, "unclassified": 28,
}
DEFAULT_SPEED_KMH = 28

# Practical capacity (vehicles/hour) by class — the saturation flow a segment can pass.
# These feed two Tier-2 features: max-flow/min-cut (the capacities of the flow network) and
# the BPR volume-delay curve (the `c` in v/c). Order-of-magnitude figures for mixed urban
# traffic, not lane-by-lane HCM values.
CAPACITY_VPH = {
    "motorway": 2200, "trunk": 1600, "primary": 1200, "secondary": 900,
    "tertiary": 600, "residential": 400, "living_street": 150,
    "service": 200, "unclassified": 500,
}
DEFAULT_CAPACITY_VPH = 400


def annotate(G):
    """Attach length_m and travel_time_s to every edge in place; return G.

    Idempotent — safe to call on a graph that already carries a `length` from osmnx, in
    which case we trust the source length and only fill in travel time.
    """
    for u, v, data in G.edges(data=True):
        if "length_m" not in data:
            data["length_m"] = _edge_length_m(G, u, v, data)
        speed = _speed_for(data.get("highway"))
        data["travel_time_s"] = data["length_m"] / (speed * 1000.0 / 3600.0)
        data["capacity"] = _capacity_for(data.get("highway"))
        # `length` is the generic weight the criticality modules default to.
        data.setdefault("length", data["length_m"])
    return G


def bpr_travel_time(free_flow_s, volume, capacity, alpha=0.15, beta=4.0):
    """BPR volume-delay function: congested travel time given a flow.

    t = t0 * (1 + alpha * (v/c)^beta), with the classic alpha=0.15, beta=4. As volume
    approaches capacity the term blows up super-linearly, which is what makes congestion bite
    — distance-only weighting would miss it entirely. Used by the scenario engine to model a
    flooded road as a *capacity reduction* (slower) rather than a hard deletion (gone).
    """
    if capacity <= 0:
        return float("inf")
    return free_flow_s * (1.0 + alpha * (volume / capacity) ** beta)


def _edge_length_m(G, u, v, data):
    # Prefer an explicit geometry if one rode along on the edge; otherwise straight-line
    # haversine between the two endpoints.
    if "length" in data and isinstance(data["length"], (int, float)):
        return float(data["length"])
    y1, x1 = G.nodes[u]["y"], G.nodes[u]["x"]
    y2, x2 = G.nodes[v]["y"], G.nodes[v]["x"]
    return haversine_m(y1, x1, y2, x2)


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres between two WGS84 points."""
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlmb = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(a))


def _speed_for(highway):
    # osmnx sometimes hands back a list (a way tagged with several classes); take the first.
    if isinstance(highway, (list, tuple)) and highway:
        highway = highway[0]
    return SPEED_KMH.get(highway, DEFAULT_SPEED_KMH)


def _capacity_for(highway):
    if isinstance(highway, (list, tuple)) and highway:
        highway = highway[0]
    return CAPACITY_VPH.get(highway, DEFAULT_CAPACITY_VPH)


def directed_simple(G, weight="length"):
    """Collapse a MultiDiGraph to a DiGraph, keeping the cheapest of any parallel edges.

    Roundabouts and divided carriageways show up as parallel edges; for shortest-path work
    only the best one matters, and keeping all of them would double-count paths in Brandes.
    """
    if not G.is_multigraph():
        return G if G.is_directed() else G.to_directed()

    D = nx.DiGraph()
    D.add_nodes_from(G.nodes(data=True))
    for u, v, data in G.edges(data=True):
        w = data.get(weight, 1.0)
        if not D.has_edge(u, v) or w < D[u][v].get(weight, float("inf")):
            D.add_edge(u, v, **data)
    return D


def undirected_view(G, weight="length"):
    """Undirected simple graph for connectivity analysis (Tarjan, robustness, components)."""
    base = directed_simple(G, weight=weight) if G.is_multigraph() else G
    return base.to_undirected()
