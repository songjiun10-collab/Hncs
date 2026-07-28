"""hybrid_engine/research/hncs_structural.py(HNCS 실제 4단계 구조를
미러링한 실험 모듈)이 apply_hncs()보다 실제로 ΔE가 개선되는지
leave-one-out 교차검증으로 확인한다. 설계 근거:
docs/superpowers/specs/2026-07-28-hncs-structural-research-design.md

  python3 -m tools.evaluate_hncs_structural
"""
import csv
import glob
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import colour
import cv2
import numpy as np

from brands.hasselblad import apply_hncs
from core.curve import film_curve
from hybrid_engine.core.raw_baseline import apply_color_matrix, fit_color_matrix
from hybrid_engine.research.hncs_structural import (
    apply_chroma_lut, classify_illuminant_cluster, decode_and_white_balance,
)
from hybrid_engine.utils.evaluate import load_image_linear_for_evaluate, mean_delta_e
from hybrid_engine.utils.exif import read_as_shot_neutral
from hybrid_engine.utils.io import decode_raw, decode_raw_native, load_image_linear

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(_ROOT, "raw_calib_cache")
CSV_PATH = os.path.join(_ROOT, "datasets", "hasselblad", "hasselblad_raw_jpeg_pairs.csv")

SAT_MULT_GRID = [0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15]
HUE_SHIFT_GRID = [-6.0, -4.0, -2.0, 0.0, 2.0, 4.0, 6.0]

FILM_CURVE_TOE_LIFT = 0.001
FILM_CURVE_SHOULDER_START = 0.78
FILM_CURVE_WHITE_POINT = 1.0

MATRIX_RIDGE = 1.0  # 클러스터당 3~10쌍뿐이라 3x3(자유도 9) 과적합 억제

# 그리드서치+ΔE 루프가 폴드당 수백 번 반복되므로 축소본으로 처리한다 -
# 3x3 매트릭스와 2-파라미터 chroma LUT는 둘 다 공간 정보가 아니라 색
# 분포에만 의존하는 전역 변환이라 축소가 피팅 품질에 실질적 영향이
# 없다(결과 기록에 한계로 명시).
DOWNSAMPLE_MAX_DIM = 512

_PAIR_DATA_CACHE = {}
_BASELINE_CACHE = {}


def _pair_names():
    """CSV의 jpeg_url basename 목록(13개, 확장자 .jpg 포함) - 실제
    사진 페어만 담고 있고 raw_calib_cache/의 x2dii-chart-* 2개(다른
    데이터셋)는 여기 없다."""
    names = []
    with open(CSV_PATH, newline="") as f:
        for row in csv.DictReader(f):
            names.append(os.path.basename(row["jpeg_url"]))
    return names


def _raw_path_for(jpeg_name):
    matches = [m for m in glob.glob(os.path.join(CACHE_DIR, jpeg_name + ".*"))
               if not m.endswith(".target.jpg")]
    if len(matches) != 1:
        raise FileNotFoundError(f"raw for {jpeg_name}: expected 1 match, got {matches}")
    return matches[0]


def _target_path_for(jpeg_name):
    return os.path.join(CACHE_DIR, jpeg_name + ".target.jpg")


def _resize_max_dim(img, max_dim):
    """긴 변이 max_dim을 넘으면 종횡비 유지한 채 축소. 이미 작으면
    그대로 반환(no-op)."""
    h, w = img.shape[:2]
    scale = min(1.0, max_dim / max(h, w))
    if scale >= 1.0:
        return img
    new_w, new_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    resized = cv2.resize(img.astype(np.float32), (new_w, new_h),
                          interpolation=cv2.INTER_AREA)
    return resized.astype(np.float64)


def load_pairs():
    """13쌍 전부를 dict 리스트로 반환: name/raw_path/target_path/cluster."""
    pairs = []
    for jpeg_name in _pair_names():
        raw_path = _raw_path_for(jpeg_name)
        as_shot_neutral = read_as_shot_neutral(raw_path)
        cluster = classify_illuminant_cluster(as_shot_neutral)
        pairs.append({
            "name": jpeg_name, "raw_path": raw_path,
            "target_path": _target_path_for(jpeg_name), "cluster": cluster,
        })
    return pairs


def _pair_data(pair):
    """(wb_rgb, target_linear) 축소본을 캐시 - RAW 디코드가 느리고
    그리드서치가 같은 페어를 폴드마다 반복 사용하므로 이름으로 캐시."""
    name = pair["name"]
    if name not in _PAIR_DATA_CACHE:
        wb_rgb = _resize_max_dim(decode_and_white_balance(pair["raw_path"]),
                                  DOWNSAMPLE_MAX_DIM)
        target = load_image_linear(pair["target_path"], resize_to=wb_rgb.shape[:2])
        _PAIR_DATA_CACHE[name] = (wb_rgb, target)
    return _PAIR_DATA_CACHE[name]


def _hncs_baseline_and_target(pair):
    """apply_hncs() 공정 비교용 - decode_raw()(WB+libraw sRGB 매트릭스,
    "일반 카메라 JPEG" 근사) 기반 축소본 캐시."""
    name = pair["name"]
    if name not in _BASELINE_CACHE:
        baseline = _resize_max_dim(decode_raw(pair["raw_path"]), DOWNSAMPLE_MAX_DIM)
        target = load_image_linear(pair["target_path"], resize_to=baseline.shape[:2])
        _BASELINE_CACHE[name] = (baseline, target)
    return _BASELINE_CACHE[name]


def fit_matrices(train_pairs):
    """클러스터별 3x3 매트릭스 피팅 (ridge=MATRIX_RIDGE)."""
    by_cluster = {}
    for cluster in ("cluster_a", "cluster_b"):
        cluster_pairs = [p for p in train_pairs if p["cluster"] == cluster]
        sources = [_pair_data(p)[0] for p in cluster_pairs]
        targets = [_pair_data(p)[1] for p in cluster_pairs]
        by_cluster[cluster] = fit_color_matrix(sources, targets, ridge=MATRIX_RIDGE)
    return by_cluster


def fit_chroma_lut_params(train_pairs, matrices):
    """클러스터별 (sat_mult, hue_shift_deg) 그리드서치 - 매트릭스 +
    chroma LUT + 공유 필름커브까지 다 적용한 뒤 타깃과의 평균
    ΔE(CIEDE2000)가 최소인 조합을 그 클러스터의 학습 페어 평균으로
    고른다."""
    by_cluster = {}
    for cluster, matrix in matrices.items():
        cluster_pairs = [p for p in train_pairs if p["cluster"] == cluster]
        best_params, best_de = (1.0, 0.0), float("inf")
        for sat_mult, hue_shift_deg in itertools.product(SAT_MULT_GRID, HUE_SHIFT_GRID):
            des = []
            for p in cluster_pairs:
                wb_rgb, target = _pair_data(p)
                matrixed = apply_color_matrix(wb_rgb, matrix)
                chroma_applied = apply_chroma_lut(matrixed, sat_mult, hue_shift_deg)
                result = film_curve(chroma_applied, toe_lift=FILM_CURVE_TOE_LIFT,
                                     shoulder_start=FILM_CURVE_SHOULDER_START,
                                     white_point=FILM_CURVE_WHITE_POINT)
                des.append(mean_delta_e(result, target))
            mean_de = float(np.mean(des))
            if mean_de < best_de:
                best_de, best_params = mean_de, (sat_mult, hue_shift_deg)
        by_cluster[cluster] = best_params
    return by_cluster


def structural_delta_e(test_pair, matrices, chroma_lut_params):
    wb_rgb, target = _pair_data(test_pair)
    cluster = test_pair["cluster"]
    matrixed = apply_color_matrix(wb_rgb, matrices[cluster])
    sat_mult, hue_shift_deg = chroma_lut_params[cluster]
    chroma_applied = apply_chroma_lut(matrixed, sat_mult, hue_shift_deg)
    result = film_curve(chroma_applied, toe_lift=FILM_CURVE_TOE_LIFT,
                         shoulder_start=FILM_CURVE_SHOULDER_START,
                         white_point=FILM_CURVE_WHITE_POINT)
    return mean_delta_e(result, target)


def _linear_to_uint8_bgr(rgb_linear):
    clipped = np.clip(rgb_linear, 0.0, 1.0)
    encoded = colour.cctf_encoding(clipped, function="sRGB")
    u8 = (np.clip(encoded, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    return u8[:, :, ::-1]


def _uint8_bgr_to_linear(bgr_uint8):
    rgb = bgr_uint8[:, :, ::-1].astype(np.float64) / 255.0
    return colour.cctf_decoding(rgb, function="sRGB")


def apply_hncs_delta_e(test_pair):
    """공정 비교: apply_hncs()도 같은 raw 기반 baseline(decode_raw())에
    적용해서 같은 13쌍 target에 대해 ΔE를 잰다 - 기존 v8~v12 이력의
    RMSE 23.3은 다른 표본/다른 측정 방식이라 그대로 갖다 쓰지 않고 이
    실험 안에서 재측정한다."""
    baseline, target = _hncs_baseline_and_target(test_pair)
    bgr_uint8 = _linear_to_uint8_bgr(baseline)
    result_bgr = apply_hncs(bgr_uint8)
    result_linear = _uint8_bgr_to_linear(result_bgr)
    return mean_delta_e(result_linear, target)


def run_loocv():
    pairs = load_pairs()
    per_fold = []
    for i, held_out in enumerate(pairs):
        train = pairs[:i] + pairs[i + 1:]
        matrices = fit_matrices(train)
        chroma_params = fit_chroma_lut_params(train, matrices)
        de_structural = structural_delta_e(held_out, matrices, chroma_params)
        de_hncs = apply_hncs_delta_e(held_out)
        per_fold.append((held_out["name"], held_out["cluster"], de_structural, de_hncs))
        print(f"  [{held_out['name']}] cluster={held_out['cluster']} "
              f"structural ΔE={de_structural:.3f} apply_hncs ΔE={de_hncs:.3f}",
              flush=True)
    return per_fold


def main():
    per_fold = run_loocv()
    structural_des = [row[2] for row in per_fold]
    hncs_des = [row[3] for row in per_fold]
    mean_structural = float(np.mean(structural_des))
    mean_hncs = float(np.mean(hncs_des))
    improvement_pct = (mean_hncs - mean_structural) / mean_hncs * 100
    print()
    print(f"평균 structural ΔE (CIEDE2000, n={len(structural_des)}): {mean_structural:.3f}")
    print(f"평균 apply_hncs ΔE (CIEDE2000, n={len(hncs_des)}): {mean_hncs:.3f}")
    verdict = "구조적 실험이 이겼다" if improvement_pct > 0 else "apply_hncs()가 더 낫다"
    print(f"개선폭: {improvement_pct:.1f}% ({verdict})")


if __name__ == "__main__":
    main()
