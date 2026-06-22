"""The full loop, on a graph that genuinely came from pixels.

    ground-truth roads  →  rasterize  →  occlude + noise (the "satellite" mask)
                        →  vectorize (skeletonize → trace)  →  EXTRACTED graph
                        →  topological repair  →  REPAIRED graph
                        →  validate against ground truth (geometric APLS + criticality ranking)

This is what closes the gap the synthetic Repair Lab left open: the false breaks here are not
removed from a graph by hand — they are burned out of an image by an occluder and rediscovered
by the vectorizer, so the repair is operating on a real extracted topology. The only thing the
offline build fakes is the *imagery itself* (synthesized from OSM geometry instead of a Bhuvan
tile); swap ``synthesize_mask`` for ``segment.predict_mask`` on a real tile and the rest is
byte-for-byte identical.
"""

from __future__ import annotations

import networkx as nx

from app.extraction import validate
from app.extraction.raster import png_data_url, rasterize_graph, tile_for_graph
from app.extraction.segment import synthesize_mask
from app.extraction.vectorize import vectorize
from app.graph.build import annotate
from app.repair.demo import _edges_geojson, _log_entry, _overlays
from app.repair.repair import repair

# tile geography — a compact neighbourhood near Koramangala, real coords so it renders in place
LON0, LAT0 = 77.6200, 12.9300
DLON, DLAT = 0.00160, 0.00150


def extract_demo():
    gt, occluders = _tile_scenario()

    tile = tile_for_graph(gt, target_px=400)
    extracted_mask = synthesize_mask(gt, occluders, tile, width_px=3, seed=1)
    extracted = vectorize(extracted_mask, tile, prune_len_m=26.0)

    out = repair(extracted, occluders)
    repaired, decisions = out["graph"], out["decisions"]

    metrics = {
        "apls_raw": round(validate.geo_apls(extracted, gt), 3),
        "apls_repaired": round(validate.geo_apls(repaired, gt), 3),
        "rho_raw": round(validate.matched_rank_correlation(extracted, gt), 3),
        "rho_repaired": round(validate.matched_rank_correlation(repaired, gt), 3),
        "counts": {
            "nodes_gt": gt.number_of_nodes(),
            "edges_gt": gt.number_of_edges(),
            "nodes_extracted": extracted.number_of_nodes(),
            "edges_extracted": extracted.number_of_edges(),
            "components_extracted": nx.number_connected_components(extracted),
            "components_repaired": nx.number_connected_components(repaired),
            "breaks_bridged": sum(1 for d in decisions
                                  if d["kind"] == "break" and d["decision"] == "bridged"),
            "mask_road_px": int(extracted_mask.sum()),
        },
    }

    return {
        "mask": {"url": png_data_url(extracted_mask), "bounds": tile.bounds()},
        "occluders": occluders,
        "graphs": {
            "ground_truth": _edges_geojson(gt),
            "raw": _edges_geojson(extracted),
            "repaired": _edges_geojson(repaired),
        },
        "overlays": _overlays(repaired, decisions),
        "decisions": [_log_entry(d) for d in decisions],
        "metrics": metrics,
    }


def _tile_scenario():
    """A small ground-truth road network with two through-roads we'll occlude mid-segment. No
    flyover here on purpose: a 2D mask can't carry the overpass cue that disambiguates one, so
    the pixel demo owns the false-*break* mode and leaves false-*junction* to the synthetic
    scenario (where the OSM bridge tag is available)."""
    G = nx.Graph()

    def node(col, row):
        i = col * 10 + row
        if i not in G:
            G.add_node(i, x=round(LON0 + col * DLON, 6), y=round(LAT0 + row * DLAT, 6))
        return i

    def road(points, highway):
        for (c0, r0), (c1, r1) in zip(points, points[1:]):
            G.add_edge(node(c0, r0), node(c1, r1), highway=highway)

    road([(0, 1), (3, 1), (6, 1)], "secondary")          # Mill Road (E-W)
    road([(0, 3), (3, 3), (6, 3)], "primary")            # Park Road (E-W) — occluded east half
    road([(0, 1), (0, 3), (0, 5)], "secondary")          # West Avenue (N-S)
    road([(6, 1), (6, 3), (6, 5)], "secondary")          # East Avenue (N-S)
    road([(0, 5), (6, 5)], "secondary")                  # North Loop
    road([(3, 1), (3, 3)], "residential")                # Cross Street — occluded mid
    road([(0, 3), (3, 1)], "tertiary")                   # Link Road (diagonal, spreads betweenness)

    annotate(G)

    occluders = [
        {"type": "canopy", "polygon": _quad(4.5, 3.0, 0.62, 0.42)},   # over Park Road east half
        {"type": "shadow", "polygon": _quad(3.0, 2.0, 0.40, 0.55)},   # over Cross Street
    ]
    return G, occluders


def _quad(col, row, hw, hh):
    cx, cy = LON0 + col * DLON, LAT0 + row * DLAT
    dx, dy = hw * DLON, hh * DLAT
    return [
        [round(cx - dx, 6), round(cy - dy * 0.8, 6)],
        [round(cx + dx * 0.85, 6), round(cy - dy, 6)],
        [round(cx + dx, 6), round(cy + dy * 0.9, 6)],
        [round(cx - dx * 0.9, 6), round(cy + dy, 6)],
    ]
