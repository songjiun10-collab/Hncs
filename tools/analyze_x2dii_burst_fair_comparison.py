"""`tools/analyze_x2dii_loss_breakdown.py`가 찾은 리키지(kmichels 9장이
같은 버스트라 5-fold CV에서 8/9이 항상 학습셋에 남는 문제)를 고쳐서
25장 전체 비교를 다시 낸다. kmichels 9장의 "global" 점수만 dpreview
25장만으로 학습한 매트릭스(kmichels 리키지 없음, `kmichels_holdout_n9`
비교와 동일 기준)로 교체하고, group1/2 16장은 원래 25-fold CV를
유지한다(이 16장은 서로 다른 ISO/노출이라 kmichels 같은 리터럴 반복
프레임이 아니라 리키지가 훨씬 덜 심각하다고 판단).

  python3 -m tools.analyze_x2dii_burst_fair_comparison

결과: `hybrid_engine/EVALUATION.md` "X2D II 100C dual-illuminant" 절의
"burst-fair 재검증" 기록 참고.
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
OUT_JSON = os.path.join(DPREVIEW_DIR, "burst_fair_comparison_report.json")
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


def _group_cv_per_image(group, reference, weights, seed=0):
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
            [group[nm] for nm in tn], [reference] * len(tn), weights=[weights] * len(tn))
        for i in test_idx:
            pred = raw_baseline.apply_color_matrix(group[names[i]], m)
            out[names[i]] = _mean_de(pred, reference)
    return out


def main():
    reference = chart_baseline.reference_patches_xyz_d50()
    weights = np.array([1.0 if i in NEUTRAL_IDX else CHROMA_WEIGHT for i in range(24)])

    kmichels = _load(os.path.join(KMICHELS_DIR, "raw"), "*.3FR")
    dpreview = _load(os.path.join(DPREVIEW_DIR, "raw"), "*.3fr")
    dp_neutral = {nm: _neutral_ratio(s) for nm, s in dpreview.items()}
    group1 = {nm: s for nm, s in dpreview.items() if dp_neutral[nm][0] < RG_SPLIT}
    group2 = {nm: s for nm, s in dpreview.items() if dp_neutral[nm][0] >= RG_SPLIT}

    combined = {**kmichels, **dpreview}
    names_all = sorted(combined.keys())
    k_all = min(len(names_all), 5)
    rng_all = np.random.RandomState(0)
    folds_all = np.array_split(rng_all.permutation(len(names_all)), k_all)
    de_global_25fold = {}
    for test_idx in folds_all:
        train_idx = [i for i in range(len(names_all)) if i not in set(test_idx.tolist())]
        train_names = [names_all[i] for i in train_idx]
        m = raw_baseline.fit_color_matrix(
            [combined[nm] for nm in train_names], [reference] * len(train_names),
            weights=[weights] * len(train_names))
        for i in test_idx:
            pred = raw_baseline.apply_color_matrix(combined[names_all[i]], m)
            de_global_25fold[names_all[i]] = _mean_de(pred, reference)

    all_dp_names = sorted(dpreview.keys())
    global_matrix_dp_only = raw_baseline.fit_color_matrix(
        [dpreview[nm] for nm in all_dp_names], [reference] * len(all_dp_names),
        weights=[weights] * len(all_dp_names))
    de_global_burst_fair = dict(de_global_25fold)
    for nm in sorted(kmichels.keys()):
        pred = raw_baseline.apply_color_matrix(kmichels[nm], global_matrix_dp_only)
        de_global_burst_fair[nm] = _mean_de(pred, reference)

    names1 = sorted(group1.keys())
    matrix_1 = raw_baseline.fit_color_matrix(
        [group1[nm] for nm in names1], [reference] * len(names1), weights=[weights] * len(names1))
    names2 = sorted(group2.keys())
    matrix_2 = raw_baseline.fit_color_matrix(
        [group2[nm] for nm in names2], [reference] * len(names2), weights=[weights] * len(names2))
    cm1 = np.linalg.inv(matrix_1).T
    cm2 = np.linalg.inv(matrix_2).T

    de_dual = {}
    de_dual.update(_group_cv_per_image(group1, reference, weights))
    de_dual.update(_group_cv_per_image(group2, reference, weights))
    for nm in sorted(kmichels.keys()):
        native_to_xyz, _ = interpolate_dng_matrix(_neutral_ratio(kmichels[nm]), cm1, ILLUM1, cm2, ILLUM2)
        de_dual[nm] = _mean_de(raw_baseline.apply_color_matrix(kmichels[nm], native_to_xyz), reference)

    de_global_arr = np.array([de_global_burst_fair[nm] for nm in names_all])
    de_dual_arr = np.array([de_dual[nm] for nm in names_all])
    diff = de_global_arr - de_dual_arr
    rng2 = np.random.RandomState(1)
    boot = np.array([diff[rng2.randint(0, len(names_all), len(names_all))].mean() for _ in range(20000)])
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])

    print("=== burst-fair 25장 전체(kmichels 리키지 제거) ===")
    print(f"global(burst-fair) = {de_global_arr.mean():.4f}")
    print(f"dual = {de_dual_arr.mean():.4f}")
    print(f"paired diff 평균={diff.mean():.4f}, 95% CI=[{ci_lo:.4f},{ci_hi:.4f}]")
    print(f"wins={int((diff > 0).sum())}, losses={int((diff < 0).sum())}, n={len(names_all)}")
    print(f"improvement_pct={(de_global_arr.mean() - de_dual_arr.mean()) / de_global_arr.mean() * 100:.2f}%")

    result = {
        "global_burst_fair_mean": float(de_global_arr.mean()),
        "dual_mean": float(de_dual_arr.mean()),
        "paired_diff_mean": float(diff.mean()),
        "bootstrap_ci95": [float(ci_lo), float(ci_hi)],
        "wins": int((diff > 0).sum()), "losses": int((diff < 0).sum()), "n": len(names_all),
        "improvement_pct": float((de_global_arr.mean() - de_dual_arr.mean()) / de_global_arr.mean() * 100),
        "note": "kmichels 9장의 global 점수만 dpreview단독학습(burst 리키지 없음)으로 교체, "
                "group1/2 16장은 기존 25-fold CV 유지",
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n저장: {OUT_JSON}")


if __name__ == "__main__":
    main()
