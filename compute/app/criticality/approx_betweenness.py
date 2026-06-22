"""Approximate edge betweenness with a *guaranteed* error bound — the scalability answer.

Exact Brandes is O(V·E): fine for a neighbourhood, infeasible for a metro graph and hopeless
for "all of India". The standard escape is source sampling: instead of running an SSSP from
every node, run it from a random sample of `k` sources and rescale. Each sampled source gives
an unbiased contribution, so the mean over the sample estimates the true (normalized)
betweenness — and crucially, you can say *how wrong it might be*.

The bound here is an honest one. Write the normalized betweenness of edge e as the mean, over
all sources s, of c_s(e) = δ_s(e)/(n−1) ∈ [0, 1] (δ_s is the Brandes dependency a single
source routes through e). Sampling k sources and averaging is then a mean of k i.i.d. [0,1]
variables, so Hoeffding bounds the deviation of any one edge, and a union bound over the m
edges makes it hold for *all* of them at once:

        k ≥ ln(2m/δ) / (2·ε²)   ⇒   P( max_e |b̂(e) − b(e)| ≤ ε ) ≥ 1 − δ.

So "ε = 0.05 with 95% confidence from k sources" is a claim with a proof behind it, not a
vibe. (Riondato–Kornaropoulos give a tighter, m-free bound via the vertex-diameter / VC
dimension; the union bound is looser but self-contained and exact to state — a deliberate
trade.)

The batch form is what the Spring gateway orchestrates: each call is one independent Monte
Carlo batch, and averaging B batches of s sources is statistically identical to one run of
B·s sources — so the gateway can stream batches, watch ε shrink as ε(K) = √(ln(2m/δ)/(2K)),
and stop the moment the target is met.
"""

from __future__ import annotations

import math
import random

from app.criticality.betweenness import (
    _accumulate,
    _edge_keys,
    _sssp_dijkstra,
    _sssp_unweighted,
)


def sample_size(m, eps, delta):
    """Sources needed for an ε-additive estimate of every edge, w.p. ≥ 1−δ (Hoeffding+union)."""
    if eps <= 0:
        raise ValueError("eps must be > 0")
    return math.ceil(math.log(2 * m / delta) / (2 * eps * eps))


def achieved_epsilon(m, samples, delta):
    """The ε the bound certifies after `samples` sources — what the gateway reports as it runs."""
    if samples <= 0:
        return float("inf")
    return math.sqrt(math.log(2 * m / delta) / (2 * samples))


def sample_betweenness_batch(G, samples, weight="length", seed=0):
    """One Monte Carlo batch: estimate normalized edge betweenness from `samples` random sources.

    Returns ``(estimates, meta)`` where ``estimates`` maps the canonical (sorted) edge key to its
    estimated betweenness in [0, 1], and ``meta`` carries the graph size the gateway needs to
    track the error bound. Averaging several batches (same graph, different seeds) is exactly a
    larger single run — that's what makes the async aggregation valid.
    """
    nodes = list(G)
    n = len(nodes)
    keys = _edge_keys(G)
    acc = dict.fromkeys(keys, 0.0)
    if n < 2 or not keys:
        return {e: 0.0 for e in keys}, {"n": n, "m": len(keys), "samples": 0, "seed": seed}

    rng = random.Random(seed)
    for _ in range(samples):
        s = rng.choice(nodes)
        if weight is None:
            order, pred, sigma = _sssp_unweighted(G, s)
        else:
            order, pred, sigma = _sssp_dijkstra(G, s, weight)
        _accumulate(acc, order, pred, sigma, s)   # adds this source's dependency δ_s(e)

    # mean over the sampled sources of c_s(e) = δ_s(e)/(n−1) — an unbiased estimate of b(e)
    denom = samples * (n - 1)
    estimates = {e: acc[e] / denom for e in keys}
    return estimates, {"n": n, "m": len(keys), "samples": samples, "seed": seed}


def approx_edge_betweenness(G, eps=0.05, delta=0.1, weight="length", seed=0):
    """One-shot approximate betweenness sized to hit ε at confidence 1−δ."""
    m = len(_edge_keys(G))
    if m == 0:
        return {}, {"k": 0, "eps": eps, "delta": delta, "n": G.number_of_nodes(), "m": 0}

    k = sample_size(m, eps, delta)
    estimates, _ = sample_betweenness_batch(G, k, weight=weight, seed=seed)
    return estimates, {
        "k": k,
        "eps": eps,
        "delta": delta,
        "n": G.number_of_nodes(),
        "m": m,
        "exact_sources": G.number_of_nodes(),   # what exact Brandes would have had to run
    }
