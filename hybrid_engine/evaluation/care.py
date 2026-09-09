"""CARE counterfactual appearance response primitives.

This module deliberately measures response between two outputs.  It does not
claim that an output matches a manufacturer JPEG unless a separate target is
present and routed through NARE.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from hybrid_engine.utils.evaluate import mean_delta_e


def build_perturbations() -> list[dict[str, Any]]:
    """Return the frozen first-version CARE perturbation grid."""
    result = [{"kind": "exposure", "ev": value}
              for value in (-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0)]
    result.extend({"kind": "wb_gain", "red": value, "blue": 1.0}
                  for value in (0.9, 1.0, 1.1))
    result.extend({"kind": "wb_gain", "red": 1.0, "blue": value}
                  for value in (0.9, 1.0, 1.1))
    return result


def _linear_rgb(image: Any) -> np.ndarray:
    value = np.asarray(image)
    if value.ndim < 3 or value.shape[-1] != 3:
        raise ValueError("CARE image must have shape (..., 3)")
    if not np.issubdtype(value.dtype, np.number) or not np.isfinite(value).all():
        raise ValueError("CARE image must contain finite numeric values")
    return value.astype(np.float64, copy=False)


def apply_exposure(image: Any, ev: float) -> np.ndarray:
    """Apply an exposure offset to linear RGB without clipping."""
    image = _linear_rgb(image)
    if not isinstance(ev, (int, float)) or not math.isfinite(float(ev)):
        raise ValueError("CARE exposure must be finite")
    return image * (2.0 ** float(ev))


def apply_wb_gain(image: Any, *, red: float, blue: float) -> np.ndarray:
    """Apply channel gains to RGB linear data; green remains unchanged."""
    image = _linear_rgb(image)
    gains = np.asarray([red, 1.0, blue], dtype=np.float64)
    if not np.isfinite(gains).all() or np.any(gains < 0):
        raise ValueError("CARE white-balance gains must be finite and non-negative")
    return image * gains


def compare_response(reference: Any, perturbed: Any,
                     *, control_delta_e00: float | None = None) -> dict[str, float | None]:
    """Summarize response magnitude between two linear RGB outputs."""
    reference = _linear_rgb(reference)
    perturbed = _linear_rgb(perturbed)
    if reference.shape != perturbed.shape:
        raise ValueError(f"CARE shape mismatch: {reference.shape} vs {perturbed.shape}")
    result = {"delta_e00": mean_delta_e(reference, perturbed),
              "control_delta_e00": control_delta_e00}
    if control_delta_e00 is not None:
        if not math.isfinite(float(control_delta_e00)) or control_delta_e00 < 0:
            raise ValueError("CARE control_delta_e00 must be finite and non-negative")
    return result


def run_care_response(image: Any, transform, *, perturbations: list[dict[str, Any]] | None = None,
                      include_identity_control: bool = True) -> list[dict[str, Any]]:
    """Run the frozen perturbation grid for one linear RGB capture."""
    image = _linear_rgb(image)
    perturbations = build_perturbations() if perturbations is None else list(perturbations)
    baseline = _linear_rgb(transform(image.copy()))
    records = []
    for perturbation in perturbations:
        kind = perturbation.get("kind")
        if kind == "exposure":
            changed = apply_exposure(image, perturbation["ev"])
        elif kind == "wb_gain":
            changed = apply_wb_gain(image, red=perturbation["red"], blue=perturbation["blue"])
        else:
            raise ValueError(f"CARE unsupported perturbation kind: {kind!r}")
        output = _linear_rgb(transform(changed.copy()))
        control = None
        if include_identity_control:
            control = compare_response(image, changed)["delta_e00"]
        response = compare_response(baseline, output, control_delta_e00=control)
        records.append({**perturbation, "response_delta_e00": response["delta_e00"],
                        "control_delta_e00": response["control_delta_e00"]})
    return records


def validate_care_record(record: dict[str, Any]) -> dict[str, Any]:
    """Validate claim routing for one CARE record."""
    if not isinstance(record, dict) or not str(record.get("capture_id", "")).strip():
        raise ValueError("CARE record requires capture_id")
    target_kind = str(record.get("target_kind", "")).strip()
    if not target_kind:
        raise ValueError("CARE record requires target_kind")
    delta = record.get("delta_e00")
    if target_kind == "none":
        if delta is not None:
            raise ValueError("CARE target-free records must not contain fidelity ΔE00")
        record = dict(record)
        record["claim_level"] = "diagnostic"
        return record
    if delta is None or not isinstance(delta, (int, float)) or not math.isfinite(float(delta)):
        raise ValueError("CARE targeted records require finite delta_e00")
    if record.get("scene_reviewed") is not True:
        raise ValueError("CARE inferential records require reviewed scenes")
    record = dict(record)
    record["claim_level"] = "targeted_response"
    return record
