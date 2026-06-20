"""Impact-based criticality: remove a segment, measure what the network loses.

Centrality tells you a road *looks* important; impact tells you what breaks when it's
gone. We quantify three things after a removal:

  * global efficiency drop  -- average of 1/distance over all reachable pairs; the single
                               most honest "how much harder is it to get around now" number
  * largest-component shrink -- did we shed a chunk of the network entirely?
  * newly-disconnected pairs -- OD pairs that had a route and now don't

Unreachable pairs contribute 0 to efficiency (1/inf), which is exactly why efficiency
degrades gracefully instead of exploding to infinity the way mean shortest-path distance
does the moment one pair disconnects. That property is the whole reason we rank on
efficiency rather than on average travel time.
"""

from __future__ import annotations

import networkx as nx


def global_efficiency(G, weight="length"):
    """Mean inverse shortest-path distance over all ordered reachable pairs.

    O(V * (E + V log V)) — we run one Dijkstra per source. Fine per neighbourhood; for a
    full city this is the expensive call we cache in Redis and recompute only on change.
    """
    n = G.number_of_nodes()
    if n < 2:
        return 0.0

    total = 0.0
    for source, lengths in nx.all_pairs_dijkstra_path_length(G, weight=weight):
        for target, d in lengths.items():
            if target != source and d > 0:
                total += 1.0 / d
    return total / (n * (n - 1))


def removal_impact(G, u, v, key=None, weight="length", baseline_efficiency=None):
    """Score the damage from cutting edge (u, v).

    Returns a small report rather than a single number so the frontend can show *why* a
    segment scored high — efficiency loss vs. outright disconnection are very different
    failure stories and planners treat them differently.
    """
    if baseline_efficiency is None:
        baseline_efficiency = global_efficiency(G, weight=weight)
    base_lcc = _largest_component_size(G)

    H = G.copy()
    _drop_edge(H, u, v, key)

    after_eff = global_efficiency(H, weight=weight)
    after_lcc = _largest_component_size(H)

    eff_drop = baseline_efficiency - after_eff
    rel_drop = eff_drop / baseline_efficiency if baseline_efficiency else 0.0

    return {
        "edge": [u, v],
        "efficiency_before": baseline_efficiency,
        "efficiency_after": after_eff,
        "efficiency_drop": eff_drop,
        "relative_drop": rel_drop,
        "lcc_before": base_lcc,
        "lcc_after": after_lcc,
        "fragmented": after_lcc < base_lcc,        # removal carved off a piece
        "newly_disconnected_pairs": _disconnected_delta(G, H),
    }


def _drop_edge(G, u, v, key):
    if G.is_multigraph() and key is not None:
        G.remove_edge(u, v, key)
    else:
        G.remove_edge(u, v)


def _largest_component_size(G):
    if G.number_of_nodes() == 0:
        return 0
    components = (nx.weakly_connected_components(G) if G.is_directed()
                 else nx.connected_components(G))
    return max((len(c) for c in components), default=0)


def _disconnected_delta(G_before, G_after):
    """How many node pairs lost all connectivity. Uses component labels, not pairwise
    reachability, so it stays O(V + E) instead of O(V^2)."""
    before = _reachable_pairs(G_before)
    after = _reachable_pairs(G_after)
    return max(before - after, 0)


def _reachable_pairs(G):
    components = (nx.weakly_connected_components(G) if G.is_directed()
                 else nx.connected_components(G))
    return sum(len(c) * (len(c) - 1) for c in components)  # ordered pairs within each part
