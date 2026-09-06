"""실험4 - 재배포 여부 재판단. 기존의 모든 "dual-illuminant 25장 검증"
(`tools/refit_x2dii_dual_illuminant.py`, `tools/validate_x2dii_dual_illuminant_real_algorithm.py`,
`tools/analyze_x2dii_burst_fair_comparison.py` 전부 포함)이 공유하는
결함을 고친다: group1/group2 16장의 "dual" 점수는 **각 이미지가 자기
클러스터에 속한다는 걸 이미 아는 것처럼** 그 클러스터 내부 CV로만
냈다 - `core/dcp_interpolate.py`의 실제 보간 함수를 한 번도 거치지
않았다. kmichels 9장만 진짜 보간을 거쳤다.

`hybrid_engine/EVALUATION.md`의 "RawTherapee 교차검증" 절이 찾은
구조적 편향(두 매트릭스 다 D50 기준이라 g가 입력과 무관하게
illuminant1 쪽으로 쏠림, group2 자기 중립색조차 g=0.7754)이 사실이면,
group2(텅스텐성) 이미지를 실제 보간에 통과시켰을 때 지금까지 보고된
"group2 CV=5.00"보다 훨씬 나쁘게 나와야 한다 - 그게 이 스크립트가
확인하는 것. 25장 전체를 **전부** `interpolate_dng_matrix()`를 거쳐
평가한 최초의 end-to-end 검증.

방법: group1/group2 각각 5-fold CV로 매트릭스1/매트릭스2 후보를
홀드아웃 학습(같은 폴드에 함께 있는 반대쪽 그룹 전체로 다른 쪽
매트릭스도 학습), 홀드아웃된 이미지의 실측 중립색을 그 폴드의
matrix_1/matrix_2로 `interpolate_dng_matrix()`에 넣어 진짜 보간
매트릭스를 얻고 ΔE00을 잰다. kmichels는 dpreview 전체로 학습한
matrix_1/matrix_2로 순수 홀드아웃(리키지 없음, 기존과 동일).

  python3 -m tools.analyze_x2dii_full_interpolation_end_to_end
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
KMICHELS_DIR = os.path.join(BASE, "datasets/hasselblad/contributed/kmichels-x2dii-2026-07")
DPREVIEW_DIR = os.path.join(BASE, "datasets/hasselblad/contributed/dpreview-x2dii100c-studio-chart-2026-09")
OUT_JSON = os.path.join(DPREVIEW_DIR, "full_interpolation_end_to_end_report.json")
CHROMA_WEIGHT = 4.0
NEUTRAL_IDX = set(range(18, 24))
RG_SPLIT = 0.5
ILLUM1, ILLUM2 = 21, 17


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


def main():
    reference = chart_baseline.reference_patches_xyz_d50()
    weights = np.array([1.0 if i in NEUTRAL_IDX else CHROMA_WEIGHT for i in range(24)])

    kmichels = _load(os.path.join(KMICHELS_DIR, "raw"), "*.3FR")
    dpreview = _load(os.path.join(DPREVIEW_DIR, "raw"), "*.3fr")
    dp_neutral = {nm: _neutral_ratio(s) for nm, s in dpreview.items()}
    group1 = {nm: s for nm, s in dpreview.items() if dp_neutral[nm][0] < RG_SPLIT}
    group2 = {nm: s for nm, s in dpreview.items() if dp_neutral[nm][0] >= RG_SPLIT}
    names1, names2 = sorted(group1.keys()), sorted(group2.keys())
    print(f"group1(daylight성) n={len(names1)}, group2(tungsten성) n={len(names2)}, "
          f"kmichels(홀드아웃) n={len(kmichels)}")

    # --- group1/group2를 진짜 interpolate_dng_matrix()에 통과시켜서
    # 홀드아웃 평가(각 폴드마다 held-out 이미지 쪽 그룹만 홀드아웃,
    # 반대쪽 그룹은 전량 학습에 씀 - 배포된 DCP의 matrix_2/matrix_1과
    # 가장 가까운 조건) ---
    de_real_interp = {}

    def _cv_through_interpolation(target_group, target_names, other_full_matrix,
                                   target_is_matrix1, seed=0):
        n = len(target_names)
        k = min(n, 5)
        rng = np.random.RandomState(seed)
        folds = np.array_split(rng.permutation(n), k)
        for test_idx in folds:
            train_idx = [i for i in range(n) if i not in set(test_idx.tolist())]
            train_names = [target_names[i] for i in train_idx]
            held_out_matrix = _fit(target_group, train_names, reference, weights)
            cm_held_out = np.linalg.inv(held_out_matrix).T
            cm_other = np.linalg.inv(other_full_matrix).T
            for i in test_idx:
                nm = target_names[i]
                neutral = _neutral_ratio(target_group[nm])
                if target_is_matrix1:
                    native_to_xyz, g = interpolate_dng_matrix(
                        neutral, cm_held_out, ILLUM1, cm_other, ILLUM2)
                else:
                    native_to_xyz, g = interpolate_dng_matrix(
                        neutral, cm_other, ILLUM1, cm_held_out, ILLUM2)
                de_real_interp[nm] = _mean_de(
                    raw_baseline.apply_color_matrix(target_group[nm], native_to_xyz), reference)

    matrix_1_full = _fit(group1, names1, reference, weights)
    matrix_2_full = _fit(group2, names2, reference, weights)
    _cv_through_interpolation(group1, names1, matrix_2_full, target_is_matrix1=True, seed=0)
    _cv_through_interpolation(group2, names2, matrix_1_full, target_is_matrix1=False, seed=1)

    cm1_full = np.linalg.inv(matrix_1_full).T
    cm2_full = np.linalg.inv(matrix_2_full).T
    for nm in sorted(kmichels.keys()):
        neutral = _neutral_ratio(kmichels[nm])
        native_to_xyz, g = interpolate_dng_matrix(neutral, cm1_full, ILLUM1, cm2_full, ILLUM2)
        de_real_interp[nm] = _mean_de(
            raw_baseline.apply_color_matrix(kmichels[nm], native_to_xyz), reference)

    # --- burst-fair global 기준선(실험1과 동일 방법) ---
    combined = {**kmichels, **dpreview}
    names_all = sorted(combined.keys())
    k_all = min(len(names_all), 5)
    rng_all = np.random.RandomState(0)
    folds_all = np.array_split(rng_all.permutation(len(names_all)), k_all)
    de_global_25fold = {}
    for test_idx in folds_all:
        train_idx = [i for i in range(len(names_all)) if i not in set(test_idx.tolist())]
        train_names = [names_all[i] for i in train_idx]
        m = _fit(combined, train_names, reference, weights)
        for i in test_idx:
            pred = raw_baseline.apply_color_matrix(combined[names_all[i]], m)
            de_global_25fold[names_all[i]] = _mean_de(pred, reference)
    global_matrix_dp_only = _fit(dpreview, sorted(dpreview.keys()), reference, weights)
    de_global_burst_fair = dict(de_global_25fold)
    for nm in sorted(kmichels.keys()):
        pred = raw_baseline.apply_color_matrix(kmichels[nm], global_matrix_dp_only)
        de_global_burst_fair[nm] = _mean_de(pred, reference)

    # --- 참고용: 기존 방식(그룹별 in-cluster CV, 보간 안 거침) ---
    def _group_cv_no_interp(group, names, seed=0):
        n = len(names)
        k = min(n, 5)
        rng = np.random.RandomState(seed)
        folds = np.array_split(rng.permutation(n), k)
        out = {}
        for test_idx in folds:
            train_idx = [i for i in range(n) if i not in set(test_idx.tolist())]
            tn = [names[i] for i in train_idx]
            m = _fit(group, tn, reference, weights)
            for i in test_idx:
                pred = raw_baseline.apply_color_matrix(group[names[i]], m)
                out[names[i]] = _mean_de(pred, reference)
        return out

    de_old_no_interp = {}
    de_old_no_interp.update(_group_cv_no_interp(group1, names1, seed=0))
    de_old_no_interp.update(_group_cv_no_interp(group2, names2, seed=0))
    for nm, de in de_real_interp.items():
        if nm in kmichels:
            de_old_no_interp[nm] = de  # kmichels는 원래도 보간 거침, 동일

    de_global_arr = np.array([de_global_burst_fair[nm] for nm in names_all])
    de_real_arr = np.array([de_real_interp[nm] for nm in names_all])
    de_old_arr = np.array([de_old_no_interp[nm] for nm in names_all])

    diff = de_global_arr - de_real_arr
    rng2 = np.random.RandomState(1)
    boot = np.array([diff[rng2.randint(0, len(names_all), len(names_all))].mean() for _ in range(20000)])
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])

    print("\n=== 실험4 - 25장 전체를 진짜 interpolate_dng_matrix()로 평가(최초 end-to-end) ===")
    print(f"global(burst-fair) = {de_global_arr.mean():.4f}")
    print(f"real-interpolation(전체) = {de_real_arr.mean():.4f}")
    print(f"(참고) 기존 방식(그룹은 in-cluster CV로 컨닝, kmichels만 진짜 보간) = {de_old_arr.mean():.4f}")
    print(f"paired diff(global-real) 평균={diff.mean():.4f}, 95% CI=[{ci_lo:.4f},{ci_hi:.4f}]")
    print(f"wins={int((diff > 0).sum())}, losses={int((diff < 0).sum())}, n={len(names_all)}")
    if ci_lo <= 0:
        print("CI가 0을 걸침 - 진짜 보간 기준으로는 유의한 승리가 아니다.")

    print("\n--- group1/group2만 따로: 진짜 보간 vs in-cluster CV(컨닝) ---")
    for label, names in [("group1", names1), ("group2", names2)]:
        real = np.mean([de_real_interp[nm] for nm in names])
        cheat = np.mean([de_old_no_interp[nm] for nm in names])
        print(f"{label}: 진짜 보간={real:.3f}  in-cluster CV(컨닝)={cheat:.3f}  차이={real - cheat:+.3f}")

    result = {
        "global_burst_fair_mean": float(de_global_arr.mean()),
        "real_interpolation_full25_mean": float(de_real_arr.mean()),
        "old_method_incluster_cv_mean": float(de_old_arr.mean()),
        "paired_diff_mean": float(diff.mean()),
        "bootstrap_ci95": [float(ci_lo), float(ci_hi)],
        "wins": int((diff > 0).sum()), "losses": int((diff < 0).sum()), "n": len(names_all),
        "ci_straddles_zero": bool(ci_lo <= 0),
        "group1_real_interp_mean": float(np.mean([de_real_interp[nm] for nm in names1])),
        "group1_incluster_cv_mean": float(np.mean([de_old_no_interp[nm] for nm in names1])),
        "group2_real_interp_mean": float(np.mean([de_real_interp[nm] for nm in names2])),
        "group2_incluster_cv_mean": float(np.mean([de_old_no_interp[nm] for nm in names2])),
        "note": "group1/group2도 interpolate_dng_matrix()를 실제로 통과시킨 최초의 25장 "
                "전체 end-to-end 검증 - 이전 버전들은 group1/group2에 in-cluster CV를 "
                "써서 보간 함수를 안 거쳤다(EVALUATION.md D50 편향 절 참고).",
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n저장: {OUT_JSON}")


if __name__ == "__main__":
    main()
