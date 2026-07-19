"""
[GitHub 이슈 #4 지적 4번] kmichels가 제공한 X2D II ColorChecker Classic
차트 raw 10장으로 raw 베이스라인(rawpy 기본 디코드)의 진짜 색채측정 오차를
재고, 차트 최소자승 매트릭스로 얼마나 줄일 수 있는지 잰다.

  python3 -m tools.analyze_colorchecker_matrix
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from hybrid_engine.utils.io import decode_raw
from hybrid_engine.core import chart_baseline, raw_baseline

SET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "datasets", "hasselblad", "contributed", "kmichels-x2dii-2026-07")
SHIPPED_PROFILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "hybrid_engine", "assets", "profiles", "hasselblad.json")


def _load_chart_samples():
    raw_paths = sorted(glob.glob(os.path.join(SET_DIR, "raw", "*.3FR")))
    per_image = {}
    for raw_path in raw_paths:
        name = os.path.basename(raw_path)
        print(f"  디코드+검출 중: {name}", flush=True)
        linear = decode_raw(raw_path)
        samples = chart_baseline.detect_and_sample(linear)
        if samples is None:
            print(f"    차트 검출 실패, 제외: {name}")
            continue
        per_image[name] = samples
    return per_image


def main():
    reference = chart_baseline.reference_patches_linear_srgb()
    per_image = _load_chart_samples()
    names = sorted(per_image.keys())
    n = len(names)
    print(f"\n검출 성공 {n}장: {names}")
    if n < 2:
        print("이미지가 2장 미만이라 교차검증 불가")
        sys.exit(1)

    # 1) 보정 없는 베이스라인: rawpy 기본 디코드(libraw 기본 매트릭스) vs 참조값
    baseline_de_per_image = {}
    for name in names:
        de = chart_baseline.patch_delta_e(per_image[name], reference)
        baseline_de_per_image[name] = float(np.mean(de))
    baseline_mean = float(np.mean(list(baseline_de_per_image.values())))

    # 2) 기존 raw_baseline_matrix(X1D 실사진 페어로 피팅, hasselblad.json)를
    #    X2D 차트 샘플에 적용했을 때 참조값과 얼마나 가까워지는가
    with open(SHIPPED_PROFILE, encoding="utf-8") as f:
        shipped = json.load(f)
    x1d_matrix = np.asarray(shipped["raw_baseline_matrix"], dtype=np.float64)
    x1d_matrix_de_per_image = {}
    for name in names:
        corrected = raw_baseline.apply_color_matrix(per_image[name], x1d_matrix)
        de = chart_baseline.patch_delta_e(corrected, reference)
        x1d_matrix_de_per_image[name] = float(np.mean(de))
    x1d_matrix_mean = float(np.mean(list(x1d_matrix_de_per_image.values())))

    # 3) 차트로 직접 피팅한 매트릭스: in-sample(전부 pooled) + leave-one-image-out CV
    all_sources = [per_image[name] for name in names]
    all_targets = [reference for _ in names]
    chart_matrix_in_sample = raw_baseline.fit_color_matrix(all_sources, all_targets)
    in_sample_de_per_image = {}
    for name in names:
        corrected = raw_baseline.apply_color_matrix(per_image[name], chart_matrix_in_sample)
        de = chart_baseline.patch_delta_e(corrected, reference)
        in_sample_de_per_image[name] = float(np.mean(de))
    in_sample_mean = float(np.mean(list(in_sample_de_per_image.values())))

    cv_de_per_image = {}
    for i, held_out in enumerate(names):
        train_sources = [per_image[name] for j, name in enumerate(names) if j != i]
        train_targets = [reference for _ in train_sources]
        m = raw_baseline.fit_color_matrix(train_sources, train_targets)
        corrected = raw_baseline.apply_color_matrix(per_image[held_out], m)
        de = chart_baseline.patch_delta_e(corrected, reference)
        cv_de_per_image[held_out] = float(np.mean(de))
    cv_mean = float(np.mean(list(cv_de_per_image.values())))

    print("\n=== 패치 평균 ΔE00 (24패치 x 이미지별 평균의 이미지간 평균) ===")
    print(f"보정 없음(rawpy/libraw 기본 매트릭스):       {baseline_mean:.2f}")
    print(f"기존 raw_baseline_matrix(X1D 실사진 유래):   {x1d_matrix_mean:.2f}")
    print(f"차트 매트릭스 in-sample({n}장 pooled 피팅):     {in_sample_mean:.2f}")
    print(f"차트 매트릭스 leave-one-image-out CV:        {cv_mean:.2f}")
    print(f"\nlibraw 기본 대비 차트 매트릭스 개선(CV 기준): "
          f"{(1 - cv_mean / baseline_mean) * 100:.1f}%")

    print("\n차트 매트릭스(9장 pooled, in-sample 피팅):")
    print(chart_matrix_in_sample)
    print("\n기존 raw_baseline_matrix(X1D 유래, 참고용):")
    print(x1d_matrix)

    report = {
        "n_images": n,
        "images": names,
        "baseline_delta_e_mean": baseline_mean,
        "baseline_delta_e_per_image": baseline_de_per_image,
        "x1d_matrix_applied_delta_e_mean": x1d_matrix_mean,
        "x1d_matrix_applied_delta_e_per_image": x1d_matrix_de_per_image,
        "chart_matrix_in_sample_delta_e_mean": in_sample_mean,
        "chart_matrix_in_sample_delta_e_per_image": in_sample_de_per_image,
        "chart_matrix_cv_delta_e_mean": cv_mean,
        "chart_matrix_cv_delta_e_per_image": cv_de_per_image,
        "chart_matrix_in_sample": chart_matrix_in_sample.tolist(),
        "x1d_matrix_reference": x1d_matrix.tolist(),
    }
    out_path = os.path.join(SET_DIR, "colorchecker_matrix_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n저장: {out_path}")


if __name__ == "__main__":
    main()
