"""Reusable validation kernel for the EAGER color-science framework.

The module deliberately contains no renderer or calibration policy.  It makes
the evidence contract executable: provenance-aware manifests, capture-group
aggregation, paired uncertainty, sample accounting, physical sanity checks,
and result classification.  Research scripts can consume these small helpers
without turning synthetic or pixel-level repeats into independent evidence.
"""

from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256
from math import comb
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


class EvidenceTier(str, Enum):
    """Strength of the data supporting a color/appearance claim."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"


_SPLITS = frozenset(("discovery", "validation", "lockbox", "evaluation"))
_REQUIRED_MANIFEST_FIELDS = (
    "scene_id", "source_body", "target_body", "illumination_id",
    "source_path", "target_path", "source_sha256", "target_sha256",
    "split", "evidence_tier",
)
_ACCOUNTING_STAGES = (
    "requested", "downloaded", "decoded", "provenance_valid", "paired",
    "group_valid", "evaluated",
)


@dataclass(frozen=True)
class SceneMetric:
    """One source/target comparison before scene-level aggregation."""

    scene_id: str
    baseline_delta_e00: float
    candidate_delta_e00: float
    source_body: str | None = None
    illumination_id: str | None = None
    neutral_baseline: float | None = None
    neutral_candidate: float | None = None
    chromatic_baseline: float | None = None
    chromatic_candidate: float | None = None


def _nonempty(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _valid_sha256(value: Any) -> bool:
    text = str(value).strip().lower()
    return len(text) == 64 and all(c in "0123456789abcdef" for c in text)


def validate_manifest(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate EAGER manifest fields and prevent scene split leakage.

    A scene may have multiple body captures, but all captures of one physical
    scene must belong to exactly one split.  Hashes are mandatory so a later
    report can prove which files were evaluated.
    """

    records = list(rows)
    if not records:
        raise ValueError("manifest must contain at least one row")
    scene_splits: dict[str, str] = {}
    for index, row in enumerate(records, start=1):
        missing = [key for key in _REQUIRED_MANIFEST_FIELDS if not _nonempty(row.get(key))]
        if missing:
            raise ValueError(f"manifest row {index} missing fields: {', '.join(missing)}")
        scene_id = str(row["scene_id"])
        split = str(row["split"])
        if split not in _SPLITS:
            raise ValueError(f"manifest row {index} has unknown split: {split!r}")
        tier = str(row["evidence_tier"]).upper()
        if tier not in {item.value for item in EvidenceTier}:
            raise ValueError(f"manifest row {index} has unknown evidence tier: {tier!r}")
        for key in ("source_sha256", "target_sha256"):
            if not _valid_sha256(row[key]):
                raise ValueError(f"manifest row {index} has invalid {key}")
        prior_split = scene_splits.setdefault(scene_id, split)
        if prior_split != split:
            raise ValueError(
                f"scene_id {scene_id!r} appears in multiple splits: {prior_split!r}, {split!r}")
    return {
        "n_rows": len(records),
        "n_scenes": len(scene_splits),
        "splits": {split: sum(value == split for value in scene_splits.values())
                   for split in sorted(_SPLITS) if split in scene_splits.values()},
        "evidence_tiers": {
            tier.value: sum(str(row["evidence_tier"]).upper() == tier.value for row in records)
            for tier in EvidenceTier if any(str(row["evidence_tier"]).upper() == tier.value
                                            for row in records)
        },
    }


def reconcile_sample_accounting(counts: Mapping[str, Any]) -> dict[str, Any]:
    """Check the monotonic sample pipeline and exclusion reconciliation."""

    values: dict[str, int] = {}
    for stage in _ACCOUNTING_STAGES:
        value = counts.get(stage)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{stage} must be a non-negative integer")
        values[stage] = value
    for previous, current in zip(_ACCOUNTING_STAGES, _ACCOUNTING_STAGES[1:]):
        if values[previous] < values[current]:
            raise ValueError(f"sample counts must be monotonic: {previous} < {current}")
    excluded = counts.get("excluded", {})
    if not isinstance(excluded, Mapping):
        raise ValueError("excluded must be a mapping of reason to count")
    excluded_total = 0
    for reason, value in excluded.items():
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("exclusion reasons must be non-empty strings")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"excluded[{reason!r}] must be a non-negative integer")
        excluded_total += value
    if values["requested"] != values["evaluated"] + excluded_total:
        raise ValueError(
            "sample accounting drift: requested must equal evaluated + excluded total")
    result = dict(values)
    result["excluded"] = dict(excluded)
    result["excluded_total"] = excluded_total
    return result


def aggregate_scene_metrics(metrics: Iterable[SceneMetric]) -> list[SceneMetric]:
    """Collapse technical repeats to one independent metric per scene."""

    groups: dict[str, list[SceneMetric]] = {}
    for metric in metrics:
        if not _nonempty(metric.scene_id):
            raise ValueError("scene_id must be non-empty")
        groups.setdefault(metric.scene_id, []).append(metric)

    def mean_optional(values: Sequence[float | None]) -> float | None:
        present = [float(value) for value in values if value is not None]
        return float(np.mean(present)) if present else None

    result = []
    for scene_id in sorted(groups):
        rows = groups[scene_id]
        result.append(SceneMetric(
            scene_id=scene_id,
            baseline_delta_e00=float(np.mean([row.baseline_delta_e00 for row in rows])),
            candidate_delta_e00=float(np.mean([row.candidate_delta_e00 for row in rows])),
            source_body="|".join(sorted({str(row.source_body) for row in rows if row.source_body})),
            illumination_id="|".join(sorted({str(row.illumination_id) for row in rows
                                               if row.illumination_id})),
            neutral_baseline=mean_optional([row.neutral_baseline for row in rows]),
            neutral_candidate=mean_optional([row.neutral_candidate for row in rows]),
            chromatic_baseline=mean_optional([row.chromatic_baseline for row in rows]),
            chromatic_candidate=mean_optional([row.chromatic_candidate for row in rows]),
        ))
    return result


def sign_test_p(differences: Sequence[float]) -> float:
    """Exact two-sided sign-test p-value, dropping zero differences."""

    values = [float(value) for value in differences if float(value) != 0.0]
    if not values:
        return 1.0
    positives = sum(value > 0 for value in values)
    negatives = len(values) - positives
    tail = sum(comb(len(values), i) for i in range(min(positives, negatives) + 1))
    return float(min(1.0, 2.0 * tail / (2 ** len(values))))


def bootstrap_mean_ci(
    differences: Sequence[float], n_bootstrap: int = 20_000, seed: int = 0,
) -> tuple[float, float]:
    """Return a percentile bootstrap 95% CI for the mean paired difference."""

    values = np.asarray(list(differences), dtype=float)
    if values.ndim != 1 or values.size == 0:
        raise ValueError("differences must contain at least one value")
    if n_bootstrap <= 0:
        raise ValueError("n_bootstrap must be positive")
    rng = np.random.default_rng(seed)
    samples = np.empty(n_bootstrap, dtype=float)
    for index in range(n_bootstrap):
        samples[index] = np.mean(values[rng.integers(0, values.size, values.size)])
    return float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))


def evaluate_paired(
    metrics: Iterable[SceneMetric], n_bootstrap: int = 20_000, seed: int = 0,
) -> dict[str, Any]:
    """Evaluate a candidate using scene-level paired uncertainty."""

    scenes = aggregate_scene_metrics(metrics)
    if not scenes:
        raise ValueError("at least one scene is required")
    baseline = np.asarray([row.baseline_delta_e00 for row in scenes], dtype=float)
    candidate = np.asarray([row.candidate_delta_e00 for row in scenes], dtype=float)
    differences = baseline - candidate
    ci95 = bootstrap_mean_ci(differences, n_bootstrap=n_bootstrap, seed=seed)

    def optional_improvement(base_key: str, candidate_key: str) -> float | None:
        base = [getattr(row, base_key) for row in scenes]
        new = [getattr(row, candidate_key) for row in scenes]
        if not all(value is not None for value in base + new):
            return None
        return float(np.mean(np.asarray(base, dtype=float) - np.asarray(new, dtype=float)))

    return {
        "n_scenes": len(scenes),
        "mean_baseline": float(np.mean(baseline)),
        "mean_candidate": float(np.mean(candidate)),
        "mean_improvement": float(np.mean(differences)),
        "mean_improvement_pct": float(100.0 * np.mean(differences) / np.mean(baseline))
        if np.mean(baseline) > 0 else None,
        "ci95": list(ci95),
        "sign_test_p": sign_test_p(differences),
        "neutral_mean_improvement": optional_improvement("neutral_baseline", "neutral_candidate"),
        "chromatic_mean_improvement": optional_improvement("chromatic_baseline", "chromatic_candidate"),
        "per_scene": [asdict(scene) | {"improvement": float(scene.baseline_delta_e00 - scene.candidate_delta_e00)}
                      for scene in scenes],
    }


def evaluate_manifest_metrics(
    manifest_rows: Iterable[Mapping[str, Any]],
    metric_rows: Iterable[Mapping[str, Any]],
    n_bootstrap: int = 20_000,
    seed: int = 0,
) -> dict[str, Any]:
    """Join a validated manifest to one precomputed metric row per scene.

    Metric rows intentionally contain already-aligned target-reference errors;
    rendering and ROI extraction stay in the caller so this kernel cannot
    silently change image-processing policy.  Only ``evaluation`` and
    ``lockbox`` scenes are eligible for the paired result.
    """

    manifest = list(manifest_rows)
    manifest_summary = validate_manifest(manifest)
    scene_metadata: dict[str, dict[str, str]] = {}
    for row in manifest:
        scene_metadata.setdefault(str(row["scene_id"]), {
            "split": str(row["split"]),
            "source_body": str(row["source_body"]),
            "illumination_id": str(row["illumination_id"]),
        })
    eligible = {scene_id for scene_id, metadata in scene_metadata.items()
                if metadata["split"] in {"evaluation", "lockbox"}}
    by_scene: dict[str, Mapping[str, Any]] = {}
    required = ("scene_id", "baseline_delta_e00", "candidate_delta_e00")
    for index, row in enumerate(metric_rows, start=1):
        missing = [key for key in required if not _nonempty(row.get(key))]
        if missing:
            raise ValueError(f"metric row {index} missing fields: {', '.join(missing)}")
        scene_id = str(row["scene_id"])
        if scene_id in by_scene:
            raise ValueError(f"duplicate metric row for scene_id {scene_id!r}")
        if scene_id not in eligible:
            raise ValueError(f"metric row {index} is not an evaluation/lockbox scene: {scene_id!r}")
        try:
            baseline = float(row["baseline_delta_e00"])
            candidate = float(row["candidate_delta_e00"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"metric row {index} has non-numeric ΔE00") from exc
        if not np.isfinite([baseline, candidate]).all() or baseline < 0 or candidate < 0:
            raise ValueError(f"metric row {index} has invalid ΔE00")
        by_scene[scene_id] = row
    missing_scenes = sorted(eligible - by_scene.keys())
    if missing_scenes:
        raise ValueError(f"metric rows missing eligible scenes: {', '.join(missing_scenes)}")

    scene_metrics = []
    for scene_id in sorted(eligible):
        row = by_scene[scene_id]
        metadata = scene_metadata[scene_id]
        scene_metrics.append(SceneMetric(
            scene_id=scene_id,
            baseline_delta_e00=float(row["baseline_delta_e00"]),
            candidate_delta_e00=float(row["candidate_delta_e00"]),
            source_body=metadata["source_body"],
            illumination_id=metadata["illumination_id"],
            neutral_baseline=float(row["neutral_baseline"]) if _nonempty(row.get("neutral_baseline")) else None,
            neutral_candidate=float(row["neutral_candidate"]) if _nonempty(row.get("neutral_candidate")) else None,
            chromatic_baseline=float(row["chromatic_baseline"]) if _nonempty(row.get("chromatic_baseline")) else None,
            chromatic_candidate=float(row["chromatic_candidate"]) if _nonempty(row.get("chromatic_candidate")) else None,
        ))
    return {
        "manifest": manifest_summary,
        "paired": evaluate_paired(scene_metrics, n_bootstrap=n_bootstrap, seed=seed),
    }


def check_physical_sanity(
    matrix: Any = None, tone_curve: Sequence[float] | None = None,
    clipping_ratio: float | None = None, lut: Any = None,
    max_condition: float = 10_000.0,
) -> dict[str, Any]:
    """Check finite, monotonic, bounded candidate properties."""

    failures: list[str] = []
    details: dict[str, Any] = {}
    if matrix is not None:
        array = np.asarray(matrix, dtype=float)
        if array.shape != (3, 3) or not np.all(np.isfinite(array)):
            failures.append("matrix_invalid")
        else:
            determinant = float(np.linalg.det(array))
            condition = float(np.linalg.cond(array))
            details.update(matrix_determinant=determinant, matrix_condition=condition)
            if abs(determinant) < 1e-8:
                failures.append("matrix_singular")
            if not np.isfinite(condition) or condition > max_condition:
                failures.append("matrix_ill_conditioned")
    if tone_curve is not None:
        curve = np.asarray(tone_curve, dtype=float)
        if curve.ndim != 1 or curve.size < 2 or not np.all(np.isfinite(curve)):
            failures.append("tone_invalid")
        elif np.any(np.diff(curve) < -1e-10):
            failures.append("tone_nonmonotonic")
    if clipping_ratio is not None:
        clipping = float(clipping_ratio)
        details["clipping_ratio"] = clipping
        if not np.isfinite(clipping) or clipping < 0 or clipping > 1:
            failures.append("clipping_invalid")
        elif clipping > 0.01:
            failures.append("clipping_excessive")
    if lut is not None:
        array = np.asarray(lut, dtype=float)
        if not np.all(np.isfinite(array)):
            failures.append("lut_nonfinite")
        elif np.any(array < 0) or np.any(array > 1):
            failures.append("lut_out_of_range")
    return {"passed": not failures, "failures": failures, **details}


_REQUIRED_CONTROLS = (
    "identity_baseline", "target_reference_shuffle", "source_label_shuffle",
    "holdout_rerun", "chart_positive_control",
)


def validate_controls(controls: Mapping[str, Any]) -> dict[str, Any]:
    """Require every pre-registered falsification/positive control."""

    if not isinstance(controls, Mapping):
        raise ValueError("controls must be a mapping of control name to boolean")
    missing = [name for name in _REQUIRED_CONTROLS if name not in controls]
    failures = [name for name in _REQUIRED_CONTROLS if controls.get(name) is not True]
    return {
        "passed": not missing and not failures,
        "missing": missing,
        "failures": failures,
        "controls": {name: controls.get(name) for name in _REQUIRED_CONTROLS},
    }


def validate_robustness(strata: Mapping[str, Any]) -> dict[str, Any]:
    """Require an explicit boolean result for every robustness stratum."""

    if not isinstance(strata, Mapping) or not strata:
        raise ValueError("robustness must contain at least one stratum")
    missing_or_invalid = [name for name, value in strata.items() if value not in (True, False)]
    failures = [name for name, value in strata.items() if value is False]
    return {
        "passed": not missing_or_invalid and not failures,
        "failures": failures + missing_or_invalid,
        "strata": dict(strata),
    }


def classify_result(
    result: Mapping[str, Any], evidence_tier: EvidenceTier | str,
    lockbox_passed: bool, external_replication: bool,
    validation_passed: bool,
) -> dict[str, Any]:
    """Apply the EAGER evidence and ship gates to a paired result."""

    tier = evidence_tier if isinstance(evidence_tier, EvidenceTier) else EvidenceTier(str(evidence_tier).upper())
    ci = result.get("ci95", (None, None))
    ci_positive = (len(ci) == 2 and ci[0] is not None and float(ci[0]) > 0)
    sign_passed = result.get("sign_test_p") is not None and float(result["sign_test_p"]) < 0.05
    effect_passed = (result.get("mean_improvement_pct") is not None and
                     float(result["mean_improvement_pct"]) >= 5.0)
    subgroup_passed = all(
        result.get(key) is None or float(result[key]) >= 0
        for key in ("neutral_mean_improvement", "chromatic_mean_improvement")
    )
    controls_passed = bool(result.get("controls_passed", False))
    robustness_passed = bool(result.get("robustness_passed", False))
    tier_supports_ship = tier in {EvidenceTier.A, EvidenceTier.B, EvidenceTier.C}
    ship_gate_passed = all((validation_passed, lockbox_passed, ci_positive, sign_passed,
                            effect_passed, subgroup_passed, controls_passed,
                            robustness_passed, tier_supports_ship))
    if tier in {EvidenceTier.D, EvidenceTier.E}:
        classification = "Exploratory"
    elif not validation_passed or not controls_passed:
        classification = "Rejected"
    elif not ship_gate_passed:
        classification = "Inconclusive"
    elif lockbox_passed and external_replication:
        classification = "Verified"
    else:
        classification = "Supported"
    return {
        "evidence_tier": tier.value,
        "ship_gate_passed": ship_gate_passed,
        "classification": classification,
        "checks": {
            "validation": validation_passed,
            "lockbox": lockbox_passed,
            "ci_positive": ci_positive,
            "sign_test": sign_passed,
            "effect_threshold": effect_passed,
            "subgroups": subgroup_passed,
            "controls": controls_passed,
            "robustness": robustness_passed,
            "tier_supports_ship": tier_supports_ship,
        },
    }


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Hash a provenance artifact without loading it all into memory."""

    digest = sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
