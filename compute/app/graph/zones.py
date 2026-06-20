"""Resolve a human-friendly zone spec to a set of node ids for origin-destination analysis.

Max-flow needs two node sets (where trips start, where they end). Rather than make callers
hand-pick node ids, a zone is named:

    west / east / north / south   -> the outer slice of the network in that direction
    ids:12,27,30                  -> an explicit set (e.g. a chosen residential block)
    amenity:hospital              -> nodes tagged as that amenity (OSM graphs only)

The geographic slices are what make the bottleneck demo self-explanatory: "how much traffic
can cross from the west of the neighbourhood to the east, and where's the wall?"
"""

from __future__ import annotations

DIRECTIONS = {"west", "east", "north", "south"}


def resolve_zone(G, spec, frac=0.22):
    if spec.startswith("ids:"):
        wanted = {int(x) for x in spec[4:].split(",") if x.strip()}
        return [n for n in G.nodes() if n in wanted]

    if spec.startswith("amenity:"):
        tag = spec.split(":", 1)[1]
        return [n for n, d in G.nodes(data=True) if d.get("amenity") == tag]

    if spec in DIRECTIONS:
        return _directional(G, spec, frac)

    raise ValueError(f"Unknown zone '{spec}'. Use west/east/north/south, ids:..., or amenity:...")


def _directional(G, side, frac):
    xs = [d["x"] for _, d in G.nodes(data=True)]
    ys = [d["y"] for _, d in G.nodes(data=True)]
    xlo, xhi, ylo, yhi = min(xs), max(xs), min(ys), max(ys)

    if side == "west":
        cut = xlo + frac * (xhi - xlo)
        return [n for n, d in G.nodes(data=True) if d["x"] <= cut]
    if side == "east":
        cut = xhi - frac * (xhi - xlo)
        return [n for n, d in G.nodes(data=True) if d["x"] >= cut]
    if side == "south":
        cut = ylo + frac * (yhi - ylo)
        return [n for n, d in G.nodes(data=True) if d["y"] <= cut]
    # north
    cut = yhi - frac * (yhi - ylo)
    return [n for n, d in G.nodes(data=True) if d["y"] >= cut]
