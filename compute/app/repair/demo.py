"""Assemble the topological-repair demo into one map-ready payload.

This is the function the API calls. It runs the whole loop end to end — build the occlusion
scenario, repair the extraction, validate against ground truth — and packages graphs, occluder
polygons, the per-decision overlay geometry, the decision log, and the metrics into a single
JSON artifact the Repair Lab renders without further round-trips.
"""

from __future__ import annotations

from app.repair import validate
from app.repair.occlusion import build_scenario
from app.repair.repair import repair


def repair_demo():
    scn = build_scenario()
    gt, raw, occluders, labels = (
        scn["ground_truth"], scn["extracted"], scn["occluders"], scn["labels"],
    )

    result = repair(raw, occluders)
    repaired, decisions = result["graph"], result["decisions"]

    quality = validate.repair_quality(decisions, labels)
    metrics = {
        "apls_raw": round(validate.apls_score(raw, gt), 3),
        "apls_repaired": round(validate.apls_score(repaired, gt), 3),
        "spearman_raw": round(validate.criticality_rank_correlation(raw, gt), 3),
        "spearman_repaired": round(validate.criticality_rank_correlation(repaired, gt), 3),
        "precision": quality["precision"],
        "recall": quality["recall"],
        "decoys_rejected": quality["decoys_rejected"],
        "flyover_correct": quality["flyover_correct"],
        "counts": {
            "nodes": gt.number_of_nodes(),
            "edges_gt": gt.number_of_edges(),
            "edges_raw": raw.number_of_edges(),
            "edges_repaired": repaired.number_of_edges(),
            "breaks_total": quality["real_breaks"],
            "breaks_bridged": quality["bridged"],
            "flyovers_split": quality["flyovers_split"],
            "crossings_kept": sum(1 for d in decisions
                                  if d["kind"] == "crossing" and d["decision"] == "kept"),
        },
    }

    return {
        "occluders": occluders,
        "graphs": {
            "ground_truth": _edges_geojson(gt),
            "raw": _edges_geojson(raw),
            "repaired": _edges_geojson(repaired),
        },
        "overlays": _overlays(repaired, decisions),
        "decisions": [_log_entry(d) for d in decisions],
        "metrics": metrics,
    }


# ── serialization ────────────────────────────────────────────────────────────────────────
def _edges_geojson(G):
    features = []
    for u, v, data in G.edges(data=True):
        features.append(_line(G, u, v, {
            "u": u, "v": v,
            "highway": data.get("highway"),
            "repaired": bool(data.get("repaired")),
            "bridge": bool(data.get("bridge")),
        }))
    return {"type": "FeatureCollection", "features": features}


def _overlays(H, decisions):
    """The geometry that explains each decision: closed gaps, rejected gaps, and the crossing
    verdicts — drawn on top of the graphs so the repair's reasoning is legible, not implied."""
    bridged, rejected, splits, kept = [], [], [], []

    for d in decisions:
        if d["kind"] == "break":
            a, b = d["ends"]
            target = bridged if d["decision"] == "bridged" else rejected
            target.append(_line(H, a, b, {
                "occluder": d.get("occluder"),
                "gap_m": d["gap_m"],
                "reason": d["reason"],
            }))
        else:                                    # crossing
            (splits if d["decision"] == "split" else kept).append({
                "type": "Feature",
                "properties": {"node": d["node"], "reason": d["reason"]},
                "geometry": {"type": "Point", "coordinates": d["location"]},
            })

    return {
        "bridged": _fc(bridged),
        "rejected": _fc(rejected),
        "splits": _fc(splits),
        "kept": _fc(kept),
    }


def _log_entry(d):
    if d["kind"] == "break":
        return {
            "kind": "break", "decision": d["decision"],
            "ends": d["ends"], "occluder": d.get("occluder"),
            "gap_m": d["gap_m"], "reason": d["reason"],
        }
    return {
        "kind": "crossing", "decision": d["decision"],
        "node": d["node"], "reason": d["reason"],
    }


def _line(G, u, v, props):
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {
            "type": "LineString",
            "coordinates": [[G.nodes[u]["x"], G.nodes[u]["y"]],
                            [G.nodes[v]["x"], G.nodes[v]["y"]]],
        },
    }


def _fc(features):
    return {"type": "FeatureCollection", "features": features}
