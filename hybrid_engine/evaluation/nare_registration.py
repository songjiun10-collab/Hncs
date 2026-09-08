"""Conservative geometry registration for NARE RAW/SOOC comparisons."""

import cv2
import numpy as np


def inspect_registration(source_bgr: np.ndarray, target_bgr: np.ndarray, *,
                         min_correlation: float = 0.6, min_overlap: float = 0.9,
                         max_shift_fraction: float = 0.05) -> dict:
    """Return ECC diagnostics and a gate decision without discarding failures."""
    try:
        _, valid, diagnostic = register_to_target(
            source_bgr, target_bgr, min_correlation=0.0, min_overlap=0.0,
            max_shift_fraction=1.0,
        )
    except ValueError as error:
        return {"passed": False, "failure_reason": str(error)}
    shift_limit = max(source_bgr.shape[:2]) * max_shift_fraction
    shift = float(np.hypot(diagnostic["shift_x_px"], diagnostic["shift_y_px"]))
    failures = []
    if diagnostic["ecc_correlation"] < min_correlation:
        failures.append("correlation")
    if shift > shift_limit:
        failures.append("translation")
    if float(valid.mean()) < min_overlap:
        failures.append("overlap")
    return {**diagnostic, "passed": not failures,
            "failure_reason": ",".join(failures) if failures else None}


def register_to_target(source_bgr: np.ndarray, target_bgr: np.ndarray, *,
                       min_correlation: float = 0.6, min_overlap: float = 0.9,
                       max_shift_fraction: float = 0.05) -> tuple[np.ndarray, np.ndarray, dict]:
    """ECC-align a RAW render to its JPEG with translation only.

    Lens/distortion differences cannot be made trustworthy by a broad warp, so
    this routine only corrects a small global translation.  It fails closed when
    the alignment's correlation, valid overlap, or displacement is insufficient.
    """
    if source_bgr.shape != target_bgr.shape or source_bgr.ndim != 3 or source_bgr.shape[2] != 3:
        raise ValueError("registration_failure: source and target must be same-size BGR images")
    height, width = source_bgr.shape[:2]
    source_gray = cv2.cvtColor(source_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    target_gray = cv2.cvtColor(target_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    warp = np.eye(2, 3, dtype=np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-6)
    try:
        correlation, warp = cv2.findTransformECC(target_gray, source_gray, warp,
                                                  cv2.MOTION_TRANSLATION, criteria, None, 5)
    except cv2.error as error:
        raise ValueError(f"registration_failure: ECC did not converge ({error})") from error
    if not np.isfinite(correlation) or not np.isfinite(warp).all():
        raise ValueError("registration_failure: nonfinite ECC result")
    shift_x, shift_y = float(warp[0, 2]), float(warp[1, 2])
    shift_limit = max(height, width) * max_shift_fraction
    if correlation < min_correlation or np.hypot(shift_x, shift_y) > shift_limit:
        raise ValueError("registration_failure: correlation or translation threshold failed")
    aligned = cv2.warpAffine(source_bgr, warp, (width, height), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                             borderMode=cv2.BORDER_CONSTANT)
    valid = cv2.warpAffine(np.ones((height, width), dtype=np.uint8), warp, (width, height),
                           flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP,
                           borderMode=cv2.BORDER_CONSTANT) > 0
    overlap = float(valid.mean())
    if overlap < min_overlap:
        raise ValueError("registration_failure: valid-overlap threshold failed")
    return aligned, valid, {"ecc_correlation": float(correlation), "overlap_fraction": overlap,
                            "shift_x_px": shift_x, "shift_y_px": shift_y,
                            "long_edge_px": max(height, width)}
