"""NARE natural-scene appearance validation contracts.

This module validates real-photo RAW/SOOC-JPEG metadata and evaluates recorded
three-layer errors at the independent scene level. Rendering and registration
remain explicit caller inputs.
"""

import math
from typing import Any, Iterable, Mapping

from .eager import SceneMetric, evaluate_paired

_REQUIRED = ("scene_id", "session_id", "contributor", "source_path", "target_path",
             "source_sha256", "target_sha256", "picture_style", "lighting",
             "scene_type", "split")
_SPLITS = {"discovery", "validation", "evaluation", "lockbox"}


def _finite_nonnegative(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"NARE {label} must be finite and non-negative") from error
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"NARE {label} must be finite and non-negative")
    return number


def _registration_is_valid(diagnostic: Any) -> bool:
    if not isinstance(diagnostic, Mapping):
        return False
    if diagnostic.get("passed") is False:
        return False
    try:
        correlation = float(diagnostic["ecc_correlation"])
        overlap = float(diagnostic["overlap_fraction"])
        shift_x = float(diagnostic.get("shift_x_px", 0.0))
        shift_y = float(diagnostic.get("shift_y_px", 0.0))
    except (KeyError, TypeError, ValueError):
        return False
    if not all(math.isfinite(value) for value in (correlation, overlap, shift_x, shift_y)):
        return False
    return 0.6 <= correlation <= 1.0 and 0.9 <= overlap <= 1.0


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
            "n_sessions": len({str(row["session_id"]) for row in records}),
            "lighting": sorted({str(row["lighting"]) for row in records}),
            "scene_type": sorted({str(row["scene_type"]) for row in records}),
            "picture_styles": sorted({str(row["picture_style"]) for row in records})}


def evaluate_nare_metrics(manifest_rows: Iterable[Mapping[str, Any]],
                          metric_rows: Iterable[Mapping[str, Any]],
                          n_bootstrap: int = 20_000, seed: int = 0) -> dict[str, Any]:
    manifest = list(manifest_rows)
    summary = validate_nare_manifest(manifest)
    metadata = {str(row["scene_id"]): row for row in manifest
                if row["split"] in {"evaluation", "lockbox"}}
    metric_records = list(metric_rows)
    metric_ids = [str(row.get("scene_id")) for row in metric_records]
    if len(metric_ids) != len(set(metric_ids)):
        raise ValueError("NARE metric rows contain duplicate scene IDs")
    metrics = dict(zip(metric_ids, metric_records))
    if set(metrics) != set(metadata):
        raise ValueError("NARE metric scene IDs must exactly match evaluation/lockbox scenes")
    required = ("raw_delta_e00", "foundation_delta_e00", "candidate_delta_e00")
    scene_metrics = []
    foundation = []
    registration = []
    for scene_id in sorted(metadata):
        row = metrics[scene_id]
        if any(key not in row for key in required):
            raise ValueError(f"NARE metric row {scene_id!r} missing baseline layer")
        raw_delta = _finite_nonnegative(row["raw_delta_e00"], f"raw_delta_e00[{scene_id}]")
        foundation_delta = _finite_nonnegative(row["foundation_delta_e00"],
                                               f"foundation_delta_e00[{scene_id}]")
        candidate_delta = _finite_nonnegative(row["candidate_delta_e00"],
                                              f"candidate_delta_e00[{scene_id}]")
        scene_metrics.append(SceneMetric(scene_id, raw_delta, candidate_delta))
        foundation.append(foundation_delta)
        diagnostic = row.get("registration")
        registration.append(_registration_is_valid(diagnostic))
    paired = evaluate_paired(scene_metrics, n_bootstrap=n_bootstrap, seed=seed)
    raw_mean = paired["mean_baseline"]
    foundation_mean = sum(foundation) / len(foundation)
    subgroup_metrics = summarize_nare_subgroups(metric_records)
    evaluated_rows = [row for row in manifest if row["split"] in {"evaluation", "lockbox"}]
    evaluated_lighting = sorted({str(row["lighting"]) for row in evaluated_rows})
    evaluated_scene_type = sorted({str(row["scene_type"]) for row in evaluated_rows})
    evaluated_styles = sorted({str(row["picture_style"]) for row in evaluated_rows})
    return {**paired, "manifest": summary,
            "improvement_pct": paired["mean_improvement_pct"],
            "baseline_layers": ["raw_decoder", "colorimetric_foundation", "appearance_candidate"],
            "mean_foundation": foundation_mean,
            "foundation_improvement_pct": 100 * (raw_mean - foundation_mean) / raw_mean,
            "registration_passed": all(registration),
            "subgroup_metrics": subgroup_metrics,
            "subgroup_metrics_passed": subgroup_metrics["passed"],
            "coverage": {"lighting": evaluated_lighting, "scene_type": evaluated_scene_type},
            "picture_styles": evaluated_styles}


def summarize_nare_subgroups(metric_rows: Iterable[Mapping[str, Any]], *,
                             required: Iterable[str] = ("skin", "sky", "foliage",
                                                         "neutral", "saturated",
                                                         "shadow", "highlight"),
                             catastrophic_regression_pct: float = 15.0) -> dict[str, Any]:
    """Aggregate semantic-region metrics and fail closed on missing regions.

    Each metric row must contain ``subgroups[name]`` with baseline and candidate
    ``*_delta_e00`` values. A positive improvement means candidate error fell;
    a regression beyond the configured percentage is catastrophic.
    """
    if catastrophic_regression_pct < 0:
        raise ValueError("catastrophic_regression_pct must be non-negative")
    rows = list(metric_rows)
    required = tuple(dict.fromkeys(str(name) for name in required))
    groups: dict[str, dict[str, list[float]]] = {
        name: {"baseline": [], "candidate": []} for name in required
    }
    missing: set[str] = set()
    for row in rows:
        subgroups = row.get("subgroups", {})
        for name in required:
            values = subgroups.get(name) if isinstance(subgroups, Mapping) else None
            if not isinstance(values, Mapping) or "baseline_delta_e00" not in values or "candidate_delta_e00" not in values:
                missing.add(name)
                continue
            groups[name]["baseline"].append(_finite_nonnegative(
                values["baseline_delta_e00"], f"subgroups[{name}].baseline_delta_e00"))
            groups[name]["candidate"].append(_finite_nonnegative(
                values["candidate_delta_e00"], f"subgroups[{name}].candidate_delta_e00"))
    summary: dict[str, dict[str, Any]] = {}
    catastrophic = []
    for name in required:
        baseline = groups[name]["baseline"]
        candidate = groups[name]["candidate"]
        if not baseline:
            missing.add(name)
            continue
        baseline_mean = sum(baseline) / len(baseline)
        candidate_mean = sum(candidate) / len(candidate)
        improvement_pct = 100 * (baseline_mean - candidate_mean) / baseline_mean if baseline_mean else 0.0
        summary[name] = {"n": len(baseline), "baseline_mean": baseline_mean,
                         "candidate_mean": candidate_mean, "improvement_pct": improvement_pct}
        if (baseline_mean == 0 and candidate_mean > 0) or improvement_pct < -catastrophic_regression_pct:
            catastrophic.append(name)
    return {"groups": summary, "missing_groups": sorted(missing),
            "catastrophic_regressions": sorted(catastrophic),
            "passed": not missing and not catastrophic}


def classify_nare_result(result: Mapping[str, Any], min_scenes: int = 12,
                         min_improvement_pct: float = 5.0) -> dict[str, Any]:
    coverage = result.get("coverage", {})
    picture_styles = [str(style).strip().lower() for style in result.get("picture_styles", [])]
    checks = {
        "scene_count": int(result.get("n_scenes", 0)) >= min_scenes,
        "effect_threshold": float(result.get("improvement_pct", 0)) >= min_improvement_pct,
        "ci_positive": bool(result.get("ci95")) and float(result["ci95"][0]) > 0,
        "sign_test": float(result.get("sign_test_p", 1)) < 0.05,
        "lighting_coverage": len(coverage.get("lighting", [])) >= 3,
        "scene_coverage": len(coverage.get("scene_type", [])) >= 3,
        "picture_style": len(picture_styles) == 1 and picture_styles[0] != "unknown",
        "registration": bool(result.get("registration_passed", False)),
        "subgroups": bool(result.get("subgroups_passed", False))
        and bool(result.get("subgroup_metrics_passed", False)),
        "controls": bool(result.get("controls_passed", False)),
        "provenance": bool(result.get("provenance_passed", False)),
    }
    return {"ship_gate_passed": all(checks.values()), "checks": checks,
            "classification": "Supported" if all(checks.values()) else "Inconclusive"}
