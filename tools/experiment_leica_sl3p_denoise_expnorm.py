"""
Leica SL3-P 스튜디오씬 챠트 실험 2: 노이즈 제거 / 노출 정규화가
5-fold CV ΔE00 floor(~12.73, `tools/fit_leica_sl3p_studio_chart.py`)를
줄이는지 테스트. 업스케일링(`tools/experiment_leica_sl3p_upscale_chart.py`)은
효과 없었음(-0.0004) - 이어서 남은 두 가설(2026-09-02, 사용자 지시
"디노이즈 먼저 테스트하고, 효과 없으면 노출 정규화도 이어서 테스트" ->
"ㄱ")을 순서대로 검증한다.

가설 A(디노이즈): 26장이 다양한 ISO(고감도 포함)로 촬영돼서, 센서
노이즈가 패치 평균값에 편향을 준다. cv2.fastNlMeansDenoisingColored는
8비트만 받으므로, 검출용 8비트 프리뷰를 만들기 *전에* 선형 float
데이터에 가우시안 블러를 걸어 노이즈를 줄인 뒤 같은 검출/샘플링
경로를 태운다.

가설 B(노출 정규화): 각 이미지마다 ISO가 달라 전체 밝기(게인)가
다른데, 매트릭스 피팅은 전 이미지에 공통 3x3 M 하나만 쓰므로 이미지별
게인 편차를 색상과 분리해서 흡수할 수 없다 - 매트릭스가 여러 이미지의
서로 다른 최적 게인을 타협한 값으로 수렴하면서 오차가 남을 수 있다.
각 이미지를 참조값에 대한 최소자승 스칼라 게인으로 노출 정규화한 뒤
매트릭스를 피팅해서 이 타협 오차가 줄어드는지 확인한다.

  python3 -m tools.experiment_leica_sl3p_denoise_expnorm <DNG 폴더 경로>
"""
import glob
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import colour

from hybrid_engine.core import chart_baseline, raw_baseline
from hybrid_engine.utils.io import decode_raw_native

CHROMA_WEIGHT = 3.0


def detect_and_sample_denoised(linear_rgb, max_dim=2000, shrink=0.5, blur_ksize=5):
    """chart_baseline.detect_and_sample()과 동일한 경로지만, 다운샘플
    직전에 선형 float 데이터에 가우시안 블러(ksize=blur_ksize)를 걸어
    고ISO 센서 노이즈를 줄인다."""
    h, w = linear_rgb.shape[:2]
    blurred = cv2.GaussianBlur(linear_rgb.astype(np.float32), (blur_ksize, blur_ksize), 0)
    scale = min(1.0, max_dim / max(h, w))
    small = cv2.resize(blurred, (int(w * scale), int(h * scale)),
                        interpolation=cv2.INTER_AREA) if scale < 1.0 else blurred

    lo, hi = np.percentile(small, 0.5), np.percentile(small, 99.5)
    norm = np.clip((small - lo) / max(hi - lo, 1e-8), 0.0, 1.0)
    preview_srgb = colour.cctf_encoding(norm, function="sRGB")
    bgr_u8 = (preview_srgb * 255).astype(np.uint8)[:, :, ::-1].copy()

    quads = chart_baseline._detect_chart_bgr8(bgr_u8)
    if quads is None:
        return None

    samples = np.zeros((24, 3), dtype=np.float64)
    img_h, img_w = small.shape[:2]
    for i, quad in enumerate(quads):
        x0, y0 = quad.min(axis=0)
        x1, y1 = quad.max(axis=0)
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        hw, hh = (x1 - x0) / 2.0 * shrink, (y1 - y0) / 2.0 * shrink
        sx0 = int(np.clip(cx - hw, 0, img_w - 1))
        sx1 = int(np.clip(cx + hw, sx0 + 1, img_w))
        sy0 = int(np.clip(cy - hh, 0, img_h - 1))
        sy1 = int(np.clip(cy + hh, sy0 + 1, img_h))
        samples[i] = small[sy0:sy1, sx0:sx1].reshape(-1, 3).mean(axis=0)
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


def _kfold_cv_per_image(names, per_image, reference, weights, k=5, ridge=0.1):
    """_kfold_cv()와 동일한 폴드 분할(같은 rng seed)이지만, 평균이 아니라
    {이미지명: out-of-fold ΔE00} 딕셔너리를 반환 - 다른 방법과 같은 이름
    기준으로 페어드 비교(summarize())를 하기 위함."""
    idx = np.arange(len(names))
    rng = np.random.RandomState(0)
    rng.shuffle(idx)
    folds = np.array_split(idx, k)
    per_name_de = {}
    for fi in range(k):
        test_idx = folds[fi]
        train_idx = np.concatenate([folds[j] for j in range(k) if j != fi])
        train_names = [names[i] for i in train_idx]
        test_names = [names[i] for i in test_idx]
        sources = [per_image[nm] for nm in train_names]
        targets = [reference for _ in train_names]
        train_weights = [weights for _ in train_names]
        m = raw_baseline.fit_color_matrix(sources, targets, weights=train_weights, ridge=ridge)
        for nm in test_names:
            per_name_de[nm] = _mean_de(raw_baseline.apply_color_matrix(per_image[nm], m), reference)
    return per_name_de


def _sign_test_p(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def summarize(label_a, des_a, label_b, des_b, n_bootstrap=20000, seed=0):
    """calibrate_profile_leica.py의 summarize()와 같은 통계(부트스트랩
    CI, 부호검정) - evaluate_*.py 컨벤션대로 복붙."""
    a = np.asarray(des_a, dtype=np.float64)
    b = np.asarray(des_b, dtype=np.float64)
    n = len(a)
    diff = a - b
    mean_a, mean_b = float(a.mean()), float(b.mean())
    improvement_pct = (mean_a - mean_b) / mean_a * 100.0 if mean_a else float("nan")
    wins = int((diff > 0).sum())
    losses = int((diff < 0).sum())

    rng = np.random.default_rng(seed)
    boot = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        bidx = rng.integers(0, n, n)
        boot[i] = diff[bidx].mean()
    ci_lo, ci_hi = (float(v) for v in np.percentile(boot, [2.5, 97.5]))
    p_value = _sign_test_p(wins, losses)
    inconclusive = ci_lo <= 0.0 <= ci_hi

    print(f"\n=== {label_a} vs {label_b} (n={n}) ===")
    print(f"평균 {label_a} ΔE00={mean_a:.3f}  평균 {label_b} ΔE00={mean_b:.3f}  "
          f"{label_b} 개선폭={improvement_pct:+.2f}%")
    print(f"승({label_b} 더 좋음)/패={wins}/{losses}  부호검정 p={p_value:.4f}")
    print(f"부트스트랩 95% CI(평균차)=[{ci_lo:+.3f}, {ci_hi:+.3f}]")
    if inconclusive:
        print("판정: 보류 (CI가 0 포함)")
    elif improvement_pct > 0:
        print(f"판정: {label_b} 우세")
    else:
        print(f"판정: {label_a} 우세")
    return dict(mean_a=mean_a, mean_b=mean_b, improvement_pct=improvement_pct,
                wins=wins, losses=losses, p_value=p_value, ci=(ci_lo, ci_hi),
                inconclusive=inconclusive)


def _exposure_normalize(samples, reference):
    """samples(24,3) 전체를 reference(24,3)에 최소자승 스칼라 게인으로
    맞춘다: gain = sum(samples*reference) / sum(samples*samples).
    색상은 안 건드리고 전체 밝기(게인)만 이미지별로 참조값 스케일에
    정렬해서, 이후 매트릭스 피팅이 이미지 간 게인 편차를 색상 변환과
    같이 타협하지 않도록 한다."""
    gain = np.sum(samples * reference) / max(np.sum(samples * samples), 1e-12)
    return samples * gain


def main():
    data_dir = sys.argv[1]
    reference = chart_baseline.reference_patches_xyz_d50()
    weights = np.array([1.0 if i in range(18, 24) else CHROMA_WEIGHT for i in range(24)])

    raw_paths = sorted(glob.glob(os.path.join(data_dir, "*.DNG")) +
                        glob.glob(os.path.join(data_dir, "*.dng")))

    per_image_baseline = {}
    per_image_denoised = {}
    for rp in raw_paths:
        name = os.path.basename(rp)
        print(f"  디코드+검출 중: {name}", flush=True)
        native = decode_raw_native(rp)
        base = chart_baseline.detect_and_sample(native)
        dn = detect_and_sample_denoised(native)
        if base is None or dn is None:
            print(f"    검출 실패, 제외: {name}")
            continue
        per_image_baseline[name] = base
        per_image_denoised[name] = dn

    names = sorted(per_image_baseline.keys())
    print(f"\n검출 성공 {len(names)}장")

    cv_baseline = _kfold_cv(names, per_image_baseline, reference, weights)
    cv_denoised = _kfold_cv(names, per_image_denoised, reference, weights)

    per_image_expnorm = {nm: _exposure_normalize(per_image_baseline[nm], reference) for nm in names}
    cv_expnorm = _kfold_cv(names, per_image_expnorm, reference, weights)

    print(f"\n5-fold CV ΔE00 (기존, 다운샘플 직접 샘플링)   = {cv_baseline:.4f}")
    print(f"5-fold CV ΔE00 (가우시안 블러 디노이즈)         = {cv_denoised:.4f}  (차이 {cv_baseline - cv_denoised:+.4f})")
    print(f"5-fold CV ΔE00 (이미지별 노출 정규화)           = {cv_expnorm:.4f}  (차이 {cv_baseline - cv_expnorm:+.4f})")

    per_name_base = _kfold_cv_per_image(names, per_image_baseline, reference, weights)
    per_name_expnorm = _kfold_cv_per_image(names, per_image_expnorm, reference, weights)
    des_base = [per_name_base[nm] for nm in names]
    des_expnorm = [per_name_expnorm[nm] for nm in names]
    summarize("기존", des_base, "노출정규화", des_expnorm)


if __name__ == "__main__":
    main()
