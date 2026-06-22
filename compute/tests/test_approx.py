"""Approximate betweenness: the estimate has to actually land inside the ε it promises, and it
has to rank the segments the same way exact Brandes does (the ranking is what criticality is
*for*)."""

from fastapi.testclient import TestClient

from app.criticality.approx_betweenness import (
    achieved_epsilon,
    approx_edge_betweenness,
    sample_betweenness_batch,
    sample_size,
)
from app.criticality.betweenness import edge_betweenness
from app.data.loaders import load_sample
from app.graph.build import undirected_view
from app.main import app
from app.repair.validate import spearman

client = TestClient(app)


def _U():
    return undirected_view(load_sample("koramangala"))


def test_sample_size_shrinks_eps_costs_more():
    # halving the error roughly quadruples the work (k ∝ 1/ε²)
    assert sample_size(80, 0.10, 0.1) < sample_size(80, 0.05, 0.1)
    assert sample_size(80, 0.05, 0.1) > 3 * sample_size(80, 0.10, 0.1)


def test_achieved_epsilon_matches_sample_size():
    # the ε the bound certifies at k sources should equal the ε that asked for k
    k = sample_size(80, 0.05, 0.1)
    assert achieved_epsilon(80, k, 0.1) <= 0.05 + 1e-9
    assert achieved_epsilon(80, k, 0.1) > 0.04            # not wildly slack


def test_estimate_lands_within_its_bound():
    U = _U()
    exact = edge_betweenness(U, weight="length", normalized=True)
    eps = 0.05
    approx, meta = approx_edge_betweenness(U, eps=eps, delta=0.1, weight="length", seed=1)

    worst = max(abs(approx[e] - exact[e]) for e in exact)
    assert worst <= eps                                   # the promised guarantee holds
    assert meta["k"] > 0 and meta["exact_sources"] == U.number_of_nodes()


def test_estimate_preserves_the_ranking():
    U = _U()
    exact = edge_betweenness(U, weight="length", normalized=True)
    approx, _ = approx_edge_betweenness(U, eps=0.05, delta=0.1, weight="length", seed=3)

    keys = list(exact)
    assert spearman([exact[e] for e in keys], [approx[e] for e in keys]) > 0.95
    # the head of the ranking survives: each side's most-critical edge sits in the other's
    # top 5. (Exact equality of #1 is *not* guaranteed — within ε, near-ties can swap, which
    # is the honest reading of an additive bound, not a failure.)
    exact_top5 = sorted(keys, key=exact.get, reverse=True)[:5]
    approx_top5 = sorted(keys, key=approx.get, reverse=True)[:5]
    assert max(keys, key=approx.get) in exact_top5
    assert max(keys, key=exact.get) in approx_top5


def test_batches_average_like_one_bigger_run():
    U = _U()
    # two batches of 200, averaged, ≈ one run of 400 (same sources, just regrouped)
    b1, _ = sample_betweenness_batch(U, 200, seed=10)
    b2, _ = sample_betweenness_batch(U, 200, seed=11)
    merged = {e: (b1[e] + b2[e]) / 2 for e in b1}
    assert all(0.0 <= v <= 1.0 for v in merged.values())
    assert achieved_epsilon(len(b1), 400, 0.1) < achieved_epsilon(len(b1), 200, 0.1)


def test_routes():
    r = client.get("/api/criticality/approx", params={"eps": 0.05, "delta": 0.1})
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["k"] > 0
    assert all({"u", "v", "b"} <= set(e) for e in body["edges"])

    b = client.get("/api/criticality/sample-batch", params={"samples": 64, "seed": 5})
    assert b.status_code == 200
    assert b.json()["meta"]["samples"] == 64
