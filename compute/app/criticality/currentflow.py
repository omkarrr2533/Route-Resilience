"""Current-flow (random-walk) edge betweenness.

Shortest-path betweenness assumes every trip takes an optimal route. Real traffic doesn't —
it spreads across alternatives. Current-flow betweenness models the network as a resistor
grid: inject one unit of current at s, draw it out at t, and an edge's score is the current
it carries, averaged over all s-t pairs. Messina et al. found this tracks real road-network
disruption better than shortest-path centrality, which is why it's a centrepiece measure
here and not an afterthought.

Maths (Newman 2005; Brandes & Fleischer 2005): with graph Laplacian L and unit current
injected by the vector b_{st} = e_s - e_t, node potentials are V = L^+ b_{st}. The current
on edge (i, j) is c_ij (V_i - V_j). Summed over all pairs and normalised by the pair count,
that's the betweenness.

The trick that makes it affordable: fix an edge (i, j) and let f_k = M_{i,k} - M_{j,k} where
M = L^+. Then the current for pair (s, t) is c_ij (f_s - f_t), and the per-edge sum over all
pairs collapses to sum_{s<t} |f_s - f_t| — the pairwise absolute difference of a vector,
which a sort evaluates in O(n log n). So the whole thing is one pseudoinverse plus a sort
per edge. Only numpy required.
"""

from __future__ import annotations

import numpy as np
import networkx as nx


def current_flow_edge_betweenness(G, weight="length", normalized=True):
    """Current-flow betweenness for each undirected edge, computed per component.

    Current flow is only defined inside a connected component (no current crosses a cut),
    so we solve each component independently and merge the results. Edges in trivial
    (1- or 2-node) components score 0.
    """
    scores = {}
    components = (G.subgraph(c) for c in nx.connected_components(G))
    for comp in components:
        if comp.number_of_nodes() < 3:
            scores.update({_key(u, v): 0.0 for u, v in comp.edges()})
            continue
        scores.update(_component_betweenness(comp, weight, normalized))
    return scores


def _component_betweenness(G, weight, normalized):
    nodes = list(G.nodes())
    index = {v: i for i, v in enumerate(nodes)}
    n = len(nodes)

    M = _laplacian_pinv(G, nodes, index, weight)  # pseudoinverse of the Laplacian

    pair_norm = 1.0 / ((n - 1) * (n - 2)) if normalized and n > 2 else 1.0

    scores = {}
    for u, v in G.edges():
        c = _conductance(G, u, v, weight)
        i, j = index[u], index[v]
        f = M[i, :] - M[j, :]               # potential drop across (u, v) per source/sink
        scores[_key(u, v)] = c * _sum_abs_pairwise(f) * pair_norm
    return scores


def _laplacian_pinv(G, nodes, index, weight):
    """Moore-Penrose pseudoinverse of the weighted (conductance) Laplacian.

    The Laplacian is rank-deficient by one (the all-ones vector is in its null space), so a
    plain inverse doesn't exist — pinv gives the unique solution orthogonal to that null
    space, which is exactly the grounded-potential convention we want.
    """
    n = len(nodes)
    L = np.zeros((n, n))
    for u, v in G.edges():
        c = _conductance(G, u, v, weight)
        i, j = index[u], index[v]
        L[i, i] += c
        L[j, j] += c
        L[i, j] -= c
        L[j, i] -= c
    return np.linalg.pinv(L)


def _conductance(G, u, v, weight):
    # Resistance is proportional to road length; conductance is its reciprocal. A longer
    # road resists flow more, so current prefers short links — the physically sensible
    # behaviour. Missing/zero lengths fall back to unit conductance.
    if weight is None:
        return 1.0
    data = G.get_edge_data(u, v)
    if G.is_multigraph():
        length = min(d.get(weight, 1.0) for d in data.values())
    else:
        length = data.get(weight, 1.0)
    return 1.0 / length if length and length > 0 else 1.0


def _sum_abs_pairwise(f):
    """sum_{s<t} |f_s - f_t| in O(n log n) via the sorted-prefix identity."""
    s = np.sort(f)
    n = len(s)
    # Each sorted value contributes (rank-weighted) to the total of absolute differences.
    weights = np.arange(n) - (n - 1 - np.arange(n))
    return float(np.dot(weights, s))


def _key(u, v):
    return tuple(sorted((u, v)))
