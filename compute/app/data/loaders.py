"""Graph sources. Two paths in, one MultiDiGraph out.

The whole system is designed so the core never depends on the heavy geospatial stack being
present. When osmnx + GDAL are installed (the Docker/Codespace path) we pull a real city
straight from OpenStreetMap. When they're not (plain Windows, CI, a quick demo) we load a
bundled sample neighbourhood from GeoJSON. Both routes return the same annotated graph, so
nothing downstream can tell the difference.
"""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from app.graph.build import annotate

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "data" / "samples"


def osmnx_available():
    try:
        import osmnx  # noqa: F401
        return True
    except Exception:
        return False


def load_place(place, network_type="drive"):
    """Pull a real road graph from OSM. Requires osmnx; raises if it isn't installed.

    Kept thin on purpose — osmnx already returns a clean, connected MultiDiGraph with x/y
    node coords and per-edge `length`, which is exactly our internal contract. We just
    re-annotate so travel times use *our* speed table rather than osmnx's maxspeed guesses.
    """
    import osmnx as ox

    G = ox.graph_from_place(place, network_type=network_type)
    return annotate(G)


def load_geojson(path):
    """Build a MultiDiGraph from a FeatureCollection of LineString road segments.

    Each edge feature carries `u`/`v` node ids in its properties; node coordinates come
    from the LineString endpoints. Two-way streets (oneway != true) get both directions so
    the directed analysis is honest about reachability.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    G = nx.MultiDiGraph()

    for feat in data["features"]:
        props = feat["properties"]
        coords = feat["geometry"]["coordinates"]
        u, v = props["u"], props["v"]
        (ux, uy), (vx, vy) = coords[0], coords[-1]

        G.add_node(u, x=ux, y=uy)
        G.add_node(v, x=vx, y=vy)

        attrs = {k: props[k] for k in ("highway", "name") if k in props}
        G.add_edge(u, v, **attrs)
        if not props.get("oneway", False):
            G.add_edge(v, u, **attrs)

    return annotate(G)


def available_samples():
    return sorted(p.stem for p in SAMPLE_DIR.glob("*.geojson"))


def load_sample(name):
    path = SAMPLE_DIR / f"{name}.geojson"
    if not path.exists():
        raise FileNotFoundError(
            f"No bundled sample '{name}'. Available: {available_samples()}"
        )
    return load_geojson(path)
