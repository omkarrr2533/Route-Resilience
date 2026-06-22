"""Validating an *extracted* graph is harder than validating a repaired synthetic one: the
extractor invents its own nodes at its own pixel positions, so there is no shared id to join
on. You have to match by geometry — which is exactly why APLS exists.

  • ``match_nodes`` pairs each ground-truth junction with the nearest extracted node within a
    tolerance (a few pixels of slack for skeleton jitter).
  • ``geo_apls`` is APLS over those matches: sample ground-truth node pairs, look up the matched
    endpoints in the predicted graph, and compare shortest-path lengths.
  • ``matched_rank_correlation`` carries the criticality claim across the geometric gap: rank
    junctions by betweenness on each graph, then correlate over the matched pairs.

The point of all three: show that the topological repair recovers not just a connected map but
the criticality *ranking*, even when the graph came from pixels rather than from a clean OSM id
space.
"""

from __future__ import annotations

import networkx as nx

from app.graph.build import haversine_m
from app.repair.validate import spearman


def match_nodes(pred, gt, tol_m=40.0):
    """Map each ground-truth node to its nearest predicted node within `tol_m` (or drop it)."""
    matches = {}
    for g, gd in gt.nodes(data=True):
        best, best_d = None, tol_m
        for p, pd in pred.nodes(data=True):
            d = haversine_m(gd["y"], gd["x"], pd["y"], pd["x"])
            if d <= best_d:
                best, best_d = p, d
        if best is not None:
            matches[g] = best
    return matches


def geo_apls(pred, gt, tol_m=40.0, weight="length"):
    """APLS path-length agreement, with endpoints matched geometrically rather than by id."""
    matches = match_nodes(pred, gt, tol_m)
    gt_len = dict(nx.all_pairs_dijkstra_path_length(gt, weight=weight))
    pred_len = dict(nx.all_pairs_dijkstra_path_length(pred, weight=weight))

    nodes = [g for g in gt if g in matches]
    total, scored = 0.0, 0
    for i, s in enumerate(nodes):
        for t in nodes[i + 1:]:
            lg = gt_len.get(s, {}).get(t)
            if lg is None or lg == 0:
                continue
            scored += 1
            lp = pred_len.get(matches[s], {}).get(matches[t])
            if lp is None:
                continue
            total += max(0.0, 1.0 - abs(lp - lg) / lg)
    return total / scored if scored else 1.0


def matched_rank_correlation(pred, gt, tol_m=40.0, weight="length"):
    """Spearman of junction criticality (betweenness) over geometrically-matched node pairs."""
    bc_gt = nx.betweenness_centrality(gt, weight=weight, normalized=True)
    bc_pred = nx.betweenness_centrality(pred, weight=weight, normalized=True)
    matches = match_nodes(pred, gt, tol_m)
    if not matches:
        return 0.0
    xs = [bc_gt[g] for g in matches]
    ys = [bc_pred[matches[g]] for g in matches]
    return spearman(xs, ys)
