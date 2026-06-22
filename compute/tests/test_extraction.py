"""Road extraction: the raster→graph pipeline has to recover topology from pixels, the
occlusion has to produce a real break (not a hand-removed edge), and the repair has to pull the
criticality ranking back up — even though the extracted graph has its own, geometry-only nodes.
"""

import networkx as nx
from fastapi.testclient import TestClient

from app.extraction.pipeline import extract_demo
from app.extraction.raster import rasterize_graph, tile_for_graph
from app.extraction.segment import synthesize_mask
from app.extraction.vectorize import skeletonize, vectorize
from app.main import app

client = TestClient(app)


def _t_graph():
    """A 'T': three endpoints and one junction."""
    G = nx.Graph()
    pts = {0: (77.6200, 12.9350), 1: (77.6240, 12.9350), 2: (77.6280, 12.9350), 3: (77.6240, 12.9320)}
    for n, (x, y) in pts.items():
        G.add_node(n, x=x, y=y)
    for u, v in [(0, 1), (1, 2), (1, 3)]:
        G.add_edge(u, v)
    return G


def test_skeleton_is_one_pixel_wide():
    G = _t_graph()
    tile = tile_for_graph(G, target_px=240)
    thick = rasterize_graph(G, tile, width_px=4)
    skel = skeletonize(thick)
    assert skel.sum() < thick.sum() / 2          # thinning removed the bulk of the road body


def test_vectorize_recovers_topology():
    G = _t_graph()
    tile = tile_for_graph(G, target_px=300)
    H = vectorize(rasterize_graph(G, tile, width_px=3), tile, prune_len_m=15)
    assert H.number_of_nodes() == 4 and H.number_of_edges() == 3
    assert sorted(dict(H.degree()).values()) == [1, 1, 1, 3]   # one junction, three dead-ends
    assert nx.is_connected(H)


def test_occlusion_burns_a_real_break_into_the_mask():
    # a single straight road; an occluder over the middle must split the vectorized centreline
    G = nx.Graph()
    G.add_node(0, x=77.6200, y=12.9340)
    G.add_node(1, x=77.6300, y=12.9340)
    G.add_edge(0, 1)
    tile = tile_for_graph(G, target_px=320)
    occ = [{"type": "canopy", "polygon": [[77.6245, 12.9335], [77.6255, 12.9335],
                                          [77.6255, 12.9345], [77.6245, 12.9345]]}]
    intact = vectorize(rasterize_graph(G, tile, 3), tile, prune_len_m=10)
    broken = vectorize(synthesize_mask(G, occ, tile, width_px=3, dropout=0, speckle=0, seed=0),
                       tile, prune_len_m=10)
    assert nx.is_connected(intact)
    assert nx.number_connected_components(broken) == 2     # the occluder severed the road


def test_pipeline_repair_lifts_apls_and_ranking():
    d = extract_demo()
    m = d["metrics"]
    # the extracted graph genuinely came from pixels: more nodes than ground truth
    assert m["counts"]["nodes_extracted"] > m["counts"]["nodes_gt"]
    assert m["counts"]["breaks_bridged"] >= 2
    # repair improves both topology agreement and the criticality ranking vs ground truth
    assert m["apls_repaired"] > m["apls_raw"]
    assert m["rho_repaired"] > m["rho_raw"]


def test_mask_is_a_png_data_url():
    d = extract_demo()
    assert d["mask"]["url"].startswith("data:image/png;base64,")
    assert len(d["mask"]["bounds"]) == 2


def test_extraction_endpoint():
    r = client.get("/api/extraction")
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"mask", "graphs", "overlays", "decisions", "metrics"}
    assert body["graphs"]["repaired"]["type"] == "FeatureCollection"
