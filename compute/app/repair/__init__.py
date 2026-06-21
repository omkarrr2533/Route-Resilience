"""Tier 3 — topological repair (plan §2, §5.6).

The headline contribution: an evidence-gated layer that undoes the topology damage occlusion
inflicts on an extracted road graph before any criticality analysis runs.

  occlusion  — a controlled scenario with known ground truth (the answer key)
  repair     — gap closure for false breaks + flyover disambiguation for false junctions
  validate   — APLS, repair precision/recall, and the criticality-ranking jump
  demo       — the whole loop, assembled into one map-ready payload
"""
