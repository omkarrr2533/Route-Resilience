"""Tier 3 — road extraction (plan §5.4, §5.5).

Closes the loop: instead of removing edges from a graph by hand, the false breaks are burned
out of a road *mask* and rediscovered by a real vectorizer, so the repair runs on a genuinely
extracted topology.

  raster     — affine tile transform, Bresenham rasterize, a tiny PNG encoder
  vectorize  — clean → Zhang–Suen skeletonize → trace → prune → georeference
  segment    — predict_mask (pretrained-model hook) + synthesize_mask (the offline tile)
  validate   — geometric APLS + criticality-ranking correlation (nodes matched by geometry)
  pipeline   — mask → extracted graph → repair → validate, assembled for the Repair Lab
"""
