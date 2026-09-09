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


CARE_TARGET_KINDS = frozenset({"none", "sooc"})


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
    if value.size == 0:
        raise ValueError("CARE image must not be empty")
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
    delta_e00 = float(mean_delta_e(reference, perturbed))
    if not math.isfinite(delta_e00) or delta_e00 < 0:
        raise ValueError("CARE delta_e00 must be finite and non-negative")
    if control_delta_e00 is not None:
        if not math.isfinite(float(control_delta_e00)) or control_delta_e00 < 0:
            raise ValueError("CARE control_delta_e00 must be finite and non-negative")
    return {"delta_e00": delta_e00, "control_delta_e00": control_delta_e00}


def run_care_response(image: Any, transform, *, preprocess=None,
                      perturbations: list[dict[str, Any]] | None = None,
                      include_identity_control: bool = True) -> list[dict[str, Any]]:
    """Run the frozen perturbation grid for one linear RGB capture.

    ``preprocess`` is CARE's fixed input conversion P.  It is applied to both the
    candidate look and the identity control so quantization or input conversion
    cannot be mistaken for look sensitivity.  The default is the identity map.
    """
    image = _linear_rgb(image)
    preprocess = (lambda value: value) if preprocess is None else preprocess
    perturbations = build_perturbations() if perturbations is None else list(perturbations)

    baseline_input = _linear_rgb(preprocess(image.copy()))
    baseline = _linear_rgb(transform(baseline_input.copy()))
    records = []
    for perturbation in perturbations:
        kind = perturbation.get("kind")
        if kind == "exposure":
            changed = apply_exposure(image, perturbation["ev"])
        elif kind == "wb_gain":
            changed = apply_wb_gain(image, red=perturbation["red"], blue=perturbation["blue"])
        else:
            raise ValueError(f"CARE unsupported perturbation kind: {kind!r}")

        changed_input = _linear_rgb(preprocess(changed.copy()))
        output = _linear_rgb(transform(changed_input.copy()))
        control = None
        if include_identity_control:
            control = compare_response(baseline_input, changed_input)["delta_e00"]
        response = compare_response(baseline, output, control_delta_e00=control)
        records.append({**perturbation, "response_delta_e00": response["delta_e00"],
                        "control_delta_e00": response["control_delta_e00"]})
    return records


def _is_numeric_metric(value: Any) -> bool:
    return isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(
        value, (bool, np.bool_)
    )


def validate_care_record(record: dict[str, Any]) -> dict[str, Any]:
    """Validate claim routing for one CARE record.

    CARE only distinguishes records without a manufacturer target (``none``) and
    records with a verified same-capture SOOC target (``sooc``).  Preview and
    chart comparisons belong to their separate exploratory/colorimetric paths.
    """
    if not isinstance(record, dict):
        raise ValueError("CARE record must be a dictionary")

    capture_id = record.get("capture_id")
    if not isinstance(capture_id, str) or not capture_id.strip():
        raise ValueError("CARE record requires a non-empty string capture_id")

    target_kind = record.get("target_kind")
    if not isinstance(target_kind, str) or target_kind not in CARE_TARGET_KINDS:
        allowed = ", ".join(sorted(CARE_TARGET_KINDS))
        raise ValueError(f"CARE target_kind must be one of: {allowed}")

    delta = record.get("delta_e00")
    if target_kind == "none":
        if delta is not None:
            raise ValueError("CARE target-free records must not contain fidelity ΔE00")
        record = dict(record)
        record["claim_level"] = "diagnostic"
        return record

    if (delta is None or not _is_numeric_metric(delta)
            or not math.isfinite(float(delta)) or float(delta) < 0):
        raise ValueError("CARE targeted records require finite non-negative delta_e00")
    if record.get("scene_reviewed") is not True:
        raise ValueError("CARE inferential records require reviewed scenes")
    record = dict(record)
    record["claim_level"] = "targeted_response"
    return record
