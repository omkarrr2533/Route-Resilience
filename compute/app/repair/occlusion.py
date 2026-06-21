"""A synthetic occlusion scenario — a road network with *known* ground truth, the damage a
2D road-extractor inflicts on it, and the labels needed to score a repair.

The whole point of Tier 3 is measurable: you can only report repair precision/recall, and the
downstream criticality-ranking accuracy, if you hold the answer key (plan §8). On a real
satellite tile that key is a hand-traced label we can't bundle here, so we synthesize the same
situation honestly — a true graph, a few occluders (tree canopy, building shadow) and one
flyover — and then *derive* the extracted graph by applying exactly the two failure modes the
plan describes:

  • false break    — an occluder hides the middle of a real road, so the extractor emits two
                     dangling dead-ends where there was one continuous through-road.
  • false junction — a flyover crosses a road in 2D; occlusion-blind vectorization fuses the
                     grade-separated crossing into a 4-way intersection, inventing a turn the
                     concrete never allowed.

Deriving the damage from ground truth (rather than hand-authoring a separate "extracted"
graph) is what gives us perfect labels for free: we know precisely which gaps are real breaks,
which gap only *looks* like one (the decoy across a park — no road there to recover), and which
4-way node is the flyover versus an honest at-grade crossroads.

Geometry note: everything lives in real WGS84 lon/lat near Koramangala so it renders over the
right basemap tiles; the topology is invented but plausible.
"""

from __future__ import annotations

import networkx as nx

from app.graph.build import annotate

# Anchor + grid pitch. ~159 m east-west and ~155 m north-south per cell at this latitude —
# a compact neighbourhood, so an occlusion gap of one cell reads clearly at street zoom.
LON0, LAT0 = 77.6210, 12.9330
DLON, DLAT = 0.00150, 0.00140


def _nid(col, row):
    # Stable, human-legible ids: col*10 + row (rows stay < 10, so no collisions). Handy when
    # a segment shows up in the UI as "34–44" — you can read the geometry straight off the id.
    return col * 10 + row


def _ll(col, row):
    return [round(LON0 + col * DLON, 6), round(LAT0 + row * DLAT, 6)]


# The flyover's elevated node sits a touch north of where it crosses the road below, so the
# span visibly bows over in the ground-truth render. The extractor will snap it down onto the
# crossing (that snap *is* the false junction).
_OVER_NODE = 991
_OVER_LL = [round(LON0 + 3 * DLON, 6), round(LAT0 + 1 * DLAT + 0.00018, 6)]


def build_scenario():
    """Return the ground-truth graph, the occlusion-damaged extraction, the occluder polygons,
    and the label key — everything the repair and its validation need."""
    G = nx.Graph()

    def node(col, row):
        i = _nid(col, row)
        if i not in G:
            lon, lat = _ll(col, row)
            G.add_node(i, x=lon, y=lat)
        return i

    def road(points, highway, name=None, **extra):
        prev = None
        for col, row in points:
            cur = node(col, row)
            if prev is not None:
                G.add_edge(prev, cur, highway=highway, name=name, **extra)
            prev = cur

    # ── the through-network: two E-W arteries, two ring roads, four N-S streets ──────────
    road([(c, 0) for c in range(9)], "secondary", "South Ring")
    road([(c, 1) for c in range(9)], "secondary", "Mill Road")
    road([(c, 4) for c in range(9)], "primary", "Canopy Avenue")     # the arterial
    road([(c, 6) for c in range(9)], "secondary", "North Ring")
    road([(0, r) for r in range(7)], "secondary", "West Ring")
    road([(2, r) for r in range(7)], "residential", "Pump House Rd")
    road([(6, r) for r in range(7)], "secondary", "Shadow Street")
    road([(8, r) for r in range(7)], "secondary", "East Ring")

    # ── the flyover: South Ring → up over Mill Road → Canopy Avenue ──────────────────────
    # Mill Road runs continuously through node (3,1). The skyway crosses *above* it on its own
    # elevated node, with no turn between them. The two elevated spans carry the overpass tag —
    # the only thing, geometrically, that distinguishes this crossing from an honest 4-way.
    m31 = node(3, 1)
    G.add_node(_OVER_NODE, x=_OVER_LL[0], y=_OVER_LL[1])
    n30, n32 = node(3, 0), node(3, 2)
    G.add_edge(n30, _OVER_NODE, highway="primary", name="MG Skyway", bridge=True, layer=1)
    G.add_edge(_OVER_NODE, n32, highway="primary", name="MG Skyway", bridge=True, layer=1)
    road([(3, 2), (3, 3), (3, 4)], "primary", "MG Skyway")           # back down to grade

    # ── two decoy stubs facing each other across a park — collinear, close, but NOT a road ──
    # In truth these are unrelated cul-de-sacs; there is nothing to recover between them. A
    # geometry-only bridger would happily (and wrongly) connect them. The occluder gate is what
    # must stop it: there is no canopy or shadow here to explain a "missing" road.
    road([(1, 1), (1, 2)], "residential", "Maple Cul-de-sac")
    road([(1, 4), (1, 3)], "residential", "Park Edge Close")

    annotate(G)
    ground_truth = G

    # ── occluders: irregular quads over the two stretches we're about to hide ─────────────
    occluders = [
        {"type": "canopy", "polygon": _quad(4.45, 4.0, 0.55, 0.42)},
        {"type": "shadow", "polygon": _quad(6.0, 2.5, 0.46, 0.62)},
    ]

    # ── derive the extracted graph: apply the two failure modes to a copy of ground truth ──
    extracted = ground_truth.copy()

    real_breaks = [
        {"u": _nid(4, 4), "v": _nid(5, 4), "occluder": "canopy"},   # Canopy Avenue, mid-span
        {"u": _nid(6, 2), "v": _nid(6, 3), "occluder": "shadow"},   # Shadow Street, mid-span
    ]
    for b in real_breaks:
        extracted.remove_edge(b["u"], b["v"])

    # Fuse the flyover: every elevated edge collapses onto the road-below node, and the elevated
    # node disappears. The result is a single 4-way junction carrying an overpass tag.
    fused = _fuse_flyover(extracted, over=_OVER_NODE, ground=m31)

    labels = {
        "real_break_gaps": [frozenset((b["u"], b["v"])) for b in real_breaks],
        "decoy_gaps": [frozenset((_nid(1, 2), _nid(1, 3)))],
        "flyover_node": fused,                       # the one 4-way that must be split
        "at_grade_nodes": _degree4_nodes(extracted) - {fused},
    }

    return {
        "ground_truth": ground_truth,
        "extracted": extracted,
        "occluders": occluders,
        "labels": labels,
    }


def _fuse_flyover(G, over, ground):
    """Collapse the elevated node `over` onto the road-below node `ground`, carrying its edges
    (and their overpass tags) across. Returns the surviving fused node id."""
    for nbr, data in list(G[over].items()):
        G.add_edge(ground, nbr, **data)
    G.remove_node(over)
    return ground


def _degree4_nodes(G):
    return {n for n in G if G.degree(n) == 4}


def _quad(col, row, half_w, half_h):
    """A slightly skewed quad around a grid point — occluders aren't axis-aligned rectangles."""
    cx, cy = LON0 + col * DLON, LAT0 + row * DLAT
    dx, dy = half_w * DLON, half_h * DLAT
    return [
        [round(cx - dx, 6), round(cy - dy * 0.8, 6)],
        [round(cx + dx * 0.85, 6), round(cy - dy, 6)],
        [round(cx + dx, 6), round(cy + dy * 0.9, 6)],
        [round(cx - dx * 0.9, 6), round(cy + dy, 6)],
    ]


def point_in_polygon(point, polygon):
    """Ray-casting point-in-polygon. `point` is [lon, lat]; `polygon` a list of [lon, lat]
    rings (no need to repeat the first vertex). Works for the convex-ish occluder quads here
    and for any arbitrary land-cover polygon a real occlusion layer would hand us."""
    x, y = point
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def occluder_at(point, occluders):
    """Which occluder, if any, covers this point — the evidence that gates a bridge."""
    for occ in occluders:
        if point_in_polygon(point, occ["polygon"]):
            return occ["type"]
    return None
