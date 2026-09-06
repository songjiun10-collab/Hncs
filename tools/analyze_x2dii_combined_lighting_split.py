"""combined_patch_residuals.json 분석에서 무채색 패치가 유채색보다
훨씬 나쁘다는 게 나왔다 - 매트릭스 하나로 여러 조명의 화이트밸런스를
동시에 못 맞추는 패턴과 일치한다는 가설. 이 스크립트는 그 가설을
검증한다: EXIF에 조명 라벨이 없으니(ISO/노출만 있고 CCT 없음) 각
이미지의 무채색 6패치 실측 네이티브 중립색 자체로 2-클러스터링해서
"조명 조건"을 데이터 기반으로 복원하고, 클러스터별로 따로 피팅했을 때
CV가 kmichels 단독(조명 1개) 수준(~2.6~2.8)까지 내려가는지 확인한다.

내려간다면: combined의 12.69는 매트릭스 표현력 부족(조명 2개를 3x3
하나로) 문제라는 게 확인되고, DNG ColorMatrix2(dual-illuminant 보간)로
풀 가치가 있다는 근거가 된다. 안 내려간다면: 가설이 틀렸고 다른
원인(예: dpreview 소스 자체의 노이즈/exposure 아티팩트)을 봐야 한다.

  python3 -m tools.analyze_x2dii_combined_lighting_split
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from hybrid_engine.core import chart_baseline, raw_baseline
from hybrid_engine.utils.io import decode_raw_native

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KMICHELS_DIR = os.path.join(BASE, "datasets", "hasselblad", "contributed",
                             "kmichels-x2dii-2026-07")
DPREVIEW_DIR = os.path.join(BASE, "datasets", "hasselblad", "contributed",
                             "dpreview-x2dii100c-studio-chart-2026-09")

CHROMA_WEIGHT = 4.0
NEUTRAL_PATCH_INDICES = set(range(18, 24))


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


def _weighted_cv(per_image, weights, reference, seed=0):
    names = sorted(per_image.keys())
    n = len(names)
    k = min(n, 5)
    if n < 2:
        return None
    rng = np.random.RandomState(seed)
    folds = np.array_split(rng.permutation(n), k)
    cv_de = np.zeros(n)
    for test_idx in folds:
        train_idx = [i for i in range(n) if i not in set(test_idx.tolist())]
        if not train_idx:
            continue
        train_names = [names[i] for i in train_idx]
        m = raw_baseline.fit_color_matrix(
            [per_image[nm] for nm in train_names],
            [reference] * len(train_names),
            weights=[weights for _ in train_names])
        for i in test_idx:
            pred = raw_baseline.apply_color_matrix(per_image[names[i]], m)
            cv_de[i] = _mean_de(pred, reference)
    return {"n": n, "k": k, "cv_mean": float(cv_de.mean())}


def main():
    reference = chart_baseline.reference_patches_xyz_d50()
    weights = np.array([1.0 if i in NEUTRAL_PATCH_INDICES else CHROMA_WEIGHT
                         for i in range(24)])

    kmichels = _load_samples(os.path.join(KMICHELS_DIR, "raw"), "*.3FR")
    dpreview = _load_samples(os.path.join(DPREVIEW_DIR, "raw"), "*.3fr")
    combined = {**kmichels, **dpreview}
    names = sorted(combined.keys())
    print(f"합계 {len(names)}장 (kmichels {len(kmichels)} + dpreview {len(dpreview)})")

    neutral = {nm: _neutral_ratio(combined[nm]) for nm in names}
    R = np.array([neutral[nm][0] for nm in names])
    B = np.array([neutral[nm][2] for nm in names])

    print(f"\n{'name':<40}{'R/G':>8}{'B/G':>8}{'src':>10}")
    for nm in names:
        src = "kmichels" if nm in kmichels else "dpreview"
        print(f"{nm:<40}{neutral[nm][0]:>8.3f}{neutral[nm][2]:>8.3f}{src:>10}")

    # 1차원 k-means(2클러스터)를 R/G 축으로: 데이터 기반 조명 그룹 복원
    x = R.copy()
    c0, c1 = x.min(), x.max()
    for _ in range(50):
        d0 = np.abs(x - c0)
        d1 = np.abs(x - c1)
        assign = (d1 < d0).astype(int)
        new_c0 = x[assign == 0].mean() if (assign == 0).any() else c0
        new_c1 = x[assign == 1].mean() if (assign == 1).any() else c1
        if np.isclose(new_c0, c0) and np.isclose(new_c1, c1):
            break
        c0, c1 = new_c0, new_c1

    print(f"\nR/G 기준 2-클러스터: center0={c0:.3f}(n={int((assign==0).sum())}), "
          f"center1={c1:.3f}(n={int((assign==1).sum())})")

    group0 = {names[i]: combined[names[i]] for i in range(len(names)) if assign[i] == 0}
    group1 = {names[i]: combined[names[i]] for i in range(len(names)) if assign[i] == 1}

    print(f"\n=== 전체 combined (재확인) ===")
    all_result = _weighted_cv(combined, weights, reference)
    print(json.dumps(all_result, indent=2))

    print(f"\n=== group0 (n={len(group0)}) 단독 ===")
    g0_result = _weighted_cv(group0, weights, reference)
    print(json.dumps(g0_result, indent=2))

    print(f"\n=== group1 (n={len(group1)}) 단독 ===")
    g1_result = _weighted_cv(group1, weights, reference)
    print(json.dumps(g1_result, indent=2))

    out = {
        "assign_by_name": {names[i]: int(assign[i]) for i in range(len(names))},
        "cluster_centers_r_over_g": [float(c0), float(c1)],
        "all_combined_cv": all_result,
        "group0_cv": g0_result,
        "group1_cv": g1_result,
    }
    out_path = os.path.join(DPREVIEW_DIR, "combined_lighting_split_analysis.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\n저장: {out_path}")


if __name__ == "__main__":
    main()
