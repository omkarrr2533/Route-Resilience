"""Criticality engine — the structural core of Route Resilience.

Public surface, so callers import from one place rather than reaching into modules:

    from app.criticality import edge_betweenness, articulation_points_and_bridges, analyze
"""

from app.criticality.analyze import analyze
from app.criticality.betweenness import edge_betweenness
from app.criticality.connectivity import articulation_points_and_bridges
from app.criticality.currentflow import current_flow_edge_betweenness
from app.criticality.impact import global_efficiency, removal_impact
from app.criticality.score import resilience_scores

__all__ = [
    "analyze",
    "edge_betweenness",
    "current_flow_edge_betweenness",
    "articulation_points_and_bridges",
    "removal_impact",
    "global_efficiency",
    "resilience_scores",
]
