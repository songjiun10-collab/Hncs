"""`tools/refit_x2dii_dual_illuminant.py`(v1)가 배포한 dual-illuminant
DCP는 `ColorMatrix1`/`ColorMatrix2`를 둘 다
`chart_baseline.reference_patches_xyz_d50()`(D50 고정)로 fit했다 - DNG
스펙 확인 결과 이건 틀렸다: 두 매트릭스는 D50이 아니라 **각자의
캘리브레이션 조명 자체의 색도**로 매핑해야 하고, D50 정합은 실제
DNG 리더가 보간 이후 별도로 수행하는 색순응 단계다. 이 구조적 결함
때문에 v1 DCP는 실제 `core/dcp_interpolate.py` 보간을 거치면
group2(텅스텐성) 이미지에서 combined 단일매트릭스보다도 나빴다
(`hybrid_engine/EVALUATION.md` "실험4" 절, ΔE00 19.878 vs 18.998).

이 스크립트(v2)는 `chart_baseline.reference_patches_xyz(illuminant_xy)`
(신규)로 matrix_1은 D65 색도, matrix_2는 Standard Illuminant A 색도로
다시 fit한다. 검증은 `tools/analyze_x2dii_illuminant_referenced_interpolation.py`와
같은 방법론(진짜 `interpolate_dng_matrix()` + 보간후 추정조명->D50
색순응, group1/group2도 in-cluster CV 컨닝 없이 held-out으로 실제
보간을 거침) - 25장 전체 CI=[+5.5509,+9.2794], 승/패=25/0(사용자
"재배포 (권장)" 승인, 2026-09-04). kmichels(중간 조명, n=9)는 여전히
두 매트릭스 어디에도 안 쓰는 완전한 홀드아웃.

`core/dcp_export.py`의 저장 형식(ColorMatrix1/2 + CalibrationIlluminant1/2)
자체는 안 바뀐다 - 바뀐 건 그 매트릭스를 fit할 때 쓰는 참조 XYZ뿐이다.

  python3 -m tools.refit_x2dii_dual_illuminant_v2_illuminant_referenced
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
from core.dcp_export import write_dcp, read_dcp, TAG_PROFILE_EMBED_POLICY
from core.dcp_interpolate import interpolate_dng_matrix, _xyz_to_xy

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KMICHELS_DIR = os.path.join(BASE, "datasets", "hasselblad", "contributed",
                             "kmichels-x2dii-2026-07")
DPREVIEW_DIR = os.path.join(BASE, "datasets", "hasselblad", "contributed",
                             "dpreview-x2dii100c-studio-chart-2026-09")
OUT_DCP = os.path.join(BASE, "hybrid_engine", "assets", "profiles",
                        "hasselblad_x2dii_chart.dcp")
OUT_REPORT = os.path.join(DPREVIEW_DIR, "dual_illuminant_report_v2_illuminant_referenced.json")

UNIQUE_CAMERA_MODEL = "Hasselblad 100-22-Coated6"
PROFILE_NAME = "HNCS X2D II Chart Colorimetric (dual-illuminant v2, illuminant-referenced)"
ILLUMINANT_1_ENUM = 21  # D65 근사 - 저R/G(daylight성) 클러스터
ILLUMINANT_2_ENUM = 17  # Standard Light A 근사 - 고R/G(tungsten성) 클러스터
D65_XY = (0.3127, 0.3290)
STD_A_XY = tuple(colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]["A"])
D50_XY = tuple(chart_baseline.D50_XY)

CHROMA_WEIGHT = 4.0
NEUTRAL_PATCH_INDICES = set(range(18, 24))
RG_SPLIT = 0.5


def _load_samples(raw_dir, pattern):
    per_image = {}
    for raw_path in sorted(glob.glob(os.path.join(raw_dir, pattern))):
        name = os.path.basename(raw_path)
        try:
            native = decode_raw_native(raw_path)
            samples = chart_baseline.detect_and_sample(native)
        except Exception as e:
            print(f"    검출 실패(예외 {type(e).__name__}), 제외: {name}")
            continue
        if samples is None:
            print(f"    검출 실패, 제외: {name}")
            continue
        per_image[name] = samples
    return per_image


def _neutral_ratio(samples):
    vals = []
    for idx in sorted(NEUTRAL_PATCH_INDICES):
        rgb = np.asarray(samples[idx], dtype=np.float64)
        if rgb[1] <= 0:
            continue
        vals.append(rgb / rgb[1])
    m = np.mean(vals, axis=0)
    return m / m[1]


def _mean_de(samples_xyz, reference):
    return float(np.mean(chart_baseline.patch_delta_e_xyz_d50(samples_xyz, reference)))


def _fit(samples_dict, names, reference, weights):
    return raw_baseline.fit_color_matrix(
        [samples_dict[nm] for nm in names], [reference] * len(names),
        weights=[weights] * len(names))


def _predict_d50(sample_rgb_24x3, neutral, cm1_native_to_xyz, cm2_native_to_xyz, ref_d50):
    native_to_xyz_row, g = interpolate_dng_matrix(
        neutral, cm1_native_to_xyz, ILLUMINANT_1_ENUM, cm2_native_to_xyz, ILLUMINANT_2_ENUM)
    xyz_as_shot = sample_rgb_24x3 @ native_to_xyz_row
    neutral_xyz = neutral @ native_to_xyz_row
    est_x, est_y = _xyz_to_xy(neutral_xyz)
    xyz_d50 = colour.chromatic_adaptation(
        xyz_as_shot, colour.xy_to_XYZ([est_x, est_y]), colour.xy_to_XYZ(D50_XY),
        method="Von Kries", transform="Bradford")
    return xyz_d50, g


def main():
    ref_d50 = chart_baseline.reference_patches_xyz_d50()
    ref_d65 = chart_baseline.reference_patches_xyz(D65_XY)
    ref_a = chart_baseline.reference_patches_xyz(STD_A_XY)
    weights = np.array([1.0 if i in NEUTRAL_PATCH_INDICES else CHROMA_WEIGHT for i in range(24)])

    print("kmichels(홀드아웃) 디코드+검출:")
    kmichels = _load_samples(os.path.join(KMICHELS_DIR, "raw"), "*.3FR")
    print(f"  {len(kmichels)}장")
    print("dpreview 디코드+검출:")
    dpreview = _load_samples(os.path.join(DPREVIEW_DIR, "raw"), "*.3fr")
    print(f"  {len(dpreview)}장")

    dp_neutral = {nm: _neutral_ratio(s) for nm, s in dpreview.items()}
    group1 = {nm: s for nm, s in dpreview.items() if dp_neutral[nm][0] < RG_SPLIT}
    group2 = {nm: s for nm, s in dpreview.items() if dp_neutral[nm][0] >= RG_SPLIT}
    names1, names2 = sorted(group1.keys()), sorted(group2.keys())
    print(f"\ngroup1(daylight성) n={len(names1)}, group2(tungsten성) n={len(names2)}, "
          f"kmichels(홀드아웃) n={len(kmichels)}")

    # --- self-consistency 확인(배포 전 최종 게이트) ---
    matrix_1_full = _fit(group1, names1, ref_d65, weights)
    matrix_2_full = _fit(group2, names2, ref_a, weights)
    cm1_full = np.linalg.inv(matrix_1_full).T
    cm2_full = np.linalg.inv(matrix_2_full).T
    g1_neutral = np.mean([dp_neutral[nm] for nm in names1], axis=0)
    g1_neutral = (g1_neutral / g1_neutral[1])
    g2_neutral = np.mean([dp_neutral[nm] for nm in names2], axis=0)
    g2_neutral = (g2_neutral / g2_neutral[1])
    _, g1_self = interpolate_dng_matrix(g1_neutral, cm1_full, ILLUMINANT_1_ENUM, cm2_full, ILLUMINANT_2_ENUM)
    _, g2_self = interpolate_dng_matrix(g2_neutral, cm1_full, ILLUMINANT_1_ENUM, cm2_full, ILLUMINANT_2_ENUM)
    print(f"\nself-consistency: group1 자기중립색 g={g1_self:.4f}(기대 1 근처), "
          f"group2 자기중립색 g={g2_self:.4f}(기대 0 근처)")

    # --- 25장 전체 held-out end-to-end 비교(analyze_x2dii_illuminant_referenced_interpolation.py와 동일 방법론) ---
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
                xyz_d50, g = _predict_d50(
                    np.asarray(target_group[nm], dtype=np.float64), neutral, cm1, cm2, ref_d50)
                de_real_interp[nm] = _mean_de(xyz_d50, ref_d50)
                g_values[nm] = g

    _cv_through_interpolation(group1, names1, ref_d65, matrix_2_full, target_is_matrix1=True, seed=0)
    _cv_through_interpolation(group2, names2, ref_a, matrix_1_full, target_is_matrix1=False, seed=1)
    for nm in sorted(kmichels.keys()):
        neutral = _neutral_ratio(kmichels[nm])
        xyz_d50, g = _predict_d50(
            np.asarray(kmichels[nm], dtype=np.float64), neutral, cm1_full, cm2_full, ref_d50)
        de_real_interp[nm] = _mean_de(xyz_d50, ref_d50)
        g_values[nm] = g

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

    print(f"\n=== 25장 전체 held-out end-to-end(v2, illuminant-referenced) ===")
    print(f"global(burst-fair) = {de_global_arr.mean():.4f}")
    print(f"real-interpolation(v2) = {de_real_arr.mean():.4f}")
    print(f"paired diff 평균={diff.mean():.4f}, 95% CI=[{ci_lo:.4f},{ci_hi:.4f}]")
    print(f"wins={int((diff > 0).sum())}, losses={int((diff < 0).sum())}, n={len(names_all)}")

    report = {
        "camera_model": "Hasselblad X2D II 100C",
        "methodology": "v1(D50 고정 fit)의 구조적 편향(EVALUATION.md 실험3/4)을 고친 v2 - "
                        "matrix_1은 D65 색도, matrix_2는 Standard Illuminant A 색도로 fit "
                        "(chart_baseline.reference_patches_xyz()), 검증은 core/dcp_interpolate.py "
                        "실제 보간 + 보간후 추정조명->D50 색순응을 전 이미지(group1/group2/kmichels "
                        "전부)에 실제로 적용한 held-out end-to-end.",
        "self_consistency": {"group1_own_neutral_g": float(g1_self), "group2_own_neutral_g": float(g2_self)},
        "group1_daylight_like": {
            "n": len(names1), "images": names1,
            "calibration_illuminant": ILLUMINANT_1_ENUM,
            "reference_illuminant_xy": list(D65_XY),
            "measured_native_neutral_g_normalized": g1_neutral.tolist(),
        },
        "group2_tungsten_like": {
            "n": len(names2), "images": names2,
            "calibration_illuminant": ILLUMINANT_2_ENUM,
            "reference_illuminant_xy": list(STD_A_XY),
            "measured_native_neutral_g_normalized": g2_neutral.tolist(),
        },
        "full25_held_out_end_to_end": {
            "n": len(names_all),
            "global_burst_fair_mean": float(de_global_arr.mean()),
            "real_interpolation_mean": float(de_real_arr.mean()),
            "paired_diff_mean": float(diff.mean()),
            "bootstrap_ci95": [float(ci_lo), float(ci_hi)],
            "wins": int((diff > 0).sum()), "losses": int((diff < 0).sum()),
        },
        "color_matrix_1": matrix_1_full.tolist(),
        "color_matrix_2": matrix_2_full.tolist(),
        "dcp_color_matrix_1": cm1_full.tolist(),
        "dcp_color_matrix_2": cm2_full.tolist(),
        "note": "사용자 승인(2026-09-04, 'D50 편향부터 고치고 재판단' -> '재배포 (권장)')으로 배포. "
                "이전 버전은 dual_illuminant_report.json(v1)에 남아있다.",
    }
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n저장: {OUT_REPORT}")

    if ci_lo <= 0:
        print("\nCI가 0을 걸침 - 배포 안 함(dry-run으로 종료).")
        return

    write_dcp(OUT_DCP, camera_model=UNIQUE_CAMERA_MODEL, profile_name=PROFILE_NAME,
              color_matrix_1=report["dcp_color_matrix_1"],
              calibration_illuminant_1=ILLUMINANT_1_ENUM,
              color_matrix_2=report["dcp_color_matrix_2"],
              calibration_illuminant_2=ILLUMINANT_2_ENUM)
    tags = read_dcp(OUT_DCP)
    print(f"\nDCP 재발급(v2, illuminant-referenced): {OUT_DCP}")
    print(f"  UniqueCameraModel = {tags[50708]!r}")
    print(f"  CalibrationIlluminant1 = {tags[50778]}, CalibrationIlluminant2 = {tags[50779]}")
    print(f"  ProfileEmbedPolicy present = {TAG_PROFILE_EMBED_POLICY in tags}")


if __name__ == "__main__":
    main()
