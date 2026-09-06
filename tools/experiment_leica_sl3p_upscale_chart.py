"""
Leica SL3-P 스튜디오씬 챠트 실험: 패치 샘플링 전에 업스케일링을 걸면
ΔE00 크로스밸리데이션 floor(~12.73)가 줄어드는지 테스트.

배경: `tools/fit_leica_sl3p_studio_chart.py`가 쓰는
`chart_baseline.detect_and_sample()`은 검출용 프리뷰를 max_dim=2000으로
다운샘플한 뒤, 패치 값도 그 다운샘플된 배열에서 바로 평균낸다. 챠트가
프레임의 ~16%만 차지하는 dpreview 스튜디오씬(하셀블라드 전용 챠트샷
~75%와 대조)에서는 패치 하나가 다운샘플 후 수십 픽셀 폭밖에 안 돼서,
crop 경계를 정수로 반올림하는 과정에서 인접 패치/배경색이 섞여
들어갈("edge bleed") 여지가 상대적으로 크다. 이미 "네이티브 해상도로
직접 샘플링"은 시도해서 효과 없었음(2026-09-02 EVALUATION.md) - 이건
그것과 다른 축: 다운샘플된 프리뷰 자체를 업스케일링(cv2.INTER_CUBIC)해서
crop 경계를 서브픽셀 정밀도로 잡는 실험(2026-09-02, 사용자 지시
"차트를 화질 보정해" -> "업스케일링 ㄱㄱ").

  python3 -m tools.experiment_leica_sl3p_upscale_chart <DNG 폴더 경로>
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import colour

from hybrid_engine.core import chart_baseline, raw_baseline
from hybrid_engine.utils.io import decode_raw_native

CHROMA_WEIGHT = 3.0
_SRGB = colour.RGB_COLOURSPACES["sRGB"]


def detect_and_sample_upscaled(linear_rgb, max_dim=2000, shrink=0.5, upscale=3.0):
    """chart_baseline.detect_and_sample()과 동일한 검출 경로(다운샘플
    프리뷰에서 cv2.mcc 검출)를 쓰되, quad를 찾은 뒤 그 프리뷰 자체를
    upscale배로 cv2.INTER_CUBIC 업스케일링해서 crop 경계를 서브픽셀
    정밀도로 다시 잡고 그 업스케일된 배열에서 패치 평균을 낸다."""
    h, w = linear_rgb.shape[:2]
    scale = min(1.0, max_dim / max(h, w))
    small = cv2.resize(linear_rgb.astype(np.float32), (int(w * scale), int(h * scale)),
                        interpolation=cv2.INTER_AREA) if scale < 1.0 else linear_rgb.astype(np.float32)

    lo, hi = np.percentile(small, 0.5), np.percentile(small, 99.5)
    norm = np.clip((small - lo) / max(hi - lo, 1e-8), 0.0, 1.0)
    preview_srgb = colour.cctf_encoding(norm, function="sRGB")
    bgr_u8 = (preview_srgb * 255).astype(np.uint8)[:, :, ::-1].copy()

    quads = chart_baseline._detect_chart_bgr8(bgr_u8)
    if quads is None:
        return None

    big_h, big_w = int(small.shape[0] * upscale), int(small.shape[1] * upscale)
    small_big = cv2.resize(small, (big_w, big_h), interpolation=cv2.INTER_CUBIC)
    quads_big = quads * upscale

    samples = np.zeros((24, 3), dtype=np.float64)
    for i, quad in enumerate(quads_big):
        x0, y0 = quad.min(axis=0)
        x1, y1 = quad.max(axis=0)
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        hw, hh = (x1 - x0) / 2.0 * shrink, (y1 - y0) / 2.0 * shrink
        sx0 = int(np.clip(cx - hw, 0, big_w - 1))
        sx1 = int(np.clip(cx + hw, sx0 + 1, big_w))
        sy0 = int(np.clip(cy - hh, 0, big_h - 1))
        sy1 = int(np.clip(cy + hh, sy0 + 1, big_h))
        samples[i] = small_big[sy0:sy1, sx0:sx1].reshape(-1, 3).mean(axis=0)
    return samples


def _mean_de(samples_xyz, reference):
    return float(np.mean(chart_baseline.patch_delta_e_xyz_d50(samples_xyz, reference)))


def _kfold_cv(names, per_image, reference, weights, k=5, ridge=0.1):
    idx = np.arange(len(names))
    rng = np.random.RandomState(0)
    rng.shuffle(idx)
    folds = np.array_split(idx, k)
    fold_des = []
    for fi in range(k):
        test_idx = folds[fi]
        train_idx = np.concatenate([folds[j] for j in range(k) if j != fi])
        train_names = [names[i] for i in train_idx]
        test_names = [names[i] for i in test_idx]
        sources = [per_image[nm] for nm in train_names]
        targets = [reference for _ in train_names]
        train_weights = [weights for _ in train_names]
        m = raw_baseline.fit_color_matrix(sources, targets, weights=train_weights, ridge=ridge)
        des = [_mean_de(raw_baseline.apply_color_matrix(per_image[nm], m), reference) for nm in test_names]
        fold_des.extend(des)
    return float(np.mean(fold_des))


def main():
    data_dir = sys.argv[1]
    upscale = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
    reference = chart_baseline.reference_patches_xyz_d50()
    weights = np.array([1.0 if i in range(18, 24) else CHROMA_WEIGHT for i in range(24)])

    raw_paths = sorted(glob.glob(os.path.join(data_dir, "*.DNG")) +
                        glob.glob(os.path.join(data_dir, "*.dng")))

    per_image_baseline = {}
    per_image_upscaled = {}
    for rp in raw_paths:
        name = os.path.basename(rp)
        print(f"  디코드+검출 중: {name}", flush=True)
        native = decode_raw_native(rp)
        base = chart_baseline.detect_and_sample(native)
        up = detect_and_sample_upscaled(native, upscale=upscale)
        if base is None or up is None:
            print(f"    검출 실패, 제외: {name}")
            continue
        per_image_baseline[name] = base
        per_image_upscaled[name] = up

    names = sorted(per_image_baseline.keys())
    print(f"\n검출 성공 {len(names)}장")

    cv_baseline = _kfold_cv(names, per_image_baseline, reference, weights)
    cv_upscaled = _kfold_cv(names, per_image_upscaled, reference, weights)

    print(f"\n5-fold CV ΔE00 (다운샘플 프리뷰 직접 샘플링, 기존)      = {cv_baseline:.4f}")
    print(f"5-fold CV ΔE00 (업스케일 {upscale:.1f}x 후 샘플링)          = {cv_upscaled:.4f}")
    diff = cv_baseline - cv_upscaled
    print(f"차이 = {diff:+.4f} ({'개선' if diff > 0 else '악화 또는 무변화'})")


if __name__ == "__main__":
    main()
