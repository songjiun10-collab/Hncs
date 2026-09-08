"""Generate scene-level NARE metrics from frozen RAW/SOOC-JPEG manifests.

This is deliberately a measurement runner, not a fitting loop: it verifies the
frozen source hashes and one known Picture Style before decoding any RAW file.
Registration, semantic masks, and spatial metrics remain separate NARE gates.
"""

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from hybrid_engine.utils.evaluate import (
    bgr_u8_to_linear_rgb,
    load_image_linear_for_evaluate,
    mean_delta_e,
)
from tools.fit.calibrate import load_neutral_render

from .eager import sha256_file
from .nare import validate_nare_manifest


ImageTransform = Callable[[Any], Any]


def _evaluation_rows(manifest_rows: Iterable[Mapping[str, Any]],
                     expected_picture_style: str) -> list[Mapping[str, Any]]:
    manifest = list(manifest_rows)
    validate_nare_manifest(manifest)
    expected = expected_picture_style.strip()
    if not expected or expected.lower() == "unknown":
        raise ValueError("expected_picture_style must be a known fixed style")
    rows = [row for row in manifest if row["split"] in {"evaluation", "lockbox"}]
    if not rows:
        raise ValueError("NARE manifest contains no evaluation or lockbox rows")
    styles = {str(row["picture_style"]).strip() for row in rows}
    if styles != {expected}:
        raise ValueError("NARE evaluation rows must have exactly the expected picture_style")
    return rows


def _verify_hash(row: Mapping[str, Any], path_key: str, hash_key: str) -> None:
    path = str(row[path_key])
    if sha256_file(path) != str(row[hash_key]).lower():
        raise ValueError(f"NARE {path_key.replace('_path', '')} hash does not match frozen manifest: {path}")


def run_nare_metrics(manifest_rows: Iterable[Mapping[str, Any]], expected_picture_style: str,
                     *, candidate: ImageTransform, foundation: ImageTransform | None = None,
                     max_dim: int = 512) -> list[dict[str, float | str]]:
    """Decode frozen NARE rows and return raw/foundation/candidate ΔE00 per scene.

    ``foundation=None`` is the explicit identity colorimetric-foundation control.
    It is useful for a first renderer comparison but cannot satisfy a claim that
    a separately fitted colorimetric foundation was evaluated.
    """
    if max_dim <= 0:
        raise ValueError("max_dim must be positive")
    rows = _evaluation_rows(manifest_rows, expected_picture_style)
    foundation = foundation or (lambda image: image)
    metrics: list[dict[str, float | str]] = []
    for row in rows:
        _verify_hash(row, "source_path", "source_sha256")
        _verify_hash(row, "target_path", "target_sha256")
        neutral = load_neutral_render(str(row["source_path"]), max_dim=max_dim)
        target = load_image_linear_for_evaluate(str(row["target_path"]), neutral.shape)
        raw_linear = bgr_u8_to_linear_rgb(neutral)
        foundation_linear = bgr_u8_to_linear_rgb(foundation(neutral.copy()))
        candidate_linear = bgr_u8_to_linear_rgb(candidate(neutral.copy()))
        metrics.append({
            "scene_id": str(row["scene_id"]),
            "raw_delta_e00": mean_delta_e(raw_linear, target),
            "foundation_delta_e00": mean_delta_e(foundation_linear, target),
            "candidate_delta_e00": mean_delta_e(candidate_linear, target),
        })
    return metrics
