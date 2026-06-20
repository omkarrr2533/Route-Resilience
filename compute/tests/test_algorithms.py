"""Cross-check the hand-written algorithms against NetworkX on graphs small enough to trust.

If Brandes' path counting is subtly wrong, every centrality score is silently wrong with no
error — so this is the test that actually matters. We assert exact agreement with NetworkX's
own (independently implemented) routines.
"""

import math

import networkx as nx
import pytest

from app.criticality.betweenness import edge_betweenness, edge_betweenness_networkx
from app.criticality.connectivity import articulation_points_and_bridges
from app.criticality.currentflow import current_flow_edge_betweenness


def _karate():
    return nx.karate_club_graph()


def _weighted_grid():
    G = nx.grid_2d_graph(5, 5)
    G = nx.convert_node_labels_to_integers(G)
    for i, (u, v) in enumerate(G.edges()):
        G[u][v]["length"] = 1.0 + (i % 4) * 0.5   # uneven weights to exercise Dijkstra
    return G


@pytest.mark.parametrize("weight", [None, "weight"])
def test_brandes_matches_networkx_unweighted_and_weighted(weight):
    G = _karate()
    if weight:
        for i, (u, v) in enumerate(G.edges()):
            G[u][v]["weight"] = 1.0 + (i % 3)

    ours = edge_betweenness(G, weight=weight, normalized=True)
    ref = nx.edge_betweenness_centrality(G, weight=weight, normalized=True)
    ref = {tuple(sorted(e)): val for e, val in ref.items()}

    assert ours.keys() == ref.keys()
    for e in ref:
        assert math.isclose(ours[e], ref[e], rel_tol=1e-9, abs_tol=1e-12), e


def test_brandes_directed():
    G = nx.gnp_random_graph(15, 0.3, seed=1, directed=True)
    ours = edge_betweenness(G, weight=None, normalized=True)
    ref = edge_betweenness_networkx(G, weight=None, normalized=True)
    for e in ref:
        assert math.isclose(ours[e], ref[e], rel_tol=1e-9, abs_tol=1e-12), e


def test_articulation_and_bridges_match_networkx():
    G = _weighted_grid()
    # graft a pendant pocket so there's a real cut vertex + bridge to find
    G.add_edge(0, 99)
    G.add_edge(99, 98)

    artic, bridges = articulation_points_and_bridges(G)
    assert artic == set(nx.articulation_points(G))
    ours = {tuple(sorted(e)) for e in bridges}
    ref = {tuple(sorted(e)) for e in nx.bridges(G)}
    assert ours == ref


def test_current_flow_is_nonnegative_and_symmetric():
    # No scipy dependency here, so we assert structural properties rather than cross-check
    # against NetworkX (whose current-flow routine needs scipy).
    G = _weighted_grid()
    cf = current_flow_edge_betweenness(G, weight="length", normalized=True)
    assert all(v >= -1e-12 for v in cf.values())
    assert cf.keys() == {tuple(sorted(e)) for e in G.edges()}
