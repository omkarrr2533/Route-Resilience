"""HTTP surface of the compute service. Thin handlers over app.service + the algorithms."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app import service
from app.criticality.impact import removal_impact
from app.data import loaders
from app.graph.build import undirected_view
from app.scenarios.robustness import robustness_curve

router = APIRouter(prefix="/api", tags=["criticality"])


@router.get("/health")
def health():
    return {"status": "ok", "osmnx": loaders.osmnx_available()}


@router.get("/samples")
def samples():
    return {"samples": loaders.available_samples()}


@router.get("/criticality")
def criticality(
    source: str = Query("sample:koramangala", description="sample:<name> or place:<osm query>"),
    weight: str = Query("length", description="edge weight: length or travel_time_s"),
):
    """Full scored network: per-edge resilience score + measures, plus articulation points."""
    try:
        return service.get_analysis(source, weight=weight)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/impact")
def impact(
    u: int = Query(..., description="edge start node id"),
    v: int = Query(..., description="edge end node id"),
    source: str = Query("sample:koramangala"),
    weight: str = Query("length"),
):
    """What breaks if segment (u, v) is removed — the 'remove this road' interaction."""
    try:
        G = service.get_graph(source)
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    U = undirected_view(G, weight=weight)
    if not U.has_edge(u, v):
        raise HTTPException(status_code=404, detail=f"No edge ({u}, {v}) in this network.")
    return removal_impact(U, u, v, weight=weight)


@router.get("/robustness")
def robustness(
    source: str = Query("sample:koramangala"),
    weight: str = Query("length"),
    steps: int = Query(20, ge=4, le=100),
):
    """Targeted-vs-random attack curves + AUC, for the resilience chart."""
    try:
        G = service.get_graph(source)
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "targeted": robustness_curve(G, "targeted", steps=steps, weight=weight),
        "random": robustness_curve(G, "random", steps=steps, weight=weight),
    }
