"""NARE natural-scene appearance validation contracts.

This module validates real-photo RAW/SOOC-JPEG metadata and evaluates recorded
three-layer errors at the independent scene level. Rendering and registration
remain explicit caller inputs.
"""

import math
from statistics import mean
from typing import Any, Iterable, Mapping

from .eager import SceneMetric, evaluate_paired, _positive_ci, _valid_number

_REQUIRED = ("scene_id", "session_id", "contributor", "source_path", "target_path",
             "source_sha256", "target_sha256", "picture_style", "lighting",
             "scene_type", "split")
_SPLITS = {"discovery", "validation", "evaluation", "lockbox"}


def _finite_nonnegative(value: Any, label: str) -> float:
    if not _valid_number(value):
        raise ValueError(f"NARE {label} must be finite and non-negative")
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
    if "passed" in diagnostic and diagnostic["passed"] is not True:
        return False
    if diagnostic.get("failure_reason"):
        return False
    keys = ("ecc_correlation", "overlap_fraction", "shift_x_px", "shift_y_px", "long_edge_px")
    if not all(_valid_number(diagnostic.get(key)) for key in keys):
        return False
    if type(diagnostic.get("long_edge_px")) is not int:
        return False
    try:
        correlation = float(diagnostic["ecc_correlation"])
        overlap = float(diagnostic["overlap_fraction"])
        shift_x = float(diagnostic["shift_x_px"])
        shift_y = float(diagnostic["shift_y_px"])
        long_edge = diagnostic["long_edge_px"]
    except (KeyError, TypeError, ValueError):
        return False
    if not all(math.isfinite(value) for value in (correlation, overlap, shift_x, shift_y)):
        return False
    return (0.6 <= correlation <= 1.0 and 0.9 <= overlap <= 1.0
            and long_edge > 0 and math.hypot(shift_x, shift_y) <= long_edge * 0.05)


def validate_nare_manifest(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    records = list(rows)
    if not records:
        raise ValueError("NARE manifest must contain at least one row")
    scenes: dict[str, str] = {}
    scene_metadata = {}
    content_scenes = {key: {} for key in ("source_sha256", "target_sha256")}
    for index, row in enumerate(records, 1):
        missing = [key for key in _REQUIRED if not isinstance(row.get(key), str) or not row[key].strip()]
        if missing:
            raise ValueError(f"NARE row {index} missing fields: {', '.join(missing)}")
        if row["split"] not in _SPLITS:
            raise ValueError(f"NARE row {index} has unknown split: {row['split']!r}")
        for key in ("source_sha256", "target_sha256"):
            value = str(row[key]).lower()
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"NARE row {index} has invalid {key}")
        scene = row["scene_id"]
        if scene != scene.strip() or row["session_id"] != row["session_id"].strip():
            raise ValueError("NARE scene/session IDs must not have surrounding whitespace")
        prior = scenes.setdefault(scene, str(row["split"]))
        if prior != row["split"]:
            raise ValueError(f"scene_id {scene!r} appears in multiple splits")
        signature = tuple(row[key].strip().casefold() for key in
                          ("session_id", "contributor", "picture_style", "lighting", "scene_type"))
        if scene_metadata.setdefault(scene, signature) != signature:
            raise ValueError(f"NARE conflicting metadata for scene {scene!r}")
        for key, seen in content_scenes.items():
            digest = row[key].lower()
            if seen.setdefault(digest, scene) != scene:
                raise ValueError(f"NARE duplicate {key} assigned to different scenes")
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
    foundation_mean = mean(foundation)
    foundation_improvement = 100 * (1 - foundation_mean / raw_mean) if raw_mean else None
    if foundation_improvement is not None and not math.isfinite(foundation_improvement):
        raise ValueError("NARE foundation improvement is not finite")
    subgroup_metrics = summarize_nare_subgroups(metric_records)
    evaluated_rows = [row for row in manifest if row["split"] in {"evaluation", "lockbox"}]
    evaluated_lighting = sorted({row["lighting"].strip().casefold() for row in evaluated_rows})
    evaluated_scene_type = sorted({row["scene_type"].strip().casefold() for row in evaluated_rows})
    evaluated_styles = sorted({row["picture_style"].strip().casefold() for row in evaluated_rows})
    return {**paired, "manifest": summary,
            "improvement_pct": paired["mean_improvement_pct"],
            "baseline_layers": ["raw_decoder", "colorimetric_foundation", "appearance_candidate"],
            "mean_foundation": foundation_mean,
            "foundation_improvement_pct": foundation_improvement,
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
    """Aggregate semantic-region metrics and fail closed on missing regions."""
    if not _valid_number(catastrophic_regression_pct) or catastrophic_regression_pct < 0:
        raise ValueError("catastrophic_regression_pct must be non-negative")
    rows = list(metric_rows)
    required = tuple(dict.fromkeys(str(name) for name in required))
    if not required or any(not name.strip() for name in required):
        raise ValueError("required subgroups must not be empty")
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
        baseline_mean = mean(baseline)
        candidate_mean = mean(candidate)
        improvement_pct = 100 * (1 - candidate_mean / baseline_mean) if baseline_mean else None
        summary[name] = {"n": len(baseline), "baseline_mean": baseline_mean,
                         "candidate_mean": candidate_mean, "improvement_pct": improvement_pct}
        if ((baseline_mean == 0 and candidate_mean > 0)
                or (improvement_pct is not None and improvement_pct < -catastrophic_regression_pct)):
            catastrophic.append(name)
    return {"groups": summary, "missing_groups": sorted(missing),
            "catastrophic_regressions": sorted(catastrophic),
            "passed": not missing and not catastrophic}


def classify_nare_result(result: Mapping[str, Any], min_scenes: int = 12,
                         min_improvement_pct: float = 5.0) -> dict[str, Any]:
    coverage = result.get("coverage", {})

    def labels(value):
        if not isinstance(value, (list, tuple)) or not all(isinstance(v, str) for v in value):
            return set()
        return {v.strip().casefold() for v in value} - {"", "unknown", "none", "null", "n/a"}

    picture_styles = labels(result.get("picture_styles", []))
    count, effect, sign = (result.get(key) for key in ("n_scenes", "improvement_pct", "sign_test_p"))
    coverage = coverage if isinstance(coverage, Mapping) else {}
    checks = {
        "scene_count": type(count) is int and count >= min_scenes,
        "effect_threshold": _valid_number(effect) and effect >= min_improvement_pct,
        "ci_positive": _positive_ci(result.get("ci95")),
        "sign_test": _valid_number(sign) and 0 <= sign < 0.05,
        "lighting_coverage": len(labels(coverage.get("lighting"))) >= 3,
        "scene_coverage": len(labels(coverage.get("scene_type"))) >= 3,
        "picture_style": len(picture_styles) == 1 and len(result.get("picture_styles", [])) == 1,
        "registration": result.get("registration_passed") is True,
        "subgroups": result.get("subgroups_passed") is True
        and result.get("subgroup_metrics_passed") is True,
        "controls": result.get("controls_passed") is True,
        "provenance": result.get("provenance_passed") is True,
        # Supported is the strongest NARE class.  A cryptographically valid
        # receipt establishes artifact integrity for this local/reproducible
        # level; it does not assert independent signer authority.
        "receipt_integrity": result.get("receipt_valid") is True,
    }
    return {"ship_gate_passed": all(checks.values()), "checks": checks,
            "classification": "Supported" if all(checks.values()) else "Inconclusive"}
