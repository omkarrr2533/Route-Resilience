"""Tier 3 — topological repair.

The properties that have to hold: the repair recovers ground-truth *topology*, it refuses the
decoy gap (no occluder = no road to invent), it splits the flyover while leaving honest
crossroads connected, and — the claim that matters — it pulls the criticality ranking back
toward ground truth.
"""

import networkx as nx
from fastapi.testclient import TestClient

from app.main import app
from app.repair import validate
from app.repair.demo import repair_demo
from app.repair.occlusion import build_scenario, occluder_at
from app.repair.repair import repair

client = TestClient(app)


def _run():
    scn = build_scenario()
    out = repair(scn["extracted"], scn["occluders"])
    return scn, out["graph"], out["decisions"]


def test_extraction_actually_damages_ground_truth():
    scn = build_scenario()
    gt, raw = scn["ground_truth"], scn["extracted"]
    assert nx.is_connected(gt)
    # two segments hidden, and the flyover's elevated node fused onto the road below
    assert raw.number_of_edges() == gt.number_of_edges() - 2
    assert raw.number_of_nodes() == gt.number_of_nodes() - 1


def test_repair_recovers_ground_truth_topology():
    scn, repaired, _ = _run()
    gt = scn["ground_truth"]
    assert repaired.number_of_nodes() == gt.number_of_nodes()
    assert repaired.number_of_edges() == gt.number_of_edges()
    # the strong statement: the repaired graph is structurally the ground-truth graph
    assert nx.is_isomorphic(repaired, gt)


def test_decoy_gap_is_refused():
    scn, _, decisions = _run()
    decoy = next(iter(scn["labels"]["decoy_gaps"]))
    match = [d for d in decisions if d["kind"] == "break" and frozenset(d["ends"]) == decoy]
    assert match, "the decoy gap should be considered as a candidate"
    assert match[0]["decision"] == "rejected"
    assert "no occluder" in match[0]["reason"]


def test_real_breaks_are_bridged_under_their_occluder():
    scn, _, decisions = _run()
    bridged = {frozenset(d["ends"]): d for d in decisions
               if d["kind"] == "break" and d["decision"] == "bridged"}
    for gap in scn["labels"]["real_break_gaps"]:
        assert gap in bridged
        assert bridged[gap]["occluder"] in ("canopy", "shadow")


def test_flyover_split_but_at_grade_crossings_kept():
    scn, _, decisions = _run()
    labels = scn["labels"]
    split = {d["node"] for d in decisions if d["kind"] == "crossing" and d["decision"] == "split"}
    kept = {d["node"] for d in decisions if d["kind"] == "crossing" and d["decision"] == "kept"}
    assert labels["flyover_node"] in split
    assert labels["at_grade_nodes"] <= kept          # every honest crossroads left intact
    assert not (split & labels["at_grade_nodes"])


def test_occluder_gate_geometry():
    scn = build_scenario()
    occ = scn["occluders"]
    canopy = next(o for o in occ if o["type"] == "canopy")
    centre = _centroid(canopy["polygon"])
    assert occluder_at(centre, occ) == "canopy"
    assert occluder_at([occ[0]["polygon"][0][0] - 1.0, 0.0], occ) is None   # far away: nothing


def test_repair_improves_criticality_ranking():
    scn, repaired, _ = _run()
    gt = scn["ground_truth"]
    raw_rho = validate.criticality_rank_correlation(scn["extracted"], gt)
    rep_rho = validate.criticality_rank_correlation(repaired, gt)
    # the headline: the repaired ranking tracks ground truth better than the raw one does
    assert rep_rho > raw_rho
    assert rep_rho > 0.99                            # topology recovered -> ranking recovered


def test_apls_improves():
    scn, repaired, _ = _run()
    gt = scn["ground_truth"]
    assert validate.apls_score(repaired, gt) >= validate.apls_score(scn["extracted"], gt)


def test_demo_payload_shape_and_metrics():
    demo = repair_demo()
    assert set(demo) >= {"occluders", "graphs", "overlays", "decisions", "metrics"}
    assert set(demo["graphs"]) == {"ground_truth", "raw", "repaired"}

    m = demo["metrics"]
    assert m["precision"] == 1.0 and m["recall"] == 1.0
    assert m["decoys_rejected"] is True and m["flyover_correct"] is True
    assert m["spearman_repaired"] > m["spearman_raw"]


def test_repair_endpoint():
    r = client.get("/api/repair")
    assert r.status_code == 200
    body = r.json()
    assert body["graphs"]["ground_truth"]["type"] == "FeatureCollection"
    assert body["metrics"]["counts"]["breaks_bridged"] == body["metrics"]["counts"]["breaks_total"]


def _centroid(poly):
    return [sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly)]
