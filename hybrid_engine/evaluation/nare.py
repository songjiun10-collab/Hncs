"""NARE natural-scene appearance validation contracts.

This module validates real-photo RAW/SOOC-JPEG metadata and evaluates recorded
three-layer errors at the independent scene level. Rendering and registration
remain explicit caller inputs.
"""

from typing import Any, Iterable, Mapping

from .eager import SceneMetric, evaluate_paired

_REQUIRED = ("scene_id", "session_id", "contributor", "source_path", "target_path",
             "source_sha256", "target_sha256", "picture_style", "lighting",
             "scene_type", "split")
_SPLITS = {"discovery", "validation", "evaluation", "lockbox"}


def validate_nare_manifest(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    records = list(rows)
    if not records:
        raise ValueError("NARE manifest must contain at least one row")
    scenes: dict[str, str] = {}
    for index, row in enumerate(records, 1):
        missing = [key for key in _REQUIRED if not str(row.get(key, "")).strip()]
        if missing:
            raise ValueError(f"NARE row {index} missing fields: {', '.join(missing)}")
        if row["split"] not in _SPLITS:
            raise ValueError(f"NARE row {index} has unknown split: {row['split']!r}")
        for key in ("source_sha256", "target_sha256"):
            value = str(row[key]).lower()
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"NARE row {index} has invalid {key}")
        scene = str(row["scene_id"])
        prior = scenes.setdefault(scene, str(row["split"]))
        if prior != row["split"]:
            raise ValueError(f"scene_id {scene!r} appears in multiple splits")
    return {"n_rows": len(records), "n_scenes": len(scenes),
            "lighting": sorted({str(row["lighting"]) for row in records}),
            "scene_type": sorted({str(row["scene_type"]) for row in records})}


def evaluate_nare_metrics(manifest_rows: Iterable[Mapping[str, Any]],
                          metric_rows: Iterable[Mapping[str, Any]],
                          n_bootstrap: int = 20_000, seed: int = 0) -> dict[str, Any]:
    manifest = list(manifest_rows)
    summary = validate_nare_manifest(manifest)
    metadata = {str(row["scene_id"]): row for row in manifest
                if row["split"] in {"evaluation", "lockbox"}}
    metrics = {str(row.get("scene_id")): row for row in metric_rows}
    if set(metrics) != set(metadata):
        raise ValueError("NARE metric scene IDs must exactly match evaluation/lockbox scenes")
    required = ("raw_delta_e00", "foundation_delta_e00", "candidate_delta_e00")
    scene_metrics = []
    foundation = []
    for scene_id in sorted(metadata):
        row = metrics[scene_id]
        if any(key not in row for key in required):
            raise ValueError(f"NARE metric row {scene_id!r} missing baseline layer")
        scene_metrics.append(SceneMetric(scene_id, float(row["raw_delta_e00"]),
                                         float(row["candidate_delta_e00"])))
        foundation.append(float(row["foundation_delta_e00"]))
    paired = evaluate_paired(scene_metrics, n_bootstrap=n_bootstrap, seed=seed)
    raw_mean = paired["mean_baseline"]
    foundation_mean = sum(foundation) / len(foundation)
    return {**paired, "manifest": summary,
            "improvement_pct": paired["mean_improvement_pct"],
            "baseline_layers": ["raw_decoder", "colorimetric_foundation", "appearance_candidate"],
            "mean_foundation": foundation_mean,
            "foundation_improvement_pct": 100 * (raw_mean - foundation_mean) / raw_mean,
            "coverage": {"lighting": summary["lighting"], "scene_type": summary["scene_type"]}}


def classify_nare_result(result: Mapping[str, Any], min_scenes: int = 12,
                         min_improvement_pct: float = 5.0) -> dict[str, Any]:
    coverage = result.get("coverage", {})
    checks = {
        "scene_count": int(result.get("n_scenes", 0)) >= min_scenes,
        "effect_threshold": float(result.get("improvement_pct", 0)) >= min_improvement_pct,
        "ci_positive": bool(result.get("ci95")) and float(result["ci95"][0]) > 0,
        "sign_test": float(result.get("sign_test_p", 1)) < 0.05,
        "lighting_coverage": len(coverage.get("lighting", [])) >= 3,
        "scene_coverage": len(coverage.get("scene_type", [])) >= 3,
        "subgroups": bool(result.get("subgroups_passed", False)),
        "controls": bool(result.get("controls_passed", False)),
        "provenance": bool(result.get("provenance_passed", False)),
    }
    return {"ship_gate_passed": all(checks.values()), "checks": checks,
            "classification": "Supported" if all(checks.values()) else "Inconclusive"}
