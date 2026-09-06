"""
Huber IRLS(iteratively reweighted least squares) 강건회귀로 DCP 챠트
매트릭스를 더 낮출 수 있는지 확인 - `tools/evaluate_dcp_weighted_patches.py`가
찾은 "무채색 4x 덜어낸 최소자승"(LOO ΔE00 2.7179)이 사람이 손으로 고른
가중치인 데 비해, IRLS는 실제 잔차 크기로 패치별 가중치를 자동으로
정한다. 두 가지를 비교: (1) 균등가중에서 시작한 순수 IRLS, (2) 이미
채택된 무채색-4x 가중치에서 시작한 IRLS(수동 사전지식 + 자동 보정
결합). `raw_baseline.fit_color_matrix()`의 기존 `weights=` 인터페이스를
그대로 쓴다 - 새 피팅 로직 없음.

  python3 -m tools.evaluate_dcp_irls_weighted
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from hybrid_engine.core import chart_baseline, raw_baseline
from hybrid_engine.utils.io import decode_raw_native

SET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "datasets", "hasselblad", "contributed", "kmichels-x2dii-2026-07")
MAX_ITERS = 15
HUBER_K = 1.345  # 표준 Huber 상수(가우시안 하에서 95% 효율)


def _mean_de(samples_xyz, reference):
    return float(np.mean(chart_baseline.patch_delta_e_xyz_d50(samples_xyz, reference)))


def _irls_fit(sources, targets, init_weights, max_iters=MAX_ITERS):
    """patch별(24,) 가중치를 IRLS로 갱신하며 수렴할 때까지 반복. 각
    source/target은 (24,3) - 여러 이미지를 이어붙여 최소자승하되, 가중치는
    패치 인덱스 기준으로 전 이미지 공유(하나의 배포용 가중치 벡터가
    필요하므로)."""
    weights = init_weights.copy()
    for it in range(max_iters):
        train_weights = [weights for _ in sources]
        m = raw_baseline.fit_color_matrix(sources, targets, weights=train_weights)
        # 패치별 잔차(XYZ 유클리드 거리) - 이미지 전체 평균
        resid_per_patch = np.zeros(24)
        for s, t in zip(sources, targets):
            pred = raw_baseline.apply_color_matrix(s, m)
            resid_per_patch += np.linalg.norm(pred - t, axis=-1)
        resid_per_patch /= len(sources)

        mad = np.median(np.abs(resid_per_patch - np.median(resid_per_patch))) or 1e-9
        delta = HUBER_K * mad * 1.4826  # MAD -> 표준편차 근사 스케일
        new_weights = np.where(resid_per_patch <= delta, 1.0, delta / resid_per_patch)
        new_weights = new_weights * init_weights  # 초기 사전 가중치와 결합(곱셈)
        if np.max(np.abs(new_weights - weights)) < 1e-4:
            weights = new_weights
            # break 직전 weights와 m이 한 iteration 어긋났다 - 수렴한
            # weights로 m을 다시 피팅해 보고값과 배포 행렬이 짝을 이루게
            # 한다(refit_dcp_irls_final.py/refit_dcp_irls_cyan_init.py가
            # 이 두 값을 그대로 배포하므로 정확성 결함이었다).
            m = raw_baseline.fit_color_matrix(
                sources, targets, weights=[weights for _ in sources])
            break
        weights = new_weights
    return weights, m


def main():
    reference = chart_baseline.reference_patches_xyz_d50()
    raw_paths = sorted(glob.glob(os.path.join(SET_DIR, "raw", "*.3FR")))
    per_image = {}
    for raw_path in raw_paths:
        name = os.path.basename(raw_path)
        native = decode_raw_native(raw_path)
        samples = chart_baseline.detect_and_sample(native)
        if samples is None:
            continue
        per_image[name] = samples
    names = sorted(per_image.keys())
    n = len(names)
    print(f"검출 성공 {n}장", flush=True)

    chroma_weight = np.array([1.0 if i in range(18, 24) else 4.0 for i in range(24)])

    for label, init_w in [("균등에서 시작한 순수 IRLS", np.ones(24)),
                           ("무채색-4x에서 시작한 IRLS", chroma_weight)]:
        cv_per_image = {}
        final_weights_last_fold = None
        for held_out in names:
            train_names = [nm for nm in names if nm != held_out]
            train_sources = [per_image[nm] for nm in train_names]
            train_targets = [reference for _ in train_sources]
            fitted_weights, m = _irls_fit(train_sources, train_targets, init_w)
            corrected = raw_baseline.apply_color_matrix(per_image[held_out], m)
            cv_per_image[held_out] = _mean_de(corrected, reference)
            final_weights_last_fold = fitted_weights
        cv_mean = float(np.mean(list(cv_per_image.values())))
        print(f"{label}: LOO ΔE00 = {cv_mean:.4f}")
        print(f"  마지막 폴드 수렴 가중치: {np.round(final_weights_last_fold, 2).tolist()}")


if __name__ == "__main__":
    main()
