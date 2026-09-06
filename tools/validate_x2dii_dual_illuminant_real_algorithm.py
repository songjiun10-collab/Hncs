"""배포된 X2D II 100C dual-illuminant DCP(`hasselblad_x2dii_chart.dcp`)를
검증할 때 썼던 보간 방식은 이 프로젝트가 급조한 근사(측정 native
R/G를 두 기준 클러스터의 평균 R/G 사이에서 선형보간)였다. 사용자가
"만들어내"(실제 DNG 스펙이 문서화한 보간 알고리즘을 만들라)로 지시한
뒤 `core/dcp_interpolate.py`에 그 알고리즘(고정점 반복, mired 선형보간,
McCamy CCT)을 구현했다 - 이 스크립트는 그 실제 알고리즘으로 배포
당시의 검증을 다시 돌려서 원래 판정이 그대로 서는지 확인한다.

  python3 -m tools.validate_x2dii_dual_illuminant_real_algorithm
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from hybrid_engine.core import chart_baseline, raw_baseline
from hybrid_engine.utils.io import decode_raw_native
from core.dcp_interpolate import interpolate_dng_matrix

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KMICHELS_DIR = os.path.join(BASE, "datasets", "hasselblad", "contributed",
                             "kmichels-x2dii-2026-07")
DPREVIEW_DIR = os.path.join(BASE, "datasets", "hasselblad", "contributed",
                             "dpreview-x2dii100c-studio-chart-2026-09")
OUT_JSON = os.path.join(DPREVIEW_DIR, "dual_illuminant_real_algorithm_report.json")

CHROMA_WEIGHT = 4.0
NEUTRAL_PATCH_INDICES = set(range(18, 24))
RG_SPLIT = 0.5
ILLUMINANT_1_ENUM = 21  # D65 근사
ILLUMINANT_2_ENUM = 17  # Standard Light A 근사


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


def _group_cv_per_image(group, weights, reference, seed=0):
    names = sorted(group.keys())
    n = len(names)
    k = min(n, 5)
    rng = np.random.RandomState(seed)
    folds = np.array_split(rng.permutation(n), k)
    out = {}
    for test_idx in folds:
        train_idx = [i for i in range(n) if i not in set(test_idx.tolist())]
        tn = [names[i] for i in train_idx]
        m = raw_baseline.fit_color_matrix(
            [group[nm] for nm in tn], [reference] * len(tn),
            weights=[weights for _ in tn])
        for i in test_idx:
            pred = raw_baseline.apply_color_matrix(group[names[i]], m)
            out[names[i]] = _mean_de(pred, reference)
    return out


def main():
    reference = chart_baseline.reference_patches_xyz_d50()
    weights = np.array([1.0 if i in NEUTRAL_PATCH_INDICES else CHROMA_WEIGHT
                         for i in range(24)])

    kmichels = _load_samples(os.path.join(KMICHELS_DIR, "raw"), "*.3FR")
    dpreview = _load_samples(os.path.join(DPREVIEW_DIR, "raw"), "*.3fr")
    dp_neutral = {nm: _neutral_ratio(s) for nm, s in dpreview.items()}
    group1 = {nm: s for nm, s in dpreview.items() if dp_neutral[nm][0] < RG_SPLIT}
    group2 = {nm: s for nm, s in dpreview.items() if dp_neutral[nm][0] >= RG_SPLIT}
    print(f"group1(daylight성) n={len(group1)}, group2(tungsten성) n={len(group2)}, "
          f"kmichels(홀드아웃) n={len(kmichels)}")

    names1 = sorted(group1.keys())
    matrix_1 = raw_baseline.fit_color_matrix(
        [group1[nm] for nm in names1], [reference] * len(names1),
        weights=[weights for _ in names1])
    names2 = sorted(group2.keys())
    matrix_2 = raw_baseline.fit_color_matrix(
        [group2[nm] for nm in names2], [reference] * len(names2),
        weights=[weights for _ in names2])
    cm1 = np.linalg.inv(matrix_1).T
    cm2 = np.linalg.inv(matrix_2).T

    all_dp_names = sorted(dpreview.keys())
    global_matrix_no_km = raw_baseline.fit_color_matrix(
        [dpreview[nm] for nm in all_dp_names], [reference] * len(all_dp_names),
        weights=[weights for _ in all_dp_names])

    km_names = sorted(kmichels.keys())
    de_global_holdout, de_real_interp = [], []
    for nm in km_names:
        km_neutral = _neutral_ratio(kmichels[nm])
        de_global_holdout.append(_mean_de(
            raw_baseline.apply_color_matrix(kmichels[nm], global_matrix_no_km), reference))
        native_to_xyz, g = interpolate_dng_matrix(
            km_neutral, cm1, ILLUMINANT_1_ENUM, cm2, ILLUMINANT_2_ENUM)
        de_real_interp.append(_mean_de(
            raw_baseline.apply_color_matrix(kmichels[nm], native_to_xyz), reference))

    de_global_holdout = np.array(de_global_holdout)
    de_real_interp = np.array(de_real_interp)
    diff = de_global_holdout - de_real_interp
    rng = np.random.RandomState(0)
    boot = np.array([diff[rng.randint(0, len(diff), len(diff))].mean() for _ in range(20000)])
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])

    print(f"\n=== kmichels(n={len(km_names)}) 홀드아웃, 실제 DNG 알고리즘 ===")
    print(f"global(dpreview만 학습) = {de_global_holdout.mean():.4f}")
    print(f"dual-illuminant(실제 알고리즘) = {de_real_interp.mean():.4f}")
    print(f"paired diff 평균={diff.mean():.4f}, 95% CI=[{ci_lo:.4f},{ci_hi:.4f}], "
          f"wins={int((diff>0).sum())}, losses={int((diff<0).sum())}")

    combined = {**kmichels, **dpreview}
    names_all = sorted(combined.keys())
    k_all = min(len(names_all), 5)
    rng_all = np.random.RandomState(0)
    folds_all = np.array_split(rng_all.permutation(len(names_all)), k_all)
    de_global_per_image = {}
    for test_idx in folds_all:
        train_idx = [i for i in range(len(names_all)) if i not in set(test_idx.tolist())]
        train_names = [names_all[i] for i in train_idx]
        m = raw_baseline.fit_color_matrix(
            [combined[nm] for nm in train_names], [reference] * len(train_names),
            weights=[weights for _ in train_names])
        for i in test_idx:
            pred = raw_baseline.apply_color_matrix(combined[names_all[i]], m)
            de_global_per_image[names_all[i]] = _mean_de(pred, reference)

    de_dual_per_image = {}
    de_dual_per_image.update(_group_cv_per_image(group1, weights, reference))
    de_dual_per_image.update(_group_cv_per_image(group2, weights, reference))
    for nm, de in zip(km_names, de_real_interp):
        de_dual_per_image[nm] = float(de)

    de_global_arr = np.array([de_global_per_image[nm] for nm in names_all])
    de_dual_arr = np.array([de_dual_per_image[nm] for nm in names_all])
    diff_all = de_global_arr - de_dual_arr
    rng2 = np.random.RandomState(1)
    boot_all = np.array([diff_all[rng2.randint(0, len(names_all), len(names_all))].mean()
                          for _ in range(20000)])
    ci_lo_all, ci_hi_all = np.percentile(boot_all, [2.5, 97.5])

    print(f"\n=== 25장 전체, 실제 DNG 알고리즘 ===")
    print(f"global(25장 5-fold CV) = {de_global_arr.mean():.4f}")
    print(f"dual-illuminant(실제 알고리즘) = {de_dual_arr.mean():.4f}")
    print(f"paired diff 평균={diff_all.mean():.4f}, 95% CI=[{ci_lo_all:.4f},{ci_hi_all:.4f}], "
          f"wins={int((diff_all>0).sum())}, losses={int((diff_all<0).sum())}")
    print(f"improvement_pct = "
          f"{(de_global_arr.mean()-de_dual_arr.mean())/de_global_arr.mean()*100:.2f}%")
    if ci_lo_all <= 0:
        print("\nCI가 0을 걸침 - 25장 전체 기준으로는 통계적으로 유의한 승리가 아니다.")

    result = {
        "kmichels_holdout_n9": {
            "global_fair_baseline_mean": float(de_global_holdout.mean()),
            "dual_illuminant_real_algorithm_mean": float(de_real_interp.mean()),
            "paired_diff_mean": float(diff.mean()),
            "bootstrap_ci95": [float(ci_lo), float(ci_hi)],
            "wins": int((diff > 0).sum()), "losses": int((diff < 0).sum()),
        },
        "full25": {
            "global_5fold_cv_mean": float(de_global_arr.mean()),
            "dual_illuminant_real_algorithm_mean": float(de_dual_arr.mean()),
            "paired_diff_mean": float(diff_all.mean()),
            "bootstrap_ci95": [float(ci_lo_all), float(ci_hi_all)],
            "wins": int((diff_all > 0).sum()), "losses": int((diff_all < 0).sum()),
            "improvement_pct": float((de_global_arr.mean() - de_dual_arr.mean())
                                      / de_global_arr.mean() * 100),
            "ci_straddles_zero": bool(ci_lo_all <= 0),
        },
        "note": "이전 배포 판정(EVALUATION.md 'X2D II 100C DCP - 단일매트릭스가 못 잡는 "
                "다조명 문제' 절)은 R/G 선형보간 근사로 낸 수치(25장 CI=[+0.81,+7.46])였다. "
                "이 리포트는 실제 DNG 알고리즘(core/dcp_interpolate.py)으로 재검증한 값.",
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n저장: {OUT_JSON}")


if __name__ == "__main__":
    main()
