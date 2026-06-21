"""Topological repair — the headline contribution (plan §2).

A post-processing layer that sits between graph extraction and the criticality engine and
undoes the two topology errors occlusion introduces. It is deliberately *evidence-gated* and
explainable: every decision it makes carries the reason it made it, so nothing is a black box
and the safeguard against hallucinating roads is visible, not implied.

Two operations, mirroring the two failure modes:

  1. Gap closure for false breaks. Find degree-1 dead-ends that face each other (close, and
     collinear so the road would genuinely continue straight), then bridge them — but *only*
     where an occluder plausibly explains the missing stretch. A gap with no canopy or shadow
     over it is left alone: there is no evidence a road was ever there, and inventing one would
     corrupt the very criticality scores this whole pipeline exists to get right.

  2. Flyover disambiguation for false junctions. A grade-separated crossing fused into a 4-way
     node has a geometric tell — two roads passing *through* with continuous heading — but so
     does an honest crossroads, so geometry alone can't separate them (the plan is explicit
     about this). The disambiguator splits a 4-way only when the through-geometry is corroborated
     by an overpass cue (a bridge/layer tag — in imagery, the elevation step). Honest crossroads
     keep their turn; the flyover gets its grade separation back.

The repair never sees the ground-truth graph or the answer key — it works from the damaged
extraction and the occluder layer alone, exactly as it would on a real tile.
"""

from __future__ import annotations

from math import cos, hypot, radians

from app.graph.build import haversine_m
from app.repair.occlusion import occluder_at

# A gap wider than this is almost certainly not a single occluded road segment; don't reach
# across it. Tuned to a few hundred metres — canopy and shadow gaps, not river crossings.
MAX_GAP_M = 320.0
# How straight the continuation must be. cos(35°) ≈ 0.82: the stub heading and the gap heading
# must agree to within ~35° at *both* ends before we'll believe one road continues across.
STRAIGHT_TOL = 0.82
# Two edges count as "passing through" a node if their headings are within ~25° of opposite.
THROUGH_TOL = -0.90


def repair(extracted, occluders):
    """Repair the extracted graph. Returns the repaired graph and a decision log.

    The input graph is left untouched; we work on a copy so the raw extraction stays available
    for the before/after comparison the validation needs.
    """
    H = extracted.copy()
    decisions = []

    _close_false_breaks(H, occluders, decisions)
    _disambiguate_flyovers(H, decisions)

    return {"graph": H, "decisions": decisions}


# ── 1. gap closure ──────────────────────────────────────────────────────────────────────
def _close_false_breaks(H, occluders, decisions):
    ends = [n for n in H if H.degree(n) == 1]

    # Every geometrically-plausible pair of dead-ends becomes a candidate; we sort the strong,
    # straight, short ones first and commit greedily so each dead-end is spent at most once.
    candidates = []
    for i, a in enumerate(ends):
        for b in ends[i + 1:]:
            gap = haversine_m(H.nodes[a]["y"], H.nodes[a]["x"], H.nodes[b]["y"], H.nodes[b]["x"])
            if gap > MAX_GAP_M:
                continue
            geom = _continuation(H, a, b)
            if geom is None:                       # a dead-end with no single stub to extend
                continue
            candidates.append((a, b, gap, geom))

    candidates.sort(key=lambda c: (-c[3]["score"], c[2]))   # most-collinear, then shortest
    spent = set()

    for a, b, gap, geom in candidates:
        if a in spent or b in spent:
            continue
        occ = occluder_at(geom["midpoint"], occluders)
        straight = geom["score"] >= STRAIGHT_TOL

        record = {
            "kind": "break",
            "ends": [a, b],
            "midpoint": geom["midpoint"],
            "gap_m": round(gap, 1),
            "straightness": round(geom["score"], 3),
            "occluder": occ,
        }

        if straight and occ:
            # Confirmed occlusion break — close it, following the incident road's class.
            H.add_edge(a, b, highway=geom["highway"], repaired=True, occluder=occ,
                       length=gap, length_m=gap)
            record["decision"] = "bridged"
            record["reason"] = f"collinear dead-ends under {occ}; gap {gap:.0f} m"
            spent.update((a, b))
        else:
            record["decision"] = "rejected"
            record["reason"] = ("ends not collinear" if not straight
                                else "no occluder over the gap — no evidence of a hidden road")
        decisions.append(record)


def _continuation(H, a, b):
    """Does the road at dead-end `a` head straight toward `b`, and vice-versa?

    Returns the collinearity score (the weaker of the two ends, in [-1, 1]; 1 = dead straight),
    the gap midpoint, and the road class to carry across — or None if either end isn't a clean
    single stub.
    """
    na, nb = _only_neighbour(H, a), _only_neighbour(H, b)
    if na is None or nb is None:
        return None

    da = _dot(_unit(H, na, a), _unit(H, a, b))     # stub a continues toward b
    db = _dot(_unit(H, nb, b), _unit(H, b, a))     # stub b continues toward a
    return {
        "score": min(da, db),
        "midpoint": [round((H.nodes[a]["x"] + H.nodes[b]["x"]) / 2, 6),
                     round((H.nodes[a]["y"] + H.nodes[b]["y"]) / 2, 6)],
        "highway": _stub_class(H, a) or _stub_class(H, b) or "residential",
    }


# ── 2. flyover disambiguation ───────────────────────────────────────────────────────────
def _disambiguate_flyovers(H, decisions):
    # Snapshot the 4-way nodes up front; splitting one rewires edges but never changes another
    # node's degree, so the list stays valid as we go.
    crossings = [n for n in H if H.degree(n) == 4]

    for n in crossings:
        pairs = _through_pairs(H, n)
        if pairs is None:
            continue                               # a genuine 4-way with no clean through-lines

        over = _overpass_pair(H, n, pairs)
        loc = [H.nodes[n]["x"], H.nodes[n]["y"]]

        if over is None:
            decisions.append({
                "kind": "crossing", "node": n, "location": loc,
                "decision": "kept",
                "reason": "two roads cross at grade — no overpass cue, so the turn is real",
            })
            continue

        under = pairs[0] if over is pairs[1] else pairs[1]
        new_node = _split_crossing(H, n, over, under)
        decisions.append({
            "kind": "crossing", "node": n, "new_node": new_node, "location": loc,
            "over": list(over), "under": list(under),
            "decision": "split",
            "reason": "grade-separated crossing — overpass tag confirms the fused turn is false",
        })


def _through_pairs(H, n):
    """Pair a 4-way node's neighbours into two near-opposite (collinear) through-lines, or None
    if the four arms don't resolve into two clean straight crossings."""
    nbrs = list(H[n])
    if len(nbrs) != 4:
        return None

    vecs = {m: _unit(H, n, m) for m in nbrs}
    first = nbrs[0]
    # The straightest partner for the first arm is the one pointing most nearly opposite.
    partner = min(nbrs[1:], key=lambda m: _dot(vecs[first], vecs[m]))
    rest = [m for m in nbrs[1:] if m != partner]

    pair_a = (first, partner)
    pair_b = (rest[0], rest[1])
    if _dot(vecs[pair_a[0]], vecs[pair_a[1]]) > THROUGH_TOL:
        return None
    if _dot(vecs[pair_b[0]], vecs[pair_b[1]]) > THROUGH_TOL:
        return None
    return (pair_a, pair_b)


def _overpass_pair(H, n, pairs):
    """Return whichever through-pair carries an overpass tag (the elevated road), or None when
    neither does — i.e. an honest at-grade intersection."""
    for pair in pairs:
        if all(_is_overpass(H[n][m]) for m in pair):
            return pair
    return None


def _split_crossing(H, n, over, under):
    """Lift the `over` road onto its own node, leaving `under` on the original — restoring the
    grade separation the extractor flattened away."""
    new_node = max(H.nodes) + 1
    # Nudge the lifted node a few metres off the crossing so the overpass reads as crossing-but-
    # not-connected rather than redrawing over the road below.
    H.add_node(new_node, x=H.nodes[n]["x"], y=round(H.nodes[n]["y"] + 0.00018, 6))
    for m in over:
        data = dict(H[n][m])
        H.remove_edge(n, m)
        H.add_edge(new_node, m, **data)
    return new_node


# ── small geometry helpers (local equirectangular frame; angles only, so the scale cancels) ─
def _unit(H, a, b):
    lat0 = radians(H.nodes[a]["y"])
    dx = (H.nodes[b]["x"] - H.nodes[a]["x"]) * cos(lat0)
    dy = (H.nodes[b]["y"] - H.nodes[a]["y"])
    norm = hypot(dx, dy) or 1.0
    return (dx / norm, dy / norm)


def _dot(p, q):
    return p[0] * q[0] + p[1] * q[1]


def _only_neighbour(H, n):
    nbrs = list(H[n])
    return nbrs[0] if len(nbrs) == 1 else None


def _stub_class(H, n):
    for _, data in H[n].items():
        return data.get("highway")
    return None


def _is_overpass(edge_data):
    return bool(edge_data.get("bridge")) or (edge_data.get("layer", 0) or 0) > 0
