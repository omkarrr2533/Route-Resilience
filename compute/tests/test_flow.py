"""Max-flow / min-cut correctness.

Two kinds of check: the raw Dinic value against NetworkX on a textbook network, and the
max-flow/min-cut theorem on the real sample (the extracted cut's capacities must sum to the
flow, or the cut isn't actually minimum).
"""

import math

import networkx as nx

from app.criticality.flow import Dinic, min_cut_between
from app.data.loaders import load_sample
from app.graph.build import undirected_view
from app.graph.zones import resolve_zone


def _dinic_value(G, s, t):
    idx = {n: i for i, n in enumerate(G.nodes())}
    d = Dinic(len(idx))
    for u, v, data in G.edges(data=True):
        d.add_edge(idx[u], idx[v], data["capacity"], 0.0)   # directed arcs
    return d.max_flow(idx[s], idx[t])


def test_dinic_matches_networkx_clrs_example():
    # The CLRS max-flow network; the known answer is 23.
    G = nx.DiGraph()
    for u, v, c in [(0, 1, 16), (0, 2, 13), (1, 2, 10), (2, 1, 4), (1, 3, 12),
                    (3, 2, 9), (2, 4, 14), (4, 3, 7), (3, 5, 20), (4, 5, 4)]:
        G.add_edge(u, v, capacity=c)

    ours = _dinic_value(G, 0, 5)
    assert math.isclose(ours, nx.maximum_flow_value(G, 0, 5, capacity="capacity"))
    assert math.isclose(ours, 23.0)


def test_bridge_is_the_only_bottleneck_into_the_pocket():
    U = undirected_view(load_sample("koramangala"))
    src = resolve_zone(U, "west")
    dst = resolve_zone(U, "ids:100,101,102,103")

    r = min_cut_between(U, src, dst)
    assert r["cut_size"] == 1                               # the lone approach road
    e = r["cut_edges"][0]
    assert {e["u"], e["v"]} == {27, 100}
    assert math.isclose(r["max_flow"], 600.0)               # tertiary-class capacity


def test_min_cut_capacity_equals_max_flow():
    U = undirected_view(load_sample("koramangala"))
    r = min_cut_between(U, resolve_zone(U, "west"), resolve_zone(U, "east"))
    assert r["max_flow"] > 0
    # max-flow / min-cut theorem: the cut we report must be a minimum cut.
    assert math.isclose(sum(e["capacity"] for e in r["cut_edges"]), r["max_flow"], rel_tol=1e-6)
