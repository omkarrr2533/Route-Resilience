"""Mask → graph. The standard, well-documented road-vectorization pipeline (plan §5.5), here
written out by hand on top of NumPy rather than pulled from scikit-image — same reason the
criticality core writes out Brandes: it's worth being able to defend, and it keeps the install
dependency-light.

    clean  →  skeletonize  →  trace  →  prune  →  georeference

  • clean        morphological close-then-open to seal pinholes and shed speckle.
  • skeletonize  Zhang–Suen thinning to a 1-px centreline (vectorized over the whole image).
  • trace        centreline pixels with ≠2 neighbours are nodes (junctions/endpoints); the
                 degree-2 runs between them are edges. Adjacent node-pixels collapse to one
                 junction at their centroid.
  • prune        drop the short dead-end spurs thinning always leaves behind.
  • georeference map every node through the tile's affine transform to a real (lon, lat).

The payoff: when an occluder erased a road's middle pixels, the centreline there simply isn't
there, so the trace emits two dangling endpoints facing each other across the gap — a *false
break*, produced by the geometry, exactly the input the topological-repair layer is built to
fix. Nothing about the break is hand-authored; it falls out of the pixels.
"""

from __future__ import annotations

import networkx as nx
import numpy as np

from app.extraction.raster import _shift, dilate, erode, polyline_length_m

_NEIGH = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def clean(mask, radius=1):
    """Morphological close then open — seal hairline gaps, then remove isolated speckle."""
    closed = erode(dilate(mask, radius), radius)
    opened = dilate(erode(closed, radius), radius)
    return opened


def skeletonize(mask):
    """Zhang–Suen thinning to a 1-pixel-wide skeleton. Vectorized: each iteration scores every
    pixel at once and deletes a whole sub-iteration's worth in one shot."""
    img = mask.astype(np.uint8)
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            p = [_shift(img, dr, dc) for (dr, dc) in
                 [(1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1)]]
            P2, P3, P4, P5, P6, P7, P8, P9 = p
            B = P2 + P3 + P4 + P5 + P6 + P7 + P8 + P9
            seq = [P2, P3, P4, P5, P6, P7, P8, P9, P2]
            A = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.uint8) for i in range(8))
            if step == 0:
                cond = (P2 * P4 * P6 == 0) & (P4 * P6 * P8 == 0)
            else:
                cond = (P2 * P4 * P8 == 0) & (P2 * P6 * P8 == 0)
            flag = (img == 1) & (B >= 2) & (B <= 6) & (A == 1) & cond
            if flag.any():
                img[flag] = 0
                changed = True
    return img.astype(bool)


def trace(skeleton, tile, prune_len_m=20.0):
    """Walk a skeleton into a georeferenced road graph."""
    ys, xs = np.where(skeleton)
    pts = set(zip(ys.tolist(), xs.tolist()))
    if not pts:
        return nx.Graph()

    degree = {p: sum((p[0] + dr, p[1] + dc) in pts for dr, dc in _NEIGH) for p in pts}
    node_px = {p for p in pts if degree[p] != 2}

    cluster_of, clusters = _cluster_nodes(node_px)
    G = nx.Graph()
    for cid, comp in enumerate(clusters):
        rr = sum(r for r, _ in comp) / len(comp)
        cc = sum(c for _, c in comp) / len(comp)
        lon, lat = tile.to_lonlat(rr, cc)
        G.add_node(cid, x=round(lon, 6), y=round(lat, 6))

    _trace_edges(G, tile, pts, node_px, degree, cluster_of)
    _prune_spurs(G, prune_len_m)
    return G


def _cluster_nodes(node_px):
    """Collapse 8-connected runs of node-pixels (a thick junction) into one node each."""
    cluster_of, clusters = {}, []
    for p in node_px:
        if p in cluster_of:
            continue
        cid = len(clusters)
        comp, stack = [], [p]
        cluster_of[p] = cid
        while stack:
            q = stack.pop()
            comp.append(q)
            for dr, dc in _NEIGH:
                nb = (q[0] + dr, q[1] + dc)
                if nb in node_px and nb not in cluster_of:
                    cluster_of[nb] = cid
                    stack.append(nb)
        clusters.append(comp)
    return cluster_of, clusters


def _trace_edges(G, tile, pts, node_px, degree, cluster_of):
    best = {}                                   # frozenset({a,b}) -> (length_m, pixel path)
    visited = set()

    def consider(a, b, path):
        if a == b:
            return                              # self-loop from a tiny junction artifact
        L = polyline_length_m(tile, path)
        keyab = frozenset((a, b))
        if keyab not in best or L < best[keyab][0]:
            best[keyab] = (L, path)

    for p in node_px:
        a = cluster_of[p]
        for dr, dc in _NEIGH:
            q = (p[0] + dr, p[1] + dc)
            if q not in pts:
                continue
            if q in node_px:                    # node adjacent to node — a one-hop edge
                consider(a, cluster_of[q], [p, q])
                continue
            if q in visited:
                continue
            # walk the degree-2 chain to the next node
            prev, cur, path = p, q, [p, q]
            visited.add(q)
            while cur not in node_px:
                nxt = [(cur[0] + a2, cur[1] + b2) for a2, b2 in _NEIGH
                       if (cur[0] + a2, cur[1] + b2) in pts and (cur[0] + a2, cur[1] + b2) != prev]
                if len(nxt) != 1:
                    break
                prev, cur = cur, nxt[0]
                path.append(cur)
                if cur not in node_px:
                    visited.add(cur)
            if cur in node_px:
                consider(a, cluster_of[cur], path)

    for keyab, (L, _) in best.items():
        a, b = tuple(keyab)
        G.add_edge(a, b, highway="extracted", length=round(L, 2), length_m=round(L, 2))


def _prune_spurs(G, prune_len_m):
    """Repeatedly drop degree-1 nodes whose only edge is a short stub (thinning debris)."""
    changed = True
    while changed:
        changed = False
        for n in [n for n in G.nodes() if G.degree(n) == 1]:
            nbr = next(iter(G[n]))
            if G[n][nbr].get("length", 0.0) < prune_len_m:
                G.remove_node(n)
                changed = True
    G.remove_nodes_from([n for n in list(G.nodes()) if G.degree(n) == 0])


def vectorize(mask, tile, clean_radius=1, prune_len_m=20.0):
    """Full pipeline: a probability/binary mask in, a georeferenced road graph out."""
    binary = mask > 0.5 if mask.dtype != bool else mask
    return trace(skeletonize(clean(binary, clean_radius)), tile, prune_len_m=prune_len_m)
