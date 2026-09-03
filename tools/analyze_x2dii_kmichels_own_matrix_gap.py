"""kmichels 9장(자기 세션 전용 데이터)에 직접 fit한 매트릭스가 있다면
얼마나 좋을지("오라클" 상한)를 재서, dual-illuminant 보간의
kmichels-홀드아웃 결과(`tools/validate_x2dii_dual_illuminant_real_algorithm.py`
의 `kmichels_holdout_n9` = 15.6459)와의 격차를 정량화한다. kmichels
자체 조명으로 캘리브레이션한 전용 매트릭스가 없다는 게 지금 얼마나
비용이 큰지 보여주는 캐리브레이션 - 배포 여부와 무관하게 기록해둘
캐비어트.

  python3 -m tools.analyze_x2dii_kmichels_own_matrix_gap
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from hybrid_engine.core import chart_baseline, raw_baseline
from hybrid_engine.utils.io import decode_raw_native

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KMICHELS_DIR = os.path.join(BASE, "datasets/hasselblad/contributed/kmichels-x2dii-2026-07")
CHROMA_WEIGHT = 4.0
NEUTRAL_IDX = set(range(18, 24))

# 대조값(다른 스크립트/리포트에서 이미 낸 결과, 재실행 없이 비교만 함)
DUAL_ILLUMINANT_HOLDOUT_DE = 15.6459  # dual_illuminant_real_algorithm_report.json kmichels_holdout_n9
GLOBAL_DP_ONLY_HOLDOUT_DE = 16.0510   # 같은 리포트의 global_fair_baseline_mean


def _load(raw_dir, pattern):
    out = {}
    for p in sorted(glob.glob(os.path.join(raw_dir, pattern))):
        name = os.path.basename(p)
        native = decode_raw_native(p)
        s = chart_baseline.detect_and_sample(native)
        if s is None:
            continue
        out[name] = s
    return out


def _mean_de(xyz, ref):
    return float(np.mean(chart_baseline.patch_delta_e_xyz_d50(xyz, ref)))


def main():
    reference = chart_baseline.reference_patches_xyz_d50()
    weights = np.array([1.0 if i in NEUTRAL_IDX else CHROMA_WEIGHT for i in range(24)])
    kmichels = _load(os.path.join(KMICHELS_DIR, "raw"), "*.3FR")
    names = sorted(kmichels.keys())
    n = len(names)

    k = min(n, 5)
    rng = np.random.RandomState(0)
    folds = np.array_split(rng.permutation(n), k)
    cv_de = np.zeros(n)
    for test_idx in folds:
        train_idx = [i for i in range(n) if i not in set(test_idx.tolist())]
        tn = [names[i] for i in train_idx]
        m = raw_baseline.fit_color_matrix(
            [kmichels[nm] for nm in tn], [reference] * len(tn), weights=[weights] * len(tn))
        for i in test_idx:
            pred = raw_baseline.apply_color_matrix(kmichels[names[i]], m)
            cv_de[i] = _mean_de(pred, reference)

    final_matrix = raw_baseline.fit_color_matrix(
        [kmichels[nm] for nm in names], [reference] * n, weights=[weights] * n)
    in_sample = np.mean([
        _mean_de(raw_baseline.apply_color_matrix(kmichels[nm], final_matrix), reference)
        for nm in names])

    print(f"kmichels 단독 5-fold CV = {cv_de.mean():.4f}")
    print(f"kmichels 단독 in-sample(9장 전체 학습) = {in_sample:.4f}")
    print(f"(대조) dual-illuminant 보간 홀드아웃 = {DUAL_ILLUMINANT_HOLDOUT_DE:.4f}")
    print(f"(대조) global(dpreview단독학습) 홀드아웃 = {GLOBAL_DP_ONLY_HOLDOUT_DE:.4f}")
    gap = DUAL_ILLUMINANT_HOLDOUT_DE - cv_de.mean()
    print(f"\n격차: 자기 조명 전용 매트릭스가 있으면 {cv_de.mean():.2f}인데,")
    print(f"보간은 {DUAL_ILLUMINANT_HOLDOUT_DE:.2f} - {gap:.2f} 더 나쁨(전용 캘리브레이션 부재 비용)")


if __name__ == "__main__":
    main()
