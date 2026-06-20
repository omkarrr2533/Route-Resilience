"""Generate the bundled sample road graph used when osmnx isn't available.

Run it two ways:

    python data/make_sample.py                 # synthesize the offline Koramangala sample
    python data/make_sample.py --place "Koramangala, Bengaluru"   # snapshot the real OSM graph

The synthetic network is a lightly-perturbed street grid with three features that make the
criticality engine show something interesting on first run: a `primary` arterial through the
middle, a couple of one-way segments, and an east-side pocket joined to the rest of the
neighbourhood by a *single* connector — a textbook bridge whose junction is an articulation
point. Coordinates are real (centred on Koramangala) so it renders in the right place on the
map; the topology is invented but plausible.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / "samples"

CENTER_LAT, CENTER_LON = 12.9352, 77.6245
ROWS, COLS = 6, 7
DLAT, DLON = 0.0034, 0.0040          # ~375 m x ~430 m grid pitch at this latitude
JITTER = 0.00045                      # nudge nodes off the perfect grid


def synthesize(seed=7):
    rng = random.Random(seed)
    nodes = {}        # id -> (lon, lat)
    edges = []        # (u, v, highway, oneway, name)

    def nid(r, c):
        return r * COLS + c

    # --- grid nodes -------------------------------------------------------------------
    for r in range(ROWS):
        for c in range(COLS):
            lon = CENTER_LON + (c - COLS / 2) * DLON + rng.uniform(-JITTER, JITTER)
            lat = CENTER_LAT + (ROWS / 2 - r) * DLAT + rng.uniform(-JITTER, JITTER)
            nodes[nid(r, c)] = (round(lon, 6), round(lat, 6))

    mid = ROWS // 2

    def klass(r, c, horizontal):
        if horizontal and r == mid:
            return "primary"                 # the arterial
        if r in (0, ROWS - 1) or c in (0, COLS - 1):
            return "secondary"               # ring roads
        return "residential"

    # --- grid edges, with a few interior gaps so it isn't a perfect lattice -----------
    drop = {(2, 3, "h"), (4, 2, "v"), (1, 5, "v"), (3, 1, "h")}
    for r in range(ROWS):
        for c in range(COLS):
            if c + 1 < COLS and (r, c, "h") not in drop:
                oneway = (r == mid and c in (2, 3))   # a one-way stretch on the arterial
                edges.append((nid(r, c), nid(r, c + 1), klass(r, c, True), oneway,
                              "MG Arterial" if r == mid else None))
            if r + 1 < ROWS and (r, c, "v") not in drop:
                edges.append((nid(r, c), nid(r + 1, c), klass(r, c, False), False, None))

    # --- a couple of diagonal connectors (spreads the betweenness around) -------------
    for (r1, c1, r2, c2) in [(1, 1, 2, 2), (3, 4, 4, 5)]:
        edges.append((nid(r1, c1), nid(r2, c2), "tertiary", False, None))

    # --- the east pocket: four nodes hanging off ONE bridge edge ----------------------
    anchor = nid(mid, COLS - 1)
    base_lon, base_lat = nodes[anchor]
    pocket = []
    for i in range(4):
        pid = 100 + i
        nodes[pid] = (round(base_lon + 0.0042 + i * 0.0026, 6),
                      round(base_lat - 0.0030 + (i % 2) * 0.0024, 6))
        pocket.append(pid)
    # internal pocket streets
    edges.append((pocket[0], pocket[1], "residential", False, "Lake View Layout"))
    edges.append((pocket[1], pocket[2], "residential", False, "Lake View Layout"))
    edges.append((pocket[2], pocket[3], "residential", False, None))
    edges.append((pocket[0], pocket[3], "residential", False, None))
    # the lone bridge — sever this and the whole pocket goes dark
    edges.append((anchor, pocket[0], "tertiary", False, "Pocket Approach Rd"))

    return nodes, edges


def to_geojson(nodes, edges):
    features = []
    for u, v, highway, oneway, name in edges:
        props = {"u": u, "v": v, "highway": highway, "oneway": bool(oneway)}
        if name:
            props["name"] = name
        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": {
                "type": "LineString",
                "coordinates": [list(nodes[u]), list(nodes[v])],
            },
        })
    return {"type": "FeatureCollection", "features": features}


def from_osm(place, network_type):
    """Snapshot a real OSM graph to the same GeoJSON shape. Needs osmnx installed."""
    import osmnx as ox

    G = ox.graph_from_place(place, network_type=network_type)
    nodes = {n: (d["x"], d["y"]) for n, d in G.nodes(data=True)}
    edges = []
    for u, v, d in G.edges(data=True):
        hw = d.get("highway")
        if isinstance(hw, list):
            hw = hw[0]
        edges.append((u, v, hw or "unclassified", bool(d.get("oneway", False)), d.get("name")))
    return nodes, edges


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", help="OSM place name; omit to synthesize")
    ap.add_argument("--network-type", default="drive")
    ap.add_argument("--name", default="koramangala")
    args = ap.parse_args()

    if args.place:
        nodes, edges = from_osm(args.place, args.network_type)
    else:
        nodes, edges = synthesize()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{args.name}.geojson"
    out.write_text(json.dumps(to_geojson(nodes, edges), indent=1), encoding="utf-8")
    print(f"wrote {out}  ({len(nodes)} nodes, {len(edges)} edges)")


if __name__ == "__main__":
    main()
