"""Road segmentation — image → road mask. The quarantined CV step (plan §5.4).

Two paths, the same downstream:

  • ``predict_mask`` is the *real* path: a pretrained encoder-decoder (D-LinkNet / U-Net /
    DeepLab) run on a satellite tile. It's a documented hook with a lazy torch import — wire a
    checkpoint and a Bhuvan tile and nothing after it changes. We deliberately don't bundle a
    GPU model or chase SOTA; the contribution is the *repair*, not a marginally better mask.

  • ``synthesize_mask`` is the *offline* path used by the demo: rasterize a known OSM road graph
    to the mask a perfect extractor would emit, then degrade it the way the real world does —
    erase the pixels an occluder hides (canopy, shadow), drop a few road pixels (recall misses),
    and sprinkle speckle (false positives). The result is a realistic, imperfect road mask for
    which we *also* hold the ground-truth graph — i.e. a controlled sample tile (plan §1), just
    synthesized rather than downloaded. The breaks are not drawn into the graph; they're burned
    out of the image and re-discovered by the vectorizer.
"""

from __future__ import annotations

import numpy as np

from app.extraction.raster import rasterize_graph
from app.repair.occlusion import occluder_at


def synthesize_mask(G, occluders, tile, width_px=3, dropout=0.02, speckle=0.0015, seed=0):
    """A realistic imperfect road mask from a ground-truth graph + occluder polygons."""
    rng = np.random.default_rng(seed)
    mask = rasterize_graph(G, tile, width_px)

    # 1) occlusion — erase road pixels an occluder hides (this is what creates the false breaks)
    rows, cols = np.where(mask)
    for r, c in zip(rows.tolist(), cols.tolist()):
        lon, lat = tile.to_lonlat(r, c)
        if occluder_at([lon, lat], occluders):
            mask[r, c] = False

    # 2) recall misses — a few road pixels dropped (morphology will heal the small ones)
    road = np.argwhere(mask)
    if dropout > 0 and len(road):
        drop = rng.choice(len(road), int(len(road) * dropout), replace=False)
        for i in drop:
            mask[tuple(road[i])] = False

    # 3) false positives — background speckle (morphological opening sweeps it up)
    if speckle > 0:
        n = int(mask.size * speckle)
        rr = rng.integers(0, tile.height, n)
        cc = rng.integers(0, tile.width, n)
        mask[rr, cc] = True

    return mask


def predict_mask(image, weights=None):
    """Real segmentation path: a pretrained encoder-decoder → per-pixel road probability.

    Lazily imports torch so the core stays installable without it; the offline demo uses
    ``synthesize_mask`` instead. Left as the documented production seam, not a half-trained net.
    """
    try:
        import torch  # noqa: F401
    except Exception as exc:
        raise RuntimeError(
            "predict_mask needs PyTorch + segmentation weights (D-LinkNet/U-Net on a road "
            "dataset). This offline build uses synthesize_mask on the bundled controlled tile; "
            "wire a checkpoint + a Bhuvan tile here to run the real path (plan §5.4)."
        ) from exc
    raise NotImplementedError(
        "load weights, normalize the tile, forward pass → HxW road-probability mask, "
        "then hand it straight to extraction.vectorize — unchanged."
    )
