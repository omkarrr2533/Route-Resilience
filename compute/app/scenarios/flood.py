"""Flood scenario, framed around access to critical services — not bare connectivity.

The naive way to score a flood is the giant-component / percolation framing: how much of the
network falls off. The flood literature (e.g. Nature Scientific Reports) shows that's the
*wrong* question for floods — what matters is **accessibility to critical services**: after the
water rises, how many people can no longer drive to a hospital, and which pockets get cut off?
This module is built around that question on purpose; it's the design choice that signals the
actual problem was understood, not just "remove edges, measure LCC".

Three outputs:
  * which road segments go under at a given water level (low point submerged)
  * which junctions lose all road access to every hospital
  * a restoration priority list — clear *these* segments first to reconnect the most people

Everything runs on the undirected projection with a per-node `elevation` (see graph.terrain).
"""

from __future__ import annotations

import networkx as nx


def default_hospitals(U, n_per_side=1):
    """Pick well-spread facilities on high ground when none are tagged.

    Real graphs carry amenity=hospital nodes; the synthetic sample doesn't, so we place
    hospitals on the highest ground in the west and east halves — somewhere that stays dry and
    forces the accessibility question to actually depend on which roads flood.
    """
    tagged = [n for n, d in U.nodes(data=True) if d.get("amenity") == "hospital"]
    if tagged:
        return tagged

    xs = [d["x"] for _, d in U.nodes(data=True)]
    mid = (min(xs) + max(xs)) / 2
    west = [n for n, d in U.nodes(data=True) if d["x"] < mid]
    east = [n for n, d in U.nodes(data=True) if d["x"] >= mid]
    high = lambda group: sorted(group, key=lambda n: U.nodes[n]["elevation"], reverse=True)
    return high(west)[:n_per_side] + high(east)[:n_per_side]


def flooded_edges(U, level):
    """Segments whose low point is under water (min endpoint elevation < level)."""
    out = []
    for u, v in U.edges():
        if min(U.nodes[u]["elevation"], U.nodes[v]["elevation"]) < level:
            out.append((u, v))
    return out


def _with_access(U, hospitals):
    """Set of nodes that can still reach at least one hospital."""
    hosp = set(hospitals)
    reachable = set()
    for comp in nx.connected_components(U):
        if comp & hosp:
            reachable |= comp
    return reachable


def flood_impact(U, level, hospitals=None):
    hospitals = hospitals or default_hospitals(U)
    submerged = flooded_edges(U, level)

    H = U.copy()
    H.remove_edges_from(submerged)

    before = _with_access(U, hospitals)
    after = _with_access(H, hospitals)
    lost = before - after

    total = U.number_of_nodes()
    return {
        "level": level,
        "hospitals": list(hospitals),
        "submerged": submerged,
        "submerged_count": len(submerged),
        "lost_access_nodes": sorted(lost),
        "lost_access_count": len(lost),
        "lost_access_fraction": round(len(lost) / total, 4) if total else 0.0,
        "with_access_after": len(after),
        "nodes_total": total,
    }


def restoration_priority(U, level, hospitals=None, k=5):
    """Greedy: which submerged segments to reopen first to restore the most lost access.

    Classic max-coverage greedy — at each step reopen the single flooded edge that hands the
    largest number of currently-cut-off junctions a route back to a hospital. Greedy isn't
    optimal for set-cover, but it's the standard, defensible heuristic and the ranking it
    produces is exactly the "clear these N roads first" deliverable a disaster cell wants.
    """
    hospitals = hospitals or default_hospitals(U)
    submerged = flooded_edges(U, level)

    H = U.copy()
    H.remove_edges_from(submerged)

    cut_off = set(U.nodes()) - _with_access(H, hospitals)
    remaining = list(submerged)
    picks = []

    while cut_off and remaining and len(picks) < k:
        best, best_gain, best_cut = None, 0, None
        for u, v in remaining:
            data = U.get_edge_data(u, v)
            H.add_edge(u, v, **data)
            after = set(U.nodes()) - _with_access(H, hospitals)
            gain = len(cut_off) - len(after)
            H.remove_edge(u, v)
            if gain > best_gain:
                best, best_gain, best_cut = (u, v), gain, after

        if best is None:
            break                          # no remaining edge helps (rest is deeper inland)
        H.add_edge(*best, **U.get_edge_data(*best))
        picks.append({"u": best[0], "v": best[1], "restores": best_gain})
        cut_off = best_cut
        remaining.remove(best)

    return picks
