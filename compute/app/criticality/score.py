"""Blend the individual measures into one explainable 0-100 criticality score.

Each measure answers a different question: betweenness ("how many routes use this"),
current-flow ("how much spread-out traffic leans on this"), impact ("what breaks if it's
gone"), and the structural flag ("is this a literal single point of failure"). A planner
shouldn't have to read four heatmaps, so we fold them into one number — but we keep the
breakdown attached to every edge so the score is auditable, not a black box. That
transparency is deliberate: "trust the 87" is a weak answer in an interview; "87, and here's
the 0.0–1.0 contribution from each of four measures" is the strong one.
"""

from __future__ import annotations

# Weights are a starting point, not gospel. Impact leads because "what actually breaks"
# beats "what looks central"; the structural bonus is a flat additive kicker so a bridge
# can never be ranked as low-criticality regardless of its flow numbers.
DEFAULT_WEIGHTS = {
    "betweenness": 0.30,
    "current_flow": 0.30,
    "impact": 0.40,
}
STRUCTURAL_BONUS = 15.0  # added (pre-clamp) when the edge is a bridge / cut edge


def resilience_scores(betweenness, current_flow, impact, bridges, weights=None):
    """Per-edge 0-100 score plus the normalised component breakdown.

    ``betweenness`` / ``current_flow`` are {edge: value}; ``impact`` is
    {edge: relative_efficiency_drop}; ``bridges`` is an iterable of edges. All edge keys are
    expected in the canonical (sorted-tuple) form the criticality modules emit.
    """
    weights = weights or DEFAULT_WEIGHTS
    bridge_set = {_canon(e) for e in bridges}

    bc_n = _normalize(betweenness)
    cf_n = _normalize(current_flow)
    im_n = _normalize(impact)

    out = {}
    edges = set(bc_n) | set(cf_n) | set(im_n)
    for e in edges:
        parts = {
            "betweenness": bc_n.get(e, 0.0),
            "current_flow": cf_n.get(e, 0.0),
            "impact": im_n.get(e, 0.0),
        }
        base = 100.0 * sum(weights[k] * parts[k] for k in weights)
        is_bridge = e in bridge_set
        score = min(100.0, base + (STRUCTURAL_BONUS if is_bridge else 0.0))
        out[e] = {
            "score": round(score, 2),
            "components": {k: round(v, 4) for k, v in parts.items()},
            "is_bridge": is_bridge,
        }
    return out


def _normalize(values):
    """Min-max to [0, 1]. A flat distribution (all-equal) maps to 0 — nothing stands out,
    so nothing is critical, which is the right answer rather than a divide-by-zero."""
    if not values:
        return {}
    lo = min(values.values())
    hi = max(values.values())
    span = hi - lo
    if span <= 0:
        return {e: 0.0 for e in values}
    return {e: (v - lo) / span for e, v in values.items()}


def _canon(edge):
    u, v = edge[0], edge[1]
    return tuple(sorted((u, v)))
