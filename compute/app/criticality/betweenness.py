"""Edge betweenness centrality via Brandes' algorithm.

We implement Brandes directly instead of calling ``networkx.edge_betweenness_centrality``
for two reasons: it documents that the math is understood (this is the segment-ranking
core of the whole system), and it lets us return the *raw* per-edge contribution dict in
the exact (u, v) key form the rest of the pipeline expects, with no surprises about how
NetworkX orders MultiGraph keys.

Reference: U. Brandes, "A faster algorithm for betweenness centrality", J. Math. Sociol.
25(2), 2001. The accumulation trick (back-propagating dependencies in order of
non-increasing distance) is what takes this from O(V^3) to O(VE) / O(VE + V^2 log V).
"""

from __future__ import annotations

import heapq
from collections import deque

import networkx as nx


def edge_betweenness(G, weight="length", normalized=True):
    """Betweenness of every edge: the fraction of shortest paths that ride over it.

    Works on Graph and DiGraph. For a directed graph each ordered pair (s, t) is a
    distinct path source, so we do *not* halve the totals the way we do for the
    undirected case. ``weight=None`` falls back to hop-count shortest paths (BFS),
    which is both faster and the right choice when edge lengths are missing.
    """
    betweenness = dict.fromkeys(_edge_keys(G), 0.0)

    for s in G.nodes():
        # Single-source shortest paths, recording predecessors and path counts.
        if weight is None:
            order, pred, sigma = _sssp_unweighted(G, s)
        else:
            order, pred, sigma = _sssp_dijkstra(G, s, weight)
        betweenness = _accumulate(betweenness, order, pred, sigma, s)

    return _rescale(betweenness, G, normalized)


def _edge_keys(G):
    # Undirected edges are stored once; (u, v) and (v, u) map to the same slot.
    if G.is_directed():
        return list(G.edges())
    return [tuple(sorted(e)) for e in G.edges()]


def _edge_slot(G, u, v):
    return (u, v) if G.is_directed() else tuple(sorted((u, v)))


def _sssp_unweighted(G, s):
    """BFS shortest paths. Returns (visit order, predecessors, path counts)."""
    pred = {v: [] for v in G}
    sigma = dict.fromkeys(G, 0.0)
    dist = dict.fromkeys(G, -1)
    sigma[s], dist[s] = 1.0, 0

    order = []
    q = deque([s])
    while q:
        v = q.popleft()
        order.append(v)
        for w in G[v]:
            if dist[w] < 0:                 # first time we reach w
                dist[w] = dist[v] + 1
                q.append(w)
            if dist[w] == dist[v] + 1:      # another shortest path into w
                sigma[w] += sigma[v]
                pred[w].append(v)
    return order, pred, sigma


def _sssp_dijkstra(G, s, weight):
    """Dijkstra with shortest-path counting. Edges must be non-negative."""
    pred = {v: [] for v in G}
    sigma = dict.fromkeys(G, 0.0)
    dist = {}
    sigma[s] = 1.0
    seen = {s: 0.0}

    order = []
    pq = [(0.0, s, s)]
    while pq:
        d, prev, v = heapq.heappop(pq)
        if v in dist:
            continue                        # already finalized
        dist[v] = d
        order.append(v)
        for w in G[v]:
            cost = d + _edge_weight(G, v, w, weight)
            if w not in dist and (w not in seen or cost < seen[w]):
                seen[w] = cost
                sigma[w] = sigma[v]
                pred[w] = [v]
                heapq.heappush(pq, (cost, v, w))
            elif _close(cost, seen.get(w)):  # equally-short alternative path
                sigma[w] += sigma[v]
                pred[w].append(v)
    return order, pred, sigma


def _accumulate(betweenness, order, pred, sigma, s):
    """Back-propagate dependencies (Brandes' delta) from the farthest node inward."""
    delta = dict.fromkeys(order, 0.0)
    for w in reversed(order):
        coeff = (1.0 + delta[w]) / sigma[w]
        for v in pred[w]:
            c = sigma[v] * coeff
            betweenness[_slot_for(betweenness, v, w)] += c
            delta[v] += c
    return betweenness


def _slot_for(betweenness, v, w):
    # The directed key is (v, w); for undirected graphs both orderings share a slot.
    if (v, w) in betweenness:
        return (v, w)
    return (w, v)


def _rescale(betweenness, G, normalized):
    n = G.number_of_nodes()
    if normalized and n > 2:
        # 1 / (number of ordered/unordered pairs) so scores are comparable across cities.
        scale = 1.0 / (n * (n - 1))
        if not G.is_directed():
            scale *= 2.0
    else:
        scale = 1.0
    half = 1.0 if G.is_directed() else 0.5  # undirected paths counted from both ends
    return {e: v * scale * half for e, v in betweenness.items()}


def _edge_weight(G, u, v, weight):
    data = G.get_edge_data(u, v)
    if G.is_multigraph():
        return min(d.get(weight, 1.0) for d in data.values())
    return data.get(weight, 1.0)


def _close(a, b, tol=1e-9):
    return b is not None and abs(a - b) <= tol


def edge_betweenness_networkx(G, weight="length", normalized=True):
    """Reference path used in tests to cross-check our Brandes implementation.

    NetworkX is battle-tested; we keep this around so a unit test can assert the two
    agree on small graphs. At city scale we prefer our version (and, eventually, the
    sampled approximation in scenarios/ for graphs too large for the exact O(VE) run).
    """
    raw = nx.edge_betweenness_centrality(G, weight=weight, normalized=normalized)
    return {_edge_slot(G, u, v): val for (u, v), val in raw.items()}
