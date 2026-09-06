"""실험4의 D50 편향 근본 수정판. `tools/analyze_x2dii_full_interpolation_end_to_end.py`가
찾은 구조적 편향(모든 매트릭스가 D50 기준이라 g가 입력과 무관하게
illuminant1 쪽으로 쏠림)을 고친다: DNG 스펙 확인 결과
`ColorMatrix1`/`ColorMatrix2`는 원래 XYZ(D50)이 아니라 **각자의
캘리브레이션 조명 자체의 색도**로 매핑해야 한다 - D50 정합(백색점
색순응)은 그 다음 별도 단계다. `chart_baseline.reference_patches_xyz()`로
matrix_1은 D65 색도, matrix_2는 Standard Illuminant A 색도를 목표로
다시 fit하고, 보간 후 최종적으로 (converged g가 추정한 촬영 조명
색도) -> D50로 Bradford 색순응을 한 번 더 거쳐야 기존 D50 기준
ColorChecker 참조값과 ΔE00을 비교할 수 있다.

자기 중립색 self-consistency 확인(이 스크립트 실행 전 별도 확인,
`hybrid_engine/EVALUATION.md` "실험4 - D50 편향 근본 수정" 절 참고):
group1 자기 중립색 -> g=0.9916(기대 1 근처), group2 자기 중립색 ->
g=0.0176(기대 0 근처) - 수정 전(각각 0.86/0.78, 둘 다 illuminant1
쪽으로 쏠림)과 대조적으로 완전히 회복됨.

  python3 -m tools.analyze_x2dii_illuminant_referenced_interpolation
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import colour
import numpy as np

from hybrid_engine.core import chart_baseline, raw_baseline
from hybrid_engine.utils.io import decode_raw_native
from core.dcp_interpolate import interpolate_dng_matrix, _xyz_to_xy

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KMICHELS_DIR = os.path.join(BASE, "datasets/hasselblad/contributed/kmichels-x2dii-2026-07")
DPREVIEW_DIR = os.path.join(BASE, "datasets/hasselblad/contributed/dpreview-x2dii100c-studio-chart-2026-09")
OUT_JSON = os.path.join(DPREVIEW_DIR, "illuminant_referenced_interpolation_report.json")
CHROMA_WEIGHT = 4.0
NEUTRAL_IDX = set(range(18, 24))
RG_SPLIT = 0.5
ILLUM1, ILLUM2 = 21, 17
D65_XY = (0.3127, 0.3290)
STD_A_XY = tuple(colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]["A"])
D50_XY = tuple(chart_baseline.D50_XY)


def _load(raw_dir, pattern):
    out = {}
    for p in sorted(glob.glob(os.path.join(raw_dir, pattern))):
        name = os.path.basename(p)
        try:
            native = decode_raw_native(p)
            s = chart_baseline.detect_and_sample(native)
        except Exception:
            continue
        if s is None:
            continue
        out[name] = s
    return out


def _neutral_ratio(s):
    vals = []
    for i in sorted(NEUTRAL_IDX):
        rgb = np.asarray(s[i], dtype=np.float64)
        if rgb[1] <= 0:
            continue
        vals.append(rgb / rgb[1])
    m = np.mean(vals, axis=0)
    return m / m[1]


def _mean_de(xyz, ref):
    return float(np.mean(chart_baseline.patch_delta_e_xyz_d50(xyz, ref)))


def _fit(samples_dict, names, reference, weights):
    return raw_baseline.fit_color_matrix(
        [samples_dict[nm] for nm in names], [reference] * len(names),
        weights=[weights] * len(names))


def _predict_d50_via_real_interpolation(sample_rgb_24x3, neutral, cm1, cm2):
    """진짜 DNG 알고리즘 - 자기 조명 색도로 보간 -> 추정 촬영조명 색도 ->
    D50 색순응. sample_rgb_24x3: (24,3) 카메라 네이티브 RGB(24패치 전부).
    반환: (24,3) XYZ(D50) 예측값, 수렴한 g."""
    native_to_xyz_row, g = interpolate_dng_matrix(neutral, cm1, ILLUM1, cm2, ILLUM2)
    xyz_as_shot = sample_rgb_24x3 @ native_to_xyz_row  # (24,3), 촬영조명 색도 기준
    neutral_xyz = neutral @ native_to_xyz_row
    est_x, est_y = _xyz_to_xy(neutral_xyz)
    xyz_d50 = colour.chromatic_adaptation(
        xyz_as_shot,
        colour.xy_to_XYZ([est_x, est_y]),
        colour.xy_to_XYZ(D50_XY),
        method="Von Kries", transform="Bradford",
    )
    return xyz_d50, g


def main():
    ref_d50 = chart_baseline.reference_patches_xyz_d50()
    ref_d65 = chart_baseline.reference_patches_xyz(D65_XY)
    ref_a = chart_baseline.reference_patches_xyz(STD_A_XY)
    weights = np.array([1.0 if i in NEUTRAL_IDX else CHROMA_WEIGHT for i in range(24)])

    kmichels = _load(os.path.join(KMICHELS_DIR, "raw"), "*.3FR")
    dpreview = _load(os.path.join(DPREVIEW_DIR, "raw"), "*.3fr")
    dp_neutral = {nm: _neutral_ratio(s) for nm, s in dpreview.items()}
    group1 = {nm: s for nm, s in dpreview.items() if dp_neutral[nm][0] < RG_SPLIT}
    group2 = {nm: s for nm, s in dpreview.items() if dp_neutral[nm][0] >= RG_SPLIT}
    names1, names2 = sorted(group1.keys()), sorted(group2.keys())
    print(f"group1(daylight성) n={len(names1)}, group2(tungsten성) n={len(names2)}, "
          f"kmichels(홀드아웃) n={len(kmichels)}")

    de_real_interp = {}
    g_values = {}

    def _cv_through_interpolation(target_group, target_names, target_ref, other_full_matrix,
                                   target_is_matrix1, seed):
        n = len(target_names)
        k = min(n, 5)
        rng = np.random.RandomState(seed)
        folds = np.array_split(rng.permutation(n), k)
        for test_idx in folds:
            train_idx = [i for i in range(n) if i not in set(test_idx.tolist())]
            train_names = [target_names[i] for i in train_idx]
            held_out_matrix = _fit(target_group, train_names, target_ref, weights)
            cm_held_out = np.linalg.inv(held_out_matrix).T
            cm_other = np.linalg.inv(other_full_matrix).T
            for i in test_idx:
                nm = target_names[i]
                neutral = _neutral_ratio(target_group[nm])
                cm1, cm2 = (cm_held_out, cm_other) if target_is_matrix1 else (cm_other, cm_held_out)
                xyz_d50, g = _predict_d50_via_real_interpolation(
                    np.asarray(target_group[nm], dtype=np.float64), neutral, cm1, cm2)
                de_real_interp[nm] = _mean_de(xyz_d50, ref_d50)
                g_values[nm] = g

    matrix_1_full = _fit(group1, names1, ref_d65, weights)
    matrix_2_full = _fit(group2, names2, ref_a, weights)
    _cv_through_interpolation(group1, names1, ref_d65, matrix_2_full, target_is_matrix1=True, seed=0)
    _cv_through_interpolation(group2, names2, ref_a, matrix_1_full, target_is_matrix1=False, seed=1)

    cm1_full = np.linalg.inv(matrix_1_full).T
    cm2_full = np.linalg.inv(matrix_2_full).T
    for nm in sorted(kmichels.keys()):
        neutral = _neutral_ratio(kmichels[nm])
        xyz_d50, g = _predict_d50_via_real_interpolation(
            np.asarray(kmichels[nm], dtype=np.float64), neutral, cm1_full, cm2_full)
        de_real_interp[nm] = _mean_de(xyz_d50, ref_d50)
        g_values[nm] = g

    # --- burst-fair global 기준선(기존과 동일 방법, D50 기준 그대로) ---
    combined = {**kmichels, **dpreview}
    names_all = sorted(combined.keys())
    k_all = min(len(names_all), 5)
    rng_all = np.random.RandomState(0)
    folds_all = np.array_split(rng_all.permutation(len(names_all)), k_all)
    de_global_25fold = {}
    for test_idx in folds_all:
        train_idx = [i for i in range(len(names_all)) if i not in set(test_idx.tolist())]
        train_names = [names_all[i] for i in train_idx]
        m = _fit(combined, train_names, ref_d50, weights)
        for i in test_idx:
            pred = raw_baseline.apply_color_matrix(combined[names_all[i]], m)
            de_global_25fold[names_all[i]] = _mean_de(pred, ref_d50)
    global_matrix_dp_only = _fit(dpreview, sorted(dpreview.keys()), ref_d50, weights)
    de_global_burst_fair = dict(de_global_25fold)
    for nm in sorted(kmichels.keys()):
        pred = raw_baseline.apply_color_matrix(kmichels[nm], global_matrix_dp_only)
        de_global_burst_fair[nm] = _mean_de(pred, ref_d50)

    de_global_arr = np.array([de_global_burst_fair[nm] for nm in names_all])
    de_real_arr = np.array([de_real_interp[nm] for nm in names_all])
    diff = de_global_arr - de_real_arr
    rng2 = np.random.RandomState(1)
    boot = np.array([diff[rng2.randint(0, len(names_all), len(names_all))].mean() for _ in range(20000)])
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])

    print("\n=== 실험4 D50편향 수정판 - 25장 전체 진짜 보간(일루미넌트 기준 매트릭스) ===")
    print(f"global(burst-fair) = {de_global_arr.mean():.4f}")
    print(f"real-interpolation(일루미넌트 기준, 전체) = {de_real_arr.mean():.4f}")
    print(f"paired diff 평균={diff.mean():.4f}, 95% CI=[{ci_lo:.4f},{ci_hi:.4f}]")
    print(f"wins={int((diff > 0).sum())}, losses={int((diff < 0).sum())}, n={len(names_all)}")
    if ci_lo <= 0:
        print("CI가 0을 걸침 - 유의한 승리가 아니다.")

    print("\n--- group1/group2 개별 ---")
    for label, names in [("group1", names1), ("group2", names2)]:
        real = np.mean([de_real_interp[nm] for nm in names])
        glob_ = np.mean([de_global_burst_fair[nm] for nm in names])
        g_mean = np.mean([g_values[nm] for nm in names])
        print(f"{label}: 진짜보간(일루미넌트기준)={real:.3f}  global={glob_:.3f}  "
              f"평균 g={g_mean:.3f}  차이(global-real)={glob_ - real:+.3f}")

    result = {
        "global_burst_fair_mean": float(de_global_arr.mean()),
        "real_interpolation_illuminant_referenced_mean": float(de_real_arr.mean()),
        "paired_diff_mean": float(diff.mean()),
        "bootstrap_ci95": [float(ci_lo), float(ci_hi)],
        "wins": int((diff > 0).sum()), "losses": int((diff < 0).sum()), "n": len(names_all),
        "ci_straddles_zero": bool(ci_lo <= 0),
        "group1_real_interp_mean": float(np.mean([de_real_interp[nm] for nm in names1])),
        "group1_global_mean": float(np.mean([de_global_burst_fair[nm] for nm in names1])),
        "group1_mean_g": float(np.mean([g_values[nm] for nm in names1])),
        "group2_real_interp_mean": float(np.mean([de_real_interp[nm] for nm in names2])),
        "group2_global_mean": float(np.mean([de_global_burst_fair[nm] for nm in names2])),
        "group2_mean_g": float(np.mean([g_values[nm] for nm in names2])),
        "self_consistency_check": {
            "note": "matrix_1/matrix_2를 각자 조명 색도(D65/StdA)로 fit한 뒤 자기 "
                     "그룹 평균 중립색을 넣었을 때의 g - 1(group1)/0(group2)에 가까울수록 "
                     "정상. 수정 전(D50 기준 fit)은 각각 0.86/0.78이었다.",
        },
        "note": "core/dcp_interpolate.py 자체는 안 건드림 - matrix_1/matrix_2를 D50 대신 "
                "각자의 캘리브레이션 조명 색도(chart_baseline.reference_patches_xyz())로 "
                "다시 fit하고, 보간 후 추정 촬영조명->D50 색순응을 추가한 최초의 end-to-end "
                "검증. .dcp 파일은 이 스크립트가 건드리지 않음(Never-list).",
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n저장: {OUT_JSON}")


if __name__ == "__main__":
    main()
