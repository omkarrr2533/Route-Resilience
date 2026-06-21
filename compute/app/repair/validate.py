"""Does the repair actually help? Three measurements, the third being the one that matters.

  • APLS-style path agreement — the standard road-graph topology metric. We sample node pairs
    that are connected in the ground truth and compare their shortest-path length in the
    candidate graph; a missing or detoured route costs score. Reported 0–1, higher is better.

  • Repair precision/recall — of the gaps the repair closed, how many were real breaks versus
    mistakes (the decoy); of the real breaks, how many it caught. Plus whether the flyover was
    split while honest crossroads were left intact.

  • Criticality-ranking accuracy — *the* claim (plan §8). We rank every junction by criticality
    (node betweenness) on the ground-truth graph, then ask how well that ranking is reproduced
    on the raw extraction versus on the repaired graph, via Spearman's rank correlation. The
    headline result is the jump: the false breaks and the false flyover-turn scramble the raw
    ranking; repair pulls it back toward ground truth. A prettier map is incidental — recovering
    the *ranking* is the point of the whole pipeline.

Spearman is written out by hand (rank, then Pearson on the ranks) rather than pulled from
scipy — it keeps the core dependency-light, and it's three lines of honest arithmetic.
"""

from __future__ import annotations

from math import sqrt

import networkx as nx


def apls_score(candidate, ground_truth, weight="length"):
    """Single-direction APLS over the node set shared by both graphs."""
    shared = [n for n in ground_truth if n in candidate]
    gt_len = dict(nx.all_pairs_dijkstra_path_length(ground_truth, weight=weight))
    cand_len = dict(nx.all_pairs_dijkstra_path_length(candidate, weight=weight))

    total, scored = 0.0, 0
    for i, s in enumerate(shared):
        for t in shared[i + 1:]:
            lg = gt_len.get(s, {}).get(t)
            if lg is None:                       # unreachable in ground truth → not scored
                continue
            scored += 1
            lp = cand_len.get(s, {}).get(t)
            if lp is None:                       # candidate lost the route entirely
                continue
            total += max(0.0, 1.0 - abs(lp - lg) / lg)
    return total / scored if scored else 1.0


def criticality_rank_correlation(candidate, ground_truth, weight="length"):
    """Spearman correlation of junction criticality (node betweenness) between the candidate
    graph and ground truth, over their shared nodes."""
    bc_gt = nx.betweenness_centrality(ground_truth, weight=weight, normalized=True)
    bc_cd = nx.betweenness_centrality(candidate, weight=weight, normalized=True)

    shared = [n for n in ground_truth if n in candidate]
    return spearman([bc_gt[n] for n in shared], [bc_cd[n] for n in shared])


def repair_quality(decisions, labels):
    """Precision/recall of the gap-closure decisions, plus the flyover verdict."""
    real = set(labels["real_break_gaps"])
    decoy = set(labels["decoy_gaps"])

    bridged = {frozenset(d["ends"]) for d in decisions
               if d["kind"] == "break" and d["decision"] == "bridged"}
    tp = len(bridged & real)
    fp = len(bridged - real)                     # closed a gap that was no real break
    fn = len(real - bridged)                     # missed a real break

    split = {d["node"] for d in decisions if d["kind"] == "crossing" and d["decision"] == "split"}
    at_grade = set(labels["at_grade_nodes"])

    return {
        "precision": _ratio(tp, tp + fp),
        "recall": _ratio(tp, tp + fn),
        "bridged": tp + fp,
        "real_breaks": len(real),
        "decoys_rejected": len(decoy - bridged) == len(decoy),
        "flyover_correct": labels["flyover_node"] in split and not (split & at_grade),
        "flyovers_split": len(split),
    }


# ── Spearman by hand ─────────────────────────────────────────────────────────────────────
def spearman(xs, ys):
    if len(xs) < 2:
        return 0.0
    return _pearson(_ranks(xs), _ranks(ys))


def _ranks(values):
    """Fractional ranks with ties averaged — so a plateau of equal criticalities doesn't bias
    the correlation."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0                # 1-based average rank across the tie block
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    va = sqrt(sum((x - ma) ** 2 for x in a))
    vb = sqrt(sum((y - mb) ** 2 for y in b))
    if va == 0 or vb == 0:
        return 0.0
    return cov / (va * vb)


def _ratio(num, den):
    return round(num / den, 3) if den else 1.0
