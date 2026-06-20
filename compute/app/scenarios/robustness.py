"""Robustness curves: how fast does the network fall apart under attack?

We pull edges out one batch at a time and watch the largest connected component (LCC)
shrink. Two attack orders:

  * targeted -- remove highest-criticality edges first (an adversary, or the worst-case
                failure: the important roads are exactly the ones that flood / get closed)
  * random   -- remove edges in random order (the baseline: bad luck, not bad intent)

The gap between the two curves *is* the vulnerability signature. A network that collapses
under targeted removal but shrugs off random removal is fragile in a structured way — it
has critical arteries. We summarise each curve by the area under it (trapezoidal): higher
AUC = the giant component survived longer = more robust.

For an honest targeted attack we re-rank after each batch (an "adaptive" adversary), because
removing the top road changes which road is now most central. Recomputing every single
removal is too slow on a city graph, so we re-rank per batch — standard practice in the
percolation literature.
"""

from __future__ import annotations

import random

import networkx as nx

from app.criticality.betweenness import edge_betweenness


def robustness_curve(G, strategy="targeted", steps=20, weight="length", seed=7):
    """Return the LCC-vs-fraction-removed curve and its AUC.

    ``steps`` batches of edges are removed; ``strategy`` is "targeted" or "random".
    The graph is treated as undirected for component counting (connectivity is undirected).
    """
    H = G.to_undirected() if G.is_directed() else G.copy()
    n0 = H.number_of_nodes()
    m0 = H.number_of_edges()
    if m0 == 0 or n0 == 0:
        return {"strategy": strategy, "fractions": [], "lcc": [], "auc": 0.0}

    rng = random.Random(seed)
    batch = max(1, m0 // steps)

    fractions = [0.0]
    lcc = [_lcc_fraction(H, n0)]

    removed = 0
    if strategy == "random":
        order = list(H.edges())
        rng.shuffle(order)
        cursor = 0

    while H.number_of_edges() > 0:
        if strategy == "targeted":
            # Re-rank the survivors, then knock out this batch's worst edges.
            ranking = edge_betweenness(H, weight=weight, normalized=False)
            victims = [e for e, _ in sorted(ranking.items(), key=lambda kv: kv[1], reverse=True)[:batch]]
        else:
            victims = order[cursor:cursor + batch]
            cursor += batch
            if not victims:
                break

        for u, v in victims:
            if H.has_edge(u, v):
                H.remove_edge(u, v)
                removed += 1

        fractions.append(removed / m0)
        lcc.append(_lcc_fraction(H, n0))

    return {
        "strategy": strategy,
        "fractions": fractions,
        "lcc": lcc,
        "auc": _auc(fractions, lcc),
    }


def _lcc_fraction(G, n0):
    if G.number_of_nodes() == 0:
        return 0.0
    largest = max((len(c) for c in nx.connected_components(G)), default=0)
    return largest / n0


def _auc(xs, ys):
    """Trapezoidal area under the (fraction, lcc) curve."""
    area = 0.0
    for i in range(1, len(xs)):
        area += (xs[i] - xs[i - 1]) * (ys[i] + ys[i - 1]) / 2.0
    return area
