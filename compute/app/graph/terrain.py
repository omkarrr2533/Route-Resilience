"""Elevation per node — the input the flood scenario needs.

With the geospatial stack we'd sample a real DEM (CartoDEM, the Indian elevation model from
Bhuvan) at each junction using rasterio. Offline we synthesize a plausible terrain: a low
"river" channel running across the neighbourhood that rises to either side, so some roads sit
lower and go under first. The numbers are invented but the *shape* is real — a gradient with a
low corridor — which is all the accessibility analysis downstream actually depends on.

When a DEM is available, swap `attach_elevation` for `sample_dem` (sketched below) and nothing
else in the flood pipeline changes.
"""

from __future__ import annotations

from math import sin

RIVER_LEVEL_M = 6.0      # elevation along the channel
RELIEF_M = 46.0          # how much higher the ridges sit above the channel


def attach_elevation(G):
    """Set a synthetic `elevation` (metres) on every node, in place. Idempotent."""
    if all("elevation" in d for _, d in G.nodes(data=True)):
        return G

    xs = [d["x"] for _, d in G.nodes(data=True)]
    ys = [d["y"] for _, d in G.nodes(data=True)]
    xlo, xhi = min(xs), max(xs)
    ylo, yhi = min(ys), max(ys)
    xspan = (xhi - xlo) or 1.0
    yspan = (yhi - ylo) or 1.0

    for _, d in G.nodes(data=True):
        u = (d["x"] - xlo) / xspan          # 0..1 west->east
        v = (d["y"] - ylo) / yspan          # 0..1 south->north
        # Distance from the SW-NE diagonal is the "distance from the river": low on the
        # channel, rising outward. A gentle ripple keeps it from looking like a ramp.
        from_river = abs(u - v)
        ripple = 0.05 * sin(6.28 * (u + v))
        d["elevation"] = round(RIVER_LEVEL_M + RELIEF_M * (from_river + ripple), 2)
    return G


def sample_dem(G, dem_path):
    """Sample a real DEM at each node (requires rasterio). The production path for CartoDEM.

    Intentionally importing rasterio lazily so the module loads fine without the geospatial
    stack; the offline `attach_elevation` is what the bundled samples use.
    """
    import rasterio

    with rasterio.open(dem_path) as dem:
        coords = [(d["x"], d["y"]) for _, d in G.nodes(data=True)]
        values = [v[0] for v in dem.sample(coords)]
    for (n, d), elev in zip(G.nodes(data=True), values):
        d["elevation"] = float(elev)
    return G
