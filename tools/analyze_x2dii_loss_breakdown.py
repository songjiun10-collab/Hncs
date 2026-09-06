"""X2D II 100C dual-illuminant DCP를 25장 전체(kmichels+dpreview)로
검증했을 때 "global(단일매트릭스 5-fold CV)"이 진 9건이 전부 kmichels인
현상을 진단한다 - `hybrid_engine/EVALUATION.md` "정정(...) 진짜 DNG
보간 알고리즘..." 절에서 발견한 25장 CI가 0을 걸치는 문제의 원인
조사. kmichels 9장은 같은 촬영 세션(94초 버스트)이라 5-fold CV에서
9장 중 8장이 항상 학습셋에 남는다 - 이게 global 쪽에만 부당하게
유리한 리키지였다는 걸 이 스크립트의 손실 내역이 보여준다(이 발견이
`tools/analyze_x2dii_burst_fair_comparison.py`의 동기가 됐다).

  python3 -m tools.analyze_x2dii_loss_breakdown
"""
import glob
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from hybrid_engine.core import chart_baseline, raw_baseline
from hybrid_engine.utils.io import decode_raw_native
from core.dcp_interpolate import interpolate_dng_matrix

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KMICHELS_DIR = os.path.join(BASE, "datasets/hasselblad/contributed/kmichels-x2dii-2026-07")
DPREVIEW_DIR = os.path.join(BASE, "datasets/hasselblad/contributed/dpreview-x2dii100c-studio-chart-2026-09")
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
    de_global_per_image = {}
    for test_idx in folds_all:
        train_idx = [i for i in range(len(names_all)) if i not in set(test_idx.tolist())]
        train_names = [names_all[i] for i in train_idx]
        m = raw_baseline.fit_color_matrix(
            [combined[nm] for nm in train_names], [reference] * len(train_names),
            weights=[weights] * len(train_names))
        for i in test_idx:
            pred = raw_baseline.apply_color_matrix(combined[names_all[i]], m)
            de_global_per_image[names_all[i]] = _mean_de(pred, reference)

    de_dual_per_image = {}
    de_dual_per_image.update(_group_cv_per_image(group1, reference, weights))
    de_dual_per_image.update(_group_cv_per_image(group2, reference, weights))

    names1 = sorted(group1.keys())
    matrix_1 = raw_baseline.fit_color_matrix(
        [group1[nm] for nm in names1], [reference] * len(names1), weights=[weights] * len(names1))
    names2 = sorted(group2.keys())
    matrix_2 = raw_baseline.fit_color_matrix(
        [group2[nm] for nm in names2], [reference] * len(names2), weights=[weights] * len(names2))
    cm1 = np.linalg.inv(matrix_1).T
    cm2 = np.linalg.inv(matrix_2).T
    for nm in sorted(kmichels.keys()):
        native_to_xyz, _ = interpolate_dng_matrix(_neutral_ratio(kmichels[nm]), cm1, ILLUM1, cm2, ILLUM2)
        de_dual_per_image[nm] = _mean_de(
            raw_baseline.apply_color_matrix(kmichels[nm], native_to_xyz), reference)

    rows = []
    for nm in names_all:
        src = "kmichels" if nm in kmichels else ("group1" if nm in group1 else "group2")
        g_de, d_de = de_global_per_image[nm], de_dual_per_image[nm]
        rows.append((src, nm, g_de, d_de, g_de - d_de))
    rows.sort(key=lambda r: r[4])

    print(f"{'src':<10}{'name':<40}{'global':>8}{'dual':>8}{'diff':>8}")
    for src, nm, g, d, diff in rows:
        tag = "LOSS" if diff < 0 else ""
        print(f"{src:<10}{nm:<40}{g:>8.2f}{d:>8.2f}{diff:>8.2f}  {tag}")

    losses = [r for r in rows if r[4] < 0]
    wins = [r for r in rows if r[4] >= 0]
    print(f"\n손실 {len(losses)}건, 소스별: {Counter(r[0] for r in losses)}")
    print(f"승리 {len(wins)}건, 소스별: {Counter(r[0] for r in wins)}")


if __name__ == "__main__":
    main()
