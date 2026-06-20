"""End-to-end checks on the HTTP surface, against the bundled sample."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_criticality_returns_scored_geojson():
    r = client.get("/api/criticality", params={"source": "sample:koramangala"})
    assert r.status_code == 200
    body = r.json()

    assert body["edges"]["type"] == "FeatureCollection"
    assert body["summary"]["connected_components"] == 1

    scores = [f["properties"]["score"] for f in body["edges"]["features"]]
    assert max(scores) == 100.0           # the planted bridge maxes out
    assert min(scores) >= 0.0

    # exactly one bridge in the sample: the pocket approach road
    bridges = [f for f in body["edges"]["features"] if f["properties"]["is_bridge"]]
    assert len(bridges) == 1


def test_impact_of_the_bridge_disconnects_the_pocket():
    r = client.get("/api/impact", params={"u": 27, "v": 100})
    assert r.status_code == 200
    body = r.json()
    assert body["fragmented"] is True            # removing the bridge sheds the pocket
    assert body["lcc_after"] < body["lcc_before"]


def test_unknown_sample_is_a_clean_400():
    r = client.get("/api/criticality", params={"source": "sample:atlantis"})
    assert r.status_code == 400


def test_robustness_targeted_collapses_faster_than_random():
    r = client.get("/api/robustness", params={"steps": 12})
    assert r.status_code == 200
    body = r.json()
    # A structured network is more fragile to targeted attack -> smaller area under curve.
    assert body["targeted"]["auc"] <= body["random"]["auc"]
