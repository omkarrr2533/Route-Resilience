"""Graph -> GeoJSON, the lingua franca between the compute service and Leaflet.

We emit one FeatureCollection of LineString edges (carrying every score so the dashboard can
switch measures client-side without a round-trip) and one of Point features for the
articulation points worth flagging.
"""

from __future__ import annotations


def edges_to_geojson(U, per_edge):
    """Serialize undirected edges. ``per_edge`` maps canonical (sorted) edge -> properties."""
    features = []
    for u, v, data in U.edges(data=True):
        key = tuple(sorted((u, v)))
        props = {
            "u": u,
            "v": v,
            "highway": data.get("highway"),
            "length_m": round(data.get("length_m", 0.0), 1),
            "travel_time_s": round(data.get("travel_time_s", 0.0), 1),
        }
        props.update(per_edge.get(key, {}))
        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [U.nodes[u]["x"], U.nodes[u]["y"]],
                    [U.nodes[v]["x"], U.nodes[v]["y"]],
                ],
            },
        })
    return {"type": "FeatureCollection", "features": features}


def nodes_to_geojson(G, node_ids, kind):
    features = []
    for n in node_ids:
        features.append({
            "type": "Feature",
            "properties": {"id": n, "kind": kind},
            "geometry": {"type": "Point", "coordinates": [G.nodes[n]["x"], G.nodes[n]["y"]]},
        })
    return {"type": "FeatureCollection", "features": features}
