"""
DCP 챠트 매트릭스(현재 LOO ΔE00 2.83)를 더 낮추는 법 조사 - 첫 번째로
쉬운 시도: `raw_baseline.fit_color_matrix()`가 이미 지원하는 patch별
가중 최소자승(`weights=`)으로, 피부톤 인접 패치(dark skin/light skin,
patch 0/1)를 더 강조해서 피팅하면 LOO ΔE00이 낮아지는지 확인한다.
`tools/analyze_camera_native_matrix.py`와 같은 데이터/방법론(공식
kmichels-x2dii-2026-07 챠트 10장, leave-one-image-out) - 가중치만 다름.

  python3 -m tools.evaluate_dcp_weighted_patches
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from hybrid_engine.core import chart_baseline, raw_baseline
from hybrid_engine.utils.io import decode_raw_native

SET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "datasets", "hasselblad", "contributed", "kmichels-x2dii-2026-07")

# patch 0/1 = dark skin/light skin (chart_baseline.PATCH_NAMES 순서)
SKIN_PATCH_IDX = [0, 1]

def _chroma_weight(mult):
    return np.array([1.0 if i in range(18, 24) else mult for i in range(24)])


WEIGHT_SCHEMES = {
    "균등(기존)": np.ones(24),
    "유채색 3.5x": _chroma_weight(3.5),
    "유채색 4x": _chroma_weight(4.0),
    "유채색 4.5x": _chroma_weight(4.5),
    "유채색 5x": _chroma_weight(5.0),
}


def _mean_de(samples_xyz, reference):
    return float(np.mean(chart_baseline.patch_delta_e_xyz_d50(samples_xyz, reference)))


def main():
    reference = chart_baseline.reference_patches_xyz_d50()
    raw_paths = sorted(glob.glob(os.path.join(SET_DIR, "raw", "*.3FR")))
    per_image = {}
    for raw_path in raw_paths:
        name = os.path.basename(raw_path)
        native = decode_raw_native(raw_path)
        samples = chart_baseline.detect_and_sample(native)
        if samples is None:
            print(f"  차트 검출 실패, 제외: {name}")
            continue
        per_image[name] = samples
    names = sorted(per_image.keys())
    n = len(names)
    print(f"검출 성공 {n}장", flush=True)

    for label, patch_weights in WEIGHT_SCHEMES.items():
        cv_per_image = {}
        for i, held_out in enumerate(names):
            train_names = [nm for nm in names if nm != held_out]
            train_sources = [per_image[nm] for nm in train_names]
            train_targets = [reference for _ in train_sources]
            train_weights = [patch_weights for _ in train_sources]
            m = raw_baseline.fit_color_matrix(train_sources, train_targets, weights=train_weights)
            corrected = raw_baseline.apply_color_matrix(per_image[held_out], m)
            cv_per_image[held_out] = _mean_de(corrected, reference)
        cv_mean = float(np.mean(list(cv_per_image.values())))
        print(f"{label}: LOO ΔE00 = {cv_mean:.4f}")


if __name__ == "__main__":
    main()
