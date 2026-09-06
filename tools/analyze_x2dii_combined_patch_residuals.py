"""kmichels+dpreview 25장 합친 X2D II 100C 챠트 데이터의 5-fold CV
패치별 잔차를 뜯어본다 - "이부분의 2.83 더 줄여봐"(사용자, 원래는
후속 실측 21의 kmichels 단독 n=9 LOO 2.83을 가리킨 요청이지만, 그
수치는 이미 이 문서에서 가중치/IRLS/cyan-init 세 단계로 2.4651까지
줄었고 전부 같은 조명 1개 데이터 안에서의 개선이었다 - 지금 배포된
매트릭스는 그 뒤 다른 조명 데이터를 합친 combined 버전(CV 12.69)이라
같은 "더 줄여봐" 요청을 여기 적용하려면 combined 데이터에서 같은
방법론(패치별 잔차 뜯어보기 -> 구조적 이상치가 있으면 타겟 재조정)이
먹히는지부터 확인해야 한다).

tools/refit_x2dii_chart_combined.py와 같은 fold 분할(seed=0, k=5)로
5-fold CV를 돌리고, 폴드별 예측 잔차를 패치 인덱스별로 모아
평균/표준편차를 낸다. cyan 사례처럼 "평균 크고 표준편차는 작다"(=
특정 이미지 노이즈가 아니라 25장 전부에서 구조적으로 반복)인 패치가
있는지가 판단 기준.

  python3 -m tools.analyze_x2dii_combined_patch_residuals
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


def main():
    reference = chart_baseline.reference_patches_xyz_d50()
    weights = np.array([1.0 if i in NEUTRAL_PATCH_INDICES else CHROMA_WEIGHT
                         for i in range(24)])

    print("kmichels 디코드+검출:")
    kmichels = _load_samples(os.path.join(KMICHELS_DIR, "raw"), "*.3FR")
    print(f"  {len(kmichels)}장")
    print("dpreview 디코드+검출:")
    dpreview = _load_samples(os.path.join(DPREVIEW_DIR, "raw"), "*.3fr")
    print(f"  {len(dpreview)}장")

    combined = {**kmichels, **dpreview}
    names = sorted(combined.keys())
    n = len(names)
    print(f"\n합계 {n}장")

    k = min(n, 5)
    rng = np.random.RandomState(0)
    folds = np.array_split(rng.permutation(n), k)

    per_patch_de = np.zeros((n, 24))
    for test_idx in folds:
        train_idx = [i for i in range(n) if i not in set(test_idx.tolist())]
        train_names = [names[i] for i in train_idx]
        m = raw_baseline.fit_color_matrix(
            [combined[nm] for nm in train_names],
            [reference] * len(train_names),
            weights=[weights for _ in train_names])
        for i in test_idx:
            pred = raw_baseline.apply_color_matrix(combined[names[i]], m)
            per_patch_de[i] = chart_baseline.patch_delta_e_xyz_d50(pred, reference)

    patch_mean = per_patch_de.mean(axis=0)
    patch_std = per_patch_de.std(axis=0)
    order = np.argsort(-patch_mean)

    print(f"\n{'patch':<28}{'mean ΔE00':>10}{'std':>8}{'std/mean':>10}")
    for i in order:
        ratio = patch_std[i] / patch_mean[i] if patch_mean[i] > 0 else float("nan")
        print(f"{chart_baseline.PATCH_NAMES[i]:<28}{patch_mean[i]:>10.3f}"
              f"{patch_std[i]:>8.3f}{ratio:>10.3f}")

    print(f"\n전체 25장 CV 평균 ΔE00 (이미지 평균의 평균) = "
          f"{per_patch_de.mean(axis=1).mean():.4f}")

    out = {
        "n_images": n,
        "fold_seed": 0,
        "k": k,
        "patch_names": chart_baseline.PATCH_NAMES,
        "patch_mean_de00": patch_mean.tolist(),
        "patch_std_de00": patch_std.tolist(),
        "cv_mean_de00": float(per_patch_de.mean(axis=1).mean()),
    }
    out_path = os.path.join(DPREVIEW_DIR, "combined_patch_residuals.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\n저장: {out_path}")


if __name__ == "__main__":
    main()
