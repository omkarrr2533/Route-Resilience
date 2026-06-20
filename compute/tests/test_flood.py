"""Flood scenario: terrain, accessibility-to-services loss, and restoration.

The property that matters is the accessibility framing — a "lost access" node must genuinely
have no route to any hospital once the flooded roads are gone, and clearing roads must only
ever restore access, never remove it.
"""

import networkx as nx

from app.data.loaders import load_sample
from app.graph.build import undirected_view
from app.graph.terrain import attach_elevation
from app.scenarios.flood import (
    default_hospitals,
    flood_impact,
    flooded_edges,
    restoration_priority,
)


def _sample():
    G = load_sample("koramangala")
    attach_elevation(G)
    return undirected_view(G)


def test_elevation_is_attached_and_idempotent():
    U = _sample()
    assert all("elevation" in d for _, d in U.nodes(data=True))
    snapshot = {n: d["elevation"] for n, d in U.nodes(data=True)}
    attach_elevation(U)                                   # second call must not change anything
    assert {n: d["elevation"] for n, d in U.nodes(data=True)} == snapshot


def test_dry_level_floods_nothing():
    U = _sample()
    lowest = min(d["elevation"] for _, d in U.nodes(data=True))
    impact = flood_impact(U, lowest - 1.0)
    assert impact["submerged_count"] == 0
    assert impact["lost_access_count"] == 0


def test_rising_water_is_monotonic():
    U = _sample()
    hosp = default_hospitals(U)
    low = flood_impact(U, 10.0, hosp)
    high = flood_impact(U, 16.0, hosp)
    assert high["submerged_count"] >= low["submerged_count"]
    assert high["lost_access_count"] >= low["lost_access_count"]


def test_lost_access_nodes_really_cannot_reach_a_hospital():
    U = _sample()
    hosp = set(default_hospitals(U))
    level = 16.0

    H = U.copy()
    H.remove_edges_from(flooded_edges(U, level))
    impact = flood_impact(U, level, hosp)

    for n in impact["lost_access_nodes"]:
        assert not any(n in c and (c & hosp) for c in nx.connected_components(H))


def test_restoration_only_helps():
    U = _sample()
    hosp = default_hospitals(U)
    picks = restoration_priority(U, 16.0, hosp, k=5)
    assert picks                                          # there's something worth clearing
    assert all(p["restores"] >= 1 for p in picks)         # every pick reconnects someone
    submerged = set(map(frozenset, flooded_edges(U, 16.0)))
    assert all(frozenset((p["u"], p["v"])) in submerged for p in picks)  # only clears flooded roads
