"""
[v1.1] hybrid_engine profile을 실제 raw+jpeg 페어로 캘리브레이션.

V0.1의 `assets/profiles/hasselblad.json`은 "미검증 seed"였다 - 이 스크립트는
`raw_calib_cache/`에 이미 캐시된 핫셀블라드 raw+jpeg 페어(원래 HNCS 프로젝트의
`tools/calibrate.py`가 쓰던 것과 동일한 소스)로 `utils/evaluate.py`의
CIEDE2000 ΔE 루프를 실제로 돌려서 파라미터를 좌표하강으로 탐색한다.

계산량 때문에 원본 해상도(최대 1억화소급) 그대로 쓰지 않고, 캘리브레이션
단계에서만 작은 해상도로 리사이즈해서 페어당 1회 디코드 후 메모리에
캐시 - 파라미터 후보마다 다시 디코드하지 않는다(디코드가 병목이라).

  python3 -m hybrid_engine.calibrate_profile
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from hybrid_engine.core import color_matrix
from hybrid_engine.pipeline.engine import HybridCameraEngine, _DEFAULT_PARAMS
from hybrid_engine.utils.io import decode_raw, load_image_linear
from hybrid_engine.utils.evaluate import mean_delta_e

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "raw_calib_cache")
CALIB_MAX_DIM = 500  # 캘리브레이션 전용 축소 해상도 - 최종 profile은 해상도 무관


def _find_pairs():
    raw_paths = sorted(glob.glob(os.path.join(CACHE_DIR, "*.3FR")) +
                        glob.glob(os.path.join(CACHE_DIR, "*.fff")))
    pairs = []
    for raw_path in raw_paths:
        base = raw_path.rsplit(".", 1)[0]  # "....jpg.3FR" -> "....jpg"
        target_path = base + ".target.jpg"
        if os.path.exists(target_path):
            pairs.append((raw_path, target_path))
    return pairs


def _resize_max_dim(img, max_dim):
    h, w = img.shape[:2]
    scale = max_dim / max(h, w)
    if scale >= 1:
        return img
    return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def _load_calib_set():
    """(작은 linear RGB, camera_whitebalance, 작은 타깃 linear RGB) 튜플 리스트.

    target은 load_image_linear(..., resize_to=...)로 원본 해상도 그대로
    float64 변환하기 전에 먼저 축소한다 - 100MP대 타깃 JPEG(X2D II 등)을
    원본 그대로 cctf_decoding했다가 버리면 그 순간 OOM(실측 확인)."""
    dataset = []
    for raw_path, target_path in _find_pairs():
        print(f"  로드 중: {os.path.basename(raw_path)}")
        linear = decode_raw(raw_path)
        linear_small = _resize_max_dim(linear, CALIB_MAX_DIM)
        camera_wb = color_matrix.extract_camera_metadata(raw_path)["camera_whitebalance"]
        target_small = load_image_linear(target_path, resize_to=linear_small.shape[:2])
        dataset.append((linear_small, camera_wb, target_small))
    return dataset


def _mean_loss(params, dataset):
    engine = HybridCameraEngine(profile=params)
    losses = []
    for linear_small, camera_wb, target_small in dataset:
        result = engine.process(linear_small, camera_whitebalance=camera_wb)
        losses.append(mean_delta_e(result, target_small))
    return float(np.mean(losses))


# 좌표하강 대상 파라미터 + 탐색 후보값. shadow_threshold/target_gray/
# correct_color_cast/use_color_unification/use_spatial은 V0.1 기본값 유지
# (표본 13장으로 8차원을 전부 캘리브레이션하면 과적합 위험이 커서, 실제로
# 브랜드 룩을 좌우하는 5개만 탐색 - 이 프로젝트의 기존 "표본 작으면 과적합보다
# 보수적 선택" 원칙과 동일).
_SEARCH_SPACE = {
    "contrast_n": [0.95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.3],
    "highlight_rolloff_start": [0.7, 0.75, 0.8, 0.82, 0.85, 0.9],
    "shadow_lift": [0.0, 0.01, 0.02, 0.03, 0.05],
    # sat_gain/max_chroma는 raw_baseline_matrix 재캘리브레이션(2026-07)이
    # 원래 경계값(0.2/90.0)에 계속 붙어서 양쪽으로 넓힘 - 진짜 최적값이
    # 탐색 범위 밖에 있었을 가능성을 배제하기 위함.
    "sat_gain": [0.0, 0.04, 0.08, 0.12, 0.15, 0.2, 0.25, 0.3],
    "max_chroma": [70.0, 80.0, 90.0, 100.0, 110.0, 120.0, 140.0],
}


def coordinate_descent(dataset, n_passes=2, base_params=None):
    """base_params를 주면 그 값을 시작점으로 5개 파라미터(_SEARCH_SPACE)만
    좌표하강 - 그 외 키(raw_baseline_matrix 등)는 그대로 유지된다. 생략
    시 V0.1 기본값(_DEFAULT_PARAMS)에서 시작(기존 동작)."""
    params = dict(base_params) if base_params is not None else dict(_DEFAULT_PARAMS)
    best_loss = _mean_loss(params, dataset)
    print(f"시작 ΔE ({'주어진 base_params' if base_params is not None else 'V0.1 기본값'}): {best_loss:.3f}")

    for p in range(n_passes):
        print(f"\n=== pass {p + 1}/{n_passes} ===")
        for key, candidates in _SEARCH_SPACE.items():
            best_val = params[key]
            for val in candidates:
                trial = dict(params)
                trial[key] = val
                loss = _mean_loss(trial, dataset)
                if loss < best_loss:
                    best_loss = loss
                    best_val = val
            params[key] = best_val
            print(f"  {key:26s} -> {best_val}  (ΔE={best_loss:.3f})")

    return params, best_loss


_LEARNED_LUT_BINS = 256
_LEARNED_LUT_FILENAME = "hasselblad_tone_learned.npy"


def learn_tone_lut(dataset, profile, n_bins=_LEARNED_LUT_BINS):
    """(정규화된 중립 L, 타깃 L) 픽셀 대응에서 1D 톤 LUT을 직접 학습.
    apply_hncs_learned와 같은 원리(bin별 타깃 평균) - 커브 모양(S자/toe/
    shoulder)을 가정하지 않는다. 반환: [0, 1] 균등 도메인에 대한 출력값
    배열 (엔진의 learned_tone_lut 포맷)."""
    from hybrid_engine.utils.evaluate import _linear_rgb_to_lab

    engine = HybridCameraEngine(profile=profile)
    sums = np.zeros(n_bins)
    counts = np.zeros(n_bins)
    for linear_small, camera_wb, target_small in dataset:
        neutral_L = engine.to_normalized_lab(linear_small, camera_whitebalance=camera_wb)[0]
        target_L = _linear_rgb_to_lab(target_small)[..., 0]
        x = np.clip(neutral_L.ravel() / 100.0, 0.0, 1.0)
        y = np.clip(target_L.ravel() / 100.0, 0.0, 1.0)
        bins = np.minimum((x * n_bins).astype(int), n_bins - 1)
        np.add.at(sums, bins, y)
        np.add.at(counts, bins, 1)

    lut = np.zeros(n_bins)
    filled = counts > 0
    lut[filled] = sums[filled] / counts[filled]
    # 표본이 없는 bin은 채워진 bin에서 선형보간 (도메인 양끝은 0/1로 고정)
    domain = np.linspace(0.0, 1.0, n_bins)
    if not filled.all():
        lut = np.interp(domain, np.concatenate(([0.0], domain[filled], [1.0])),
                         np.concatenate(([0.0], lut[filled], [1.0])))
    return np.clip(lut, 0.0, 1.0)


_LEARNED_HUE_LUT_BINS = 36  # 10도 간격 - 표본 13장으로 tone(256bin)만큼 세분화하면 과적합
_LEARNED_HUE_LUT_FILENAME = "hasselblad_hue_learned.npy"


def learn_hue_lut(dataset, profile, n_bins=_LEARNED_HUE_LUT_BINS):
    """(엔진의 tone+color 적용 후 a/b, 타깃 a/b) 픽셀 대응에서 순환(circular)
    1D hue LUT을 직접 학습. 입력 hue를 n_bins개 구간으로 나누고, 구간별로
    "타깃 hue가 입력 hue에서 얼마나(도, circular) 벗어났는지"를 chroma
    가중 순환평균으로 구한다. 반환: bin별 hue 보정량(도) 배열
    (엔진의 learned_hue_lut 포맷, hue_core.apply_hue_lut이 소비)."""
    from hybrid_engine.utils.evaluate import _linear_rgb_to_lab

    engine = HybridCameraEngine(profile=profile)
    bin_width = 360.0 / n_bins
    sum_re = np.zeros(n_bins)
    sum_im = np.zeros(n_bins)
    weight_sum = np.zeros(n_bins)

    for linear_small, camera_wb, target_small in dataset:
        _, a2, b2 = engine.to_pre_hue_lab(linear_small, camera_whitebalance=camera_wb)
        target_lab = _linear_rgb_to_lab(target_small)
        target_a, target_b = target_lab[..., 1], target_lab[..., 2]

        source_hue = np.degrees(np.arctan2(b2, a2)) % 360.0
        target_hue = np.degrees(np.arctan2(target_b, target_a)) % 360.0
        delta = (target_hue - source_hue + 180.0) % 360.0 - 180.0

        chroma_source = np.hypot(a2, b2)
        chroma_target = np.hypot(target_a, target_b)
        weight = np.clip((chroma_source + chroma_target) / 2.0, 0.0, None)

        bins = np.minimum((source_hue.ravel() / bin_width).astype(int), n_bins - 1)
        w = weight.ravel()
        delta_rad = np.radians(delta.ravel())
        np.add.at(sum_re, bins, w * np.cos(delta_rad))
        np.add.at(sum_im, bins, w * np.sin(delta_rad))
        np.add.at(weight_sum, bins, w)

    lut = np.zeros(n_bins)
    filled = weight_sum > 1e-6
    # 순환평균: 가중 delta를 단위원 위 벡터 합으로 누적한 뒤 각도만 추출
    # (일반 산술평균은 -179도/+179도가 섞이면 0도로 잘못 수렴하는 wraparound
    # 문제가 있어서 못 씀)
    lut[filled] = np.degrees(np.arctan2(sum_im[filled], sum_re[filled]))

    if filled.any() and not filled.all():
        centers = (np.arange(n_bins) + 0.5) * bin_width
        src_centers = centers[filled]
        src_vals = lut[filled]
        domain = np.concatenate([src_centers - 360.0, src_centers, src_centers + 360.0])
        values = np.tile(src_vals, 3)
        order = np.argsort(domain)
        lut = np.interp(centers, domain[order], values[order])
    # filled가 전부 False면(표본이 아예 없으면) 무보정(전부 0)으로 남긴다 -
    # 안 겪어본 hue를 추측해서 왜곡시키지 않기 위함
    return lut


def run_hue_mode(dataset):
    """학습 hue LUT 모드: 캘리브레이션된 파라메트릭 profile을 베이스로 hue
    보정 단계를 추가하고 in-sample ΔE와 leave-one-out 교차검증 ΔE를 둘 다
    낸다(lab2d/lab3d와 같은 이유 - in-sample만으로는 과적합을 못 잡는다는
    게 3D LUT 실험에서 실측으로 확인됨). 채택 여부는 교차검증 기준이어야
    한다는 게 이 함수를 부르는 쪽(main)의 책임."""
    import json
    profile_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", "profiles", "hasselblad.json")
    with open(profile_path, encoding="utf-8") as f:
        profile = json.load(f)
    profile.pop("_comment", None)
    profile.pop("learned_hue_lut", None)  # 학습 도메인은 항상 hue 보정 전 단계 기준

    baseline_loss = _mean_loss(profile, dataset)
    print(f"hue 보정 전 ΔE (기준선): {baseline_loss:.3f}")

    lut = learn_hue_lut(dataset, profile)
    lut_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", "luts", _LEARNED_HUE_LUT_FILENAME)
    np.save(lut_path, lut)

    hue_profile = dict(profile, learned_hue_lut=_LEARNED_HUE_LUT_FILENAME)
    in_sample_loss = _mean_loss(hue_profile, dataset)
    in_sample_improvement = (baseline_loss - in_sample_loss) / baseline_loss * 100
    print(f"hue 보정 후 ΔE (in-sample): {in_sample_loss:.3f} ({in_sample_improvement:+.1f}%)")

    loo_loss = None
    if len(dataset) > 1:
        loo_losses = []
        for i in range(len(dataset)):
            train_set = dataset[:i] + dataset[i + 1:]
            held_out = [dataset[i]]
            fold_lut = learn_hue_lut(train_set, profile)
            fold_path = lut_path + f".fold{i}.npy"
            np.save(fold_path, fold_lut)
            try:
                fold_profile = dict(profile, learned_hue_lut=fold_path)
                loo_losses.append(_mean_loss(fold_profile, held_out))
            finally:
                os.remove(fold_path)
        loo_loss = float(np.mean(loo_losses))
        loo_improvement = (baseline_loss - loo_loss) / baseline_loss * 100
        print(f"hue 보정 후 ΔE (leave-one-out 교차검증, {len(dataset)}-fold): "
              f"{loo_loss:.3f} ({loo_improvement:+.1f}%)")

    return baseline_loss, in_sample_loss, loo_loss, lut_path


_LEARNED_HUE_CHROMA_LUT_BINS = 36  # hue LUT과 동일한 세분화 - 표본 13장 기준 과적합 균형점
_LEARNED_HUE_CHROMA_LUT_FILENAME = "hasselblad_hue_chroma_learned.npy"


def learn_hue_chroma_lut(dataset, profile, n_bins=_LEARNED_HUE_CHROMA_LUT_BINS):
    """(엔진의 tone+color 적용 후 a/b, 타깃 a/b) 픽셀 대응에서 순환 1D
    hue-chroma LUT을 학습한다 - learn_hue_lut의 자매 함수, hue 회전 대신
    chroma(채도) 배율을 구한다는 것만 다르다. EVALUATION.md 후속 실측
    10에서 확인된 "옐로우오렌지(피부톤) hue 대역만 유독 실측보다 채도가
    낮다"는 국소 문제를 겨냥.

    bin별 배율은 픽셀별 비율(target/source)의 평균이 아니라 **에너지
    비율**로 추정한다 - sum(target chroma) / sum(source chroma). 픽셀별
    비율은 source chroma가 0에 가까우면 발산하는데, 에너지 비율은
    그 픽셀들이 분자/분모 양쪽에서 자연히 거의 기여하지 않게 만들어서
    안정적이다. 반환: bin별 chroma 배율(1.0=무보정) 배열
    (엔진의 learned_hue_chroma_lut 포맷, hue_core.apply_hue_chroma_lut이
    소비)."""
    from hybrid_engine.utils.evaluate import _linear_rgb_to_lab

    engine = HybridCameraEngine(profile=profile)
    bin_width = 360.0 / n_bins
    sum_source = np.zeros(n_bins)
    sum_target = np.zeros(n_bins)

    for linear_small, camera_wb, target_small in dataset:
        _, a2, b2 = engine.to_pre_hue_lab(linear_small, camera_whitebalance=camera_wb)
        target_lab = _linear_rgb_to_lab(target_small)
        target_a, target_b = target_lab[..., 1], target_lab[..., 2]

        source_hue = np.degrees(np.arctan2(b2, a2)) % 360.0
        chroma_source = np.hypot(a2, b2)
        chroma_target = np.hypot(target_a, target_b)

        bins = np.minimum((source_hue.ravel() / bin_width).astype(int), n_bins - 1)
        np.add.at(sum_source, bins, chroma_source.ravel())
        np.add.at(sum_target, bins, chroma_target.ravel())

    lut = np.ones(n_bins)
    filled = sum_source > 1e-6
    lut[filled] = sum_target[filled] / sum_source[filled]

    if filled.any() and not filled.all():
        centers = (np.arange(n_bins) + 0.5) * bin_width
        src_centers = centers[filled]
        src_vals = lut[filled]
        domain = np.concatenate([src_centers - 360.0, src_centers, src_centers + 360.0])
        values = np.tile(src_vals, 3)
        order = np.argsort(domain)
        lut = np.interp(centers, domain[order], values[order])
    # filled가 전부 False면(표본이 아예 없으면) 무보정(전부 1.0)으로 남긴다
    return lut


def run_hue_chroma_mode(dataset):
    """학습 hue-chroma LUT 모드: run_hue_mode와 같은 구조로 in-sample ΔE와
    leave-one-out 교차검증 ΔE를 둘 다 낸다. 채택 여부는 교차검증 기준."""
    import json
    profile_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", "profiles", "hasselblad.json")
    with open(profile_path, encoding="utf-8") as f:
        profile = json.load(f)
    profile.pop("_comment", None)
    profile.pop("learned_hue_chroma_lut", None)

    baseline_loss = _mean_loss(profile, dataset)
    print(f"hue-chroma 보정 전 ΔE (기준선): {baseline_loss:.3f}")

    lut = learn_hue_chroma_lut(dataset, profile)
    lut_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", "luts",
        _LEARNED_HUE_CHROMA_LUT_FILENAME)
    np.save(lut_path, lut)

    chroma_profile = dict(profile, learned_hue_chroma_lut=_LEARNED_HUE_CHROMA_LUT_FILENAME)
    in_sample_loss = _mean_loss(chroma_profile, dataset)
    in_sample_improvement = (baseline_loss - in_sample_loss) / baseline_loss * 100
    print(f"hue-chroma 보정 후 ΔE (in-sample): {in_sample_loss:.3f} ({in_sample_improvement:+.1f}%)")

    loo_loss = None
    if len(dataset) > 1:
        loo_losses = []
        for i in range(len(dataset)):
            train_set = dataset[:i] + dataset[i + 1:]
            held_out = [dataset[i]]
            fold_lut = learn_hue_chroma_lut(train_set, profile)
            fold_path = lut_path + f".fold{i}.npy"
            np.save(fold_path, fold_lut)
            try:
                fold_profile = dict(profile, learned_hue_chroma_lut=fold_path)
                loo_losses.append(_mean_loss(fold_profile, held_out))
            finally:
                os.remove(fold_path)
        loo_loss = float(np.mean(loo_losses))
        loo_improvement = (baseline_loss - loo_loss) / baseline_loss * 100
        print(f"hue-chroma 보정 후 ΔE (leave-one-out 교차검증, {len(dataset)}-fold): "
              f"{loo_loss:.3f} ({loo_improvement:+.1f}%)")

    return baseline_loss, in_sample_loss, loo_loss, lut_path


_LAB2D_GRID_SIZE = 9  # 9^2=81 격자점 - 3D(729)보다 훨씬 적어서 과적합 위험이 낮음.
                       # 그래도 run_lab2d_mode가 leave-one-out으로 확인(3D에서 in-sample만
                       # 보면 오판한다는 게 이미 실측으로 확인됐어서).
_LEARNED_LAB2D_LUT_FILENAME = "hasselblad_lab2d_learned.npz"


def learn_lab2d_lut(dataset, profile, grid_size=_LAB2D_GRID_SIZE):
    """(엔진의 tone+color+hue 적용 후 a/b, 타깃 a/b) 픽셀 대응에서 2D
    잔차 LUT을 직접 학습. L은 학습 입력에서 제외(3D와 달리 a/b 두 축만
    결합) - 격자별 타깃 평균, 표본이 없는 cell은 항등(무보정)으로 남긴다
    (learn_lab3d_lut과 같은 원리). 반환: (table (grid_size,grid_size,2),
    domain ([[amin,bmin],[amax,bmax]]))."""
    from hybrid_engine.utils.evaluate import _linear_rgb_to_lab

    engine = HybridCameraEngine(profile=profile)
    sources, targets = [], []
    for linear_small, camera_wb, target_small in dataset:
        _, a2, b2 = engine.to_pre_hue_lab(linear_small, camera_whitebalance=camera_wb)
        target_lab = _linear_rgb_to_lab(target_small)
        sources.append(np.stack([a2, b2], axis=-1).reshape(-1, 2))
        targets.append(target_lab[..., 1:3].reshape(-1, 2))
    source = np.concatenate(sources, axis=0)
    target = np.concatenate(targets, axis=0)

    lo = source.min(axis=0)
    hi = source.max(axis=0)
    domain = np.stack([lo, hi], axis=0)
    span = np.clip(hi - lo, 1e-6, None)

    idx = np.clip(np.round((source - lo) / span * (grid_size - 1)).astype(int),
                  0, grid_size - 1)
    flat_idx = idx[:, 0] * grid_size + idx[:, 1]

    n_cells = grid_size ** 2
    sums = np.zeros((n_cells, 2))
    counts = np.zeros(n_cells)
    np.add.at(sums, flat_idx, target)
    np.add.at(counts, flat_idx, 1)

    coords = np.stack(np.meshgrid(
        np.linspace(lo[0], hi[0], grid_size),
        np.linspace(lo[1], hi[1], grid_size),
        indexing="ij"), axis=-1)
    table = coords.reshape(n_cells, 2).copy()

    filled = counts > 0
    table[filled] = sums[filled] / counts[filled, None]
    table = table.reshape(grid_size, grid_size, 2)
    return table, domain


def run_lab2d_mode(dataset, grid_size=_LAB2D_GRID_SIZE):
    """2D 잔차 LUT 모드: in-sample ΔE와 leave-one-out 교차검증 ΔE를 둘 다
    낸다(run_lab3d_mode와 같은 이유 - in-sample만으로는 과적합을 못 잡는다는
    게 3D 실험에서 실측으로 확인됨)."""
    import json
    profile_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", "profiles", "hasselblad.json")
    with open(profile_path, encoding="utf-8") as f:
        profile = json.load(f)
    profile.pop("_comment", None)
    profile.pop("learned_lab2d_lut", None)

    baseline_loss = _mean_loss(profile, dataset)
    print(f"2D LUT 보정 전 ΔE (기준선): {baseline_loss:.3f}")

    table, domain = learn_lab2d_lut(dataset, profile, grid_size=grid_size)
    lut_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", "luts", _LEARNED_LAB2D_LUT_FILENAME)
    np.savez(lut_path, table=table, domain=domain)

    lab2d_profile = dict(profile, learned_lab2d_lut=_LEARNED_LAB2D_LUT_FILENAME)
    in_sample_loss = _mean_loss(lab2d_profile, dataset)
    in_sample_improvement = (baseline_loss - in_sample_loss) / baseline_loss * 100
    print(f"2D LUT 보정 후 ΔE (in-sample): {in_sample_loss:.3f} "
          f"({in_sample_improvement:+.1f}%)")

    loo_loss = None
    if len(dataset) > 1:
        loo_losses = []
        for i in range(len(dataset)):
            train_set = dataset[:i] + dataset[i + 1:]
            held_out = [dataset[i]]
            table_i, domain_i = learn_lab2d_lut(train_set, profile, grid_size=grid_size)
            fold_path = lut_path + f".fold{i}.npz"
            np.savez(fold_path, table=table_i, domain=domain_i)
            try:
                fold_profile = dict(profile, learned_lab2d_lut=fold_path)
                loo_losses.append(_mean_loss(fold_profile, held_out))
            finally:
                os.remove(fold_path)
        loo_loss = float(np.mean(loo_losses))
        loo_improvement = (baseline_loss - loo_loss) / baseline_loss * 100
        print(f"2D LUT 보정 후 ΔE (leave-one-out 교차검증, {len(dataset)}-fold): "
              f"{loo_loss:.3f} ({loo_improvement:+.1f}%)")

    return baseline_loss, in_sample_loss, loo_loss, lut_path


_LAB3D_GRID_SIZE = 9  # 9^3=729 격자점 - 표본 13장(수백만 픽셀)이어도 L/a/b 결합 공간은
                       # 넓어서 과적합 위험이 큼. run_lab3d_mode가 leave-one-out으로 확인.
_LEARNED_LAB3D_LUT_FILENAME = "hasselblad_lab3d_learned.npz"


def learn_lab3d_lut(dataset, profile, grid_size=_LAB3D_GRID_SIZE):
    """(엔진의 tone+color+hue 적용 후 L/a/b, 타깃 L/a/b) 픽셀 대응에서
    3D 잔차 LUT을 직접 학습. 톤/hue LUT과 달리 세 축을 "조합"으로 보고
    격자(cell)별 타깃 평균을 구한다 - 표본이 없는 cell은 그 격자점 자체
    좌표(항등, 즉 무보정)로 남긴다(외삽으로 잘못된 보정을 추측하지 않기
    위함). 반환: (table (grid_size,grid_size,grid_size,3), domain
    ([[Lmin,amin,bmin],[Lmax,amax,bmax]]))."""
    from hybrid_engine.utils.evaluate import _linear_rgb_to_lab

    engine = HybridCameraEngine(profile=profile)
    sources, targets = [], []
    for linear_small, camera_wb, target_small in dataset:
        L2, a2, b2 = engine.to_pre_hue_lab(linear_small, camera_whitebalance=camera_wb)
        target_lab = _linear_rgb_to_lab(target_small)
        sources.append(np.stack([L2, a2, b2], axis=-1).reshape(-1, 3))
        targets.append(target_lab.reshape(-1, 3))
    source = np.concatenate(sources, axis=0)
    target = np.concatenate(targets, axis=0)

    lo = source.min(axis=0)
    hi = source.max(axis=0)
    domain = np.stack([lo, hi], axis=0)
    span = np.clip(hi - lo, 1e-6, None)

    idx = np.clip(np.round((source - lo) / span * (grid_size - 1)).astype(int),
                  0, grid_size - 1)
    flat_idx = (idx[:, 0] * grid_size + idx[:, 1]) * grid_size + idx[:, 2]

    n_cells = grid_size ** 3
    sums = np.zeros((n_cells, 3))
    counts = np.zeros(n_cells)
    np.add.at(sums, flat_idx, target)
    np.add.at(counts, flat_idx, 1)

    coords = np.stack(np.meshgrid(
        np.linspace(lo[0], hi[0], grid_size),
        np.linspace(lo[1], hi[1], grid_size),
        np.linspace(lo[2], hi[2], grid_size),
        indexing="ij"), axis=-1)
    table = coords.reshape(n_cells, 3).copy()

    filled = counts > 0
    table[filled] = sums[filled] / counts[filled, None]
    table = table.reshape(grid_size, grid_size, grid_size, 3)
    return table, domain


def run_lab3d_mode(dataset, grid_size=_LAB3D_GRID_SIZE):
    """3D 잔차 LUT 모드: in-sample ΔE(참고용, 과적합 위험 큼 - 729개
    격자점을 13장에서 학습하니 톤/hue LUT보다도 과적합 위험이 훨씬 큼)와
    leave-one-out 교차검증 ΔE(13-fold, 매번 12장으로 학습해서 나머지
    1장에서 평가)를 둘 다 낸다. 실제 채택 여부 판단은 교차검증 수치
    기준이어야 한다는 게 이 함수를 부르는 쪽(main)의 책임."""
    import json
    profile_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", "profiles", "hasselblad.json")
    with open(profile_path, encoding="utf-8") as f:
        profile = json.load(f)
    profile.pop("_comment", None)
    profile.pop("learned_lab3d_lut", None)

    baseline_loss = _mean_loss(profile, dataset)
    print(f"3D LUT 보정 전 ΔE (기준선): {baseline_loss:.3f}")

    table, domain = learn_lab3d_lut(dataset, profile, grid_size=grid_size)
    lut_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", "luts", _LEARNED_LAB3D_LUT_FILENAME)
    np.savez(lut_path, table=table, domain=domain)

    lab3d_profile = dict(profile, learned_lab3d_lut=_LEARNED_LAB3D_LUT_FILENAME)
    in_sample_loss = _mean_loss(lab3d_profile, dataset)
    in_sample_improvement = (baseline_loss - in_sample_loss) / baseline_loss * 100
    print(f"3D LUT 보정 후 ΔE (in-sample, 과적합 위험 큼): {in_sample_loss:.3f} "
          f"({in_sample_improvement:+.1f}%)")

    loo_loss = None
    if len(dataset) > 1:
        loo_losses = []
        for i in range(len(dataset)):
            train_set = dataset[:i] + dataset[i + 1:]
            held_out = [dataset[i]]
            table_i, domain_i = learn_lab3d_lut(train_set, profile, grid_size=grid_size)
            fold_path = lut_path + f".fold{i}.npz"
            np.savez(fold_path, table=table_i, domain=domain_i)
            try:
                fold_profile = dict(profile, learned_lab3d_lut=fold_path)
                loo_losses.append(_mean_loss(fold_profile, held_out))
            finally:
                os.remove(fold_path)
        loo_loss = float(np.mean(loo_losses))
        loo_improvement = (baseline_loss - loo_loss) / baseline_loss * 100
        print(f"3D LUT 보정 후 ΔE (leave-one-out 교차검증, {len(dataset)}-fold): "
              f"{loo_loss:.3f} ({loo_improvement:+.1f}%)")

    return baseline_loss, in_sample_loss, loo_loss, lut_path


# LUT 계열(톤/hue/2D/3D) 네 실험이 전부 교차검증 기준 음성으로 끝난 뒤의
# 다음 시도 - 이웃 픽셀을 보는 공간 연산(Phase 2). 파라미터가 3개뿐인
# 파라메트릭 모델이라 LUT들과 달리 과적합 위험이 원래 낮다 - 그래도
# in-sample만 믿지 않는 원칙은 동일하게 유지(k-fold 교차검증도 같이 낸다).
_SPATIAL_SEARCH_SPACE = {
    "spatial_radius": [10.0, 20.0, 30.0, 50.0, 80.0],
    "spatial_amount": [0.0, 0.1, 0.2, 0.3, 0.5, 0.8, 1.2],
    "spatial_threshold": [0.0, 0.5, 1.0, 2.0],
}


def _spatial_coordinate_descent(dataset, base_profile, n_passes=1, search_space=None):
    """base_profile(이미 캘리브레이션된 톤/채도 파라미터) 위에 spatial_*
    3개만 좌표하강으로 탐색 - 나머지 파라미터는 고정."""
    search_space = search_space or _SPATIAL_SEARCH_SPACE
    params = dict(base_profile)
    params["use_spatial"] = True
    params.setdefault("spatial_radius", _DEFAULT_PARAMS["spatial_radius"])
    params.setdefault("spatial_amount", _DEFAULT_PARAMS["spatial_amount"])
    params.setdefault("spatial_threshold", _DEFAULT_PARAMS["spatial_threshold"])
    best_loss = _mean_loss(params, dataset)

    for _ in range(n_passes):
        for key, candidates in search_space.items():
            best_val = params[key]
            for val in candidates:
                trial = dict(params)
                trial[key] = val
                loss = _mean_loss(trial, dataset)
                if loss < best_loss:
                    best_loss = loss
                    best_val = val
            params[key] = best_val

    return params, best_loss


def run_spatial_mode(dataset, n_folds=4, seed=0):
    """Phase 2(로컬 콘트라스트) 모드: base profile(hasselblad.json) 위에
    spatial_* 파라미터만 좌표하강으로 탐색하고, in-sample ΔE와 k-fold
    교차검증 ΔE(기본 4-fold - LUT 실험들의 leave-one-out보다 폴드당 비용이
    큰 좌표하강을 13번이 아니라 4번만 반복해서 계산량을 절충)를 둘 다
    낸다. 채택 여부는 교차검증 기준."""
    import json
    profile_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", "profiles", "hasselblad.json")
    with open(profile_path, encoding="utf-8") as f:
        base_profile = json.load(f)
    base_profile.pop("_comment", None)
    base_profile["use_spatial"] = False

    baseline_loss = _mean_loss(base_profile, dataset)
    print(f"공간 연산 보정 전 ΔE (기준선): {baseline_loss:.3f}")

    tuned_params, in_sample_loss = _spatial_coordinate_descent(dataset, base_profile)
    in_sample_improvement = (baseline_loss - in_sample_loss) / baseline_loss * 100
    print(f"공간 연산 보정 후 ΔE (in-sample): {in_sample_loss:.3f} "
          f"({in_sample_improvement:+.1f}%)  "
          f"radius={tuned_params['spatial_radius']} amount={tuned_params['spatial_amount']} "
          f"threshold={tuned_params['spatial_threshold']}")

    cv_loss = None
    if len(dataset) >= n_folds:
        rng = np.random.default_rng(seed)
        order = rng.permutation(len(dataset))
        folds = np.array_split(order, n_folds)
        fold_losses = []
        for fold_idx in folds:
            fold_idx_set = set(fold_idx.tolist())
            train_set = [d for i, d in enumerate(dataset) if i not in fold_idx_set]
            held_out = [dataset[i] for i in fold_idx]
            fold_params, _ = _spatial_coordinate_descent(train_set, base_profile)
            fold_losses.append(_mean_loss(fold_params, held_out))
        cv_loss = float(np.mean(fold_losses))
        cv_improvement = (baseline_loss - cv_loss) / baseline_loss * 100
        print(f"공간 연산 보정 후 ΔE ({n_folds}-fold 교차검증): {cv_loss:.3f} "
              f"({cv_improvement:+.1f}%)")

    return baseline_loss, in_sample_loss, cv_loss, tuned_params


_GRAY_WORLD_PERCENTILE_CANDIDATES = [30.0, 50.0, 70.0, 85.0, 100.0]


def run_gray_world_mode(dataset):
    """robust gray world(EVALUATION.md 후속 실측 10에서 확인된 야경
    과보정 대책) 모드: `gray_world_saturation_percentile`을 후보 격자에서
    탐색한다. 이 파라미터는 페어별 손실이 서로 독립이라(joint fitting이
    없음) 후보 x 페어 손실 행렬 한 번만 계산하면 leave-one-out 교차검증을
    정확하게(근사 없이) 돌릴 수 있다 - 각 held-out 페어에 대해 나머지
    12쌍 평균이 최소인 후보를 고르고 그 후보의 held-out 손실을 기록.
    채택 여부는 교차검증 기준(이 프로젝트의 확립된 원칙)."""
    import json
    profile_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", "profiles", "hasselblad.json")
    with open(profile_path, encoding="utf-8") as f:
        base_profile = json.load(f)
    base_profile.pop("_comment", None)

    candidates = _GRAY_WORLD_PERCENTILE_CANDIDATES
    n = len(dataset)
    loss_matrix = np.zeros((len(candidates), n))
    for ci, pct in enumerate(candidates):
        params = dict(base_profile)
        params["gray_world_saturation_percentile"] = pct
        engine = HybridCameraEngine(profile=params)
        for pi, (linear_small, camera_wb, target_small) in enumerate(dataset):
            result = engine.process(linear_small, camera_whitebalance=camera_wb)
            loss_matrix[ci, pi] = mean_delta_e(result, target_small)
        print(f"  percentile={pct:5.1f}: 평균 ΔE {loss_matrix[ci].mean():.3f}")

    baseline_idx = candidates.index(100.0)
    baseline_loss = float(loss_matrix[baseline_idx].mean())
    in_sample_idx = int(np.argmin(loss_matrix.mean(axis=1)))
    in_sample_loss = float(loss_matrix[in_sample_idx].mean())
    print(f"\n기준선(percentile=100, 기존 gray world) ΔE: {baseline_loss:.3f}")
    print(f"in-sample 최선: percentile={candidates[in_sample_idx]} "
          f"ΔE {in_sample_loss:.3f} "
          f"({(baseline_loss - in_sample_loss) / baseline_loss * 100:+.1f}%)")

    loo_losses = []
    chosen = []
    for held_out in range(n):
        train_mean = np.delete(loss_matrix, held_out, axis=1).mean(axis=1)
        best_ci = int(np.argmin(train_mean))
        chosen.append(candidates[best_ci])
        loo_losses.append(loss_matrix[best_ci, held_out])
    loo_loss = float(np.mean(loo_losses))
    print(f"leave-one-out 교차검증 ΔE: {loo_loss:.3f} "
          f"({(baseline_loss - loo_loss) / baseline_loss * 100:+.1f}%)  "
          f"fold별 선택: {chosen}")

    print("\n페어별 ΔE (기준선 -> in-sample 최선 후보):")
    for pi, (linear_small, camera_wb, target_small) in enumerate(dataset):
        print(f"  pair {pi}: {loss_matrix[baseline_idx, pi]:6.2f} -> "
              f"{loss_matrix[in_sample_idx, pi]:6.2f}")

    return baseline_loss, in_sample_loss, loo_loss, candidates[in_sample_idx]


_GRAY_WORLD_ZONES_CANDIDATES = [1, 2, 3, 4, 5]


def run_gray_world_zoned_mode(dataset):
    """zoned gray world(EVALUATION.md 후속 실측 10/11 - 야경 하늘 과보정을
    밝기 구간별 독립 추정으로 겨냥) 모드: `gray_world_zones`를 후보
    격자에서 탐색한다. run_gray_world_mode와 동일한 구조(후보 x 페어
    손실 행렬 -> 정확한 leave-one-out) - zones=1이 기존 동작(기준선)."""
    import json
    profile_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", "profiles", "hasselblad.json")
    with open(profile_path, encoding="utf-8") as f:
        base_profile = json.load(f)
    base_profile.pop("_comment", None)

    candidates = _GRAY_WORLD_ZONES_CANDIDATES
    n = len(dataset)
    loss_matrix = np.zeros((len(candidates), n))
    for ci, nz in enumerate(candidates):
        params = dict(base_profile)
        params["gray_world_zones"] = nz
        engine = HybridCameraEngine(profile=params)
        for pi, (linear_small, camera_wb, target_small) in enumerate(dataset):
            result = engine.process(linear_small, camera_whitebalance=camera_wb)
            loss_matrix[ci, pi] = mean_delta_e(result, target_small)
        print(f"  zones={nz}: 평균 ΔE {loss_matrix[ci].mean():.3f}")

    baseline_idx = candidates.index(1)
    baseline_loss = float(loss_matrix[baseline_idx].mean())
    in_sample_idx = int(np.argmin(loss_matrix.mean(axis=1)))
    in_sample_loss = float(loss_matrix[in_sample_idx].mean())
    print(f"\n기준선(zones=1, 기존 gray world) ΔE: {baseline_loss:.3f}")
    print(f"in-sample 최선: zones={candidates[in_sample_idx]} "
          f"ΔE {in_sample_loss:.3f} "
          f"({(baseline_loss - in_sample_loss) / baseline_loss * 100:+.1f}%)")

    loo_losses = []
    chosen = []
    for held_out in range(n):
        train_mean = np.delete(loss_matrix, held_out, axis=1).mean(axis=1)
        best_ci = int(np.argmin(train_mean))
        chosen.append(candidates[best_ci])
        loo_losses.append(loss_matrix[best_ci, held_out])
    loo_loss = float(np.mean(loo_losses))
    print(f"leave-one-out 교차검증 ΔE: {loo_loss:.3f} "
          f"({(baseline_loss - loo_loss) / baseline_loss * 100:+.1f}%)  "
          f"fold별 선택: {chosen}")

    print("\n페어별 ΔE (기준선 -> in-sample 최선 후보):")
    for pi, (linear_small, camera_wb, target_small) in enumerate(dataset):
        print(f"  pair {pi}: {loss_matrix[baseline_idx, pi]:6.2f} -> "
              f"{loss_matrix[in_sample_idx, pi]:6.2f}")

    return baseline_loss, in_sample_loss, loo_loss, candidates[in_sample_idx]


_GRAY_WORLD_STRENGTH_CANDIDATES = [0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.3, 1.4]


def run_gray_world_strength_mode(dataset):
    """gray world 미세보정(후속 실측 14) 모드: percentile/hue-chroma/zoned
    (후속 실측 11/12/13) 전부 자유도를 늘리는 방향이었다가 기각된 것과
    반대로, `gray_world_strength`(추정된 색치우침 보정을 항등과 섞는
    배율, 자유도 1개) 하나만 촘촘한 격자로 탐색한다. strength=1.0이
    기존 동작(기준선)."""
    import json
    profile_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", "profiles", "hasselblad.json")
    with open(profile_path, encoding="utf-8") as f:
        base_profile = json.load(f)
    base_profile.pop("_comment", None)

    candidates = _GRAY_WORLD_STRENGTH_CANDIDATES
    n = len(dataset)
    loss_matrix = np.zeros((len(candidates), n))
    for ci, s in enumerate(candidates):
        params = dict(base_profile)
        params["gray_world_strength"] = s
        engine = HybridCameraEngine(profile=params)
        for pi, (linear_small, camera_wb, target_small) in enumerate(dataset):
            result = engine.process(linear_small, camera_whitebalance=camera_wb)
            loss_matrix[ci, pi] = mean_delta_e(result, target_small)
        print(f"  strength={s:.2f}: 평균 ΔE {loss_matrix[ci].mean():.3f}")

    baseline_idx = candidates.index(1.0)
    baseline_loss = float(loss_matrix[baseline_idx].mean())
    in_sample_idx = int(np.argmin(loss_matrix.mean(axis=1)))
    in_sample_loss = float(loss_matrix[in_sample_idx].mean())
    print(f"\n기준선(strength=1.0, 기존 gray world) ΔE: {baseline_loss:.3f}")
    print(f"in-sample 최선: strength={candidates[in_sample_idx]} "
          f"ΔE {in_sample_loss:.3f} "
          f"({(baseline_loss - in_sample_loss) / baseline_loss * 100:+.1f}%)")

    loo_losses = []
    chosen = []
    for held_out in range(n):
        train_mean = np.delete(loss_matrix, held_out, axis=1).mean(axis=1)
        best_ci = int(np.argmin(train_mean))
        chosen.append(candidates[best_ci])
        loo_losses.append(loss_matrix[best_ci, held_out])
    loo_loss = float(np.mean(loo_losses))
    print(f"leave-one-out 교차검증 ΔE: {loo_loss:.3f} "
          f"({(baseline_loss - loo_loss) / baseline_loss * 100:+.1f}%)  "
          f"fold별 선택: {chosen}")

    print("\n페어별 ΔE (기준선 -> in-sample 최선 후보):")
    for pi, (linear_small, camera_wb, target_small) in enumerate(dataset):
        print(f"  pair {pi}: {loss_matrix[baseline_idx, pi]:6.2f} -> "
              f"{loss_matrix[in_sample_idx, pi]:6.2f}")

    return baseline_loss, in_sample_loss, loo_loss, candidates[in_sample_idx]


def run_raw_baseline_mode(dataset, n_folds=4, seed=0):
    """GitHub 이슈 #4 대응: hybrid_engine의 Phase 0-2를 전혀 안 거친
    순수 rawpy 디코드(_load_calib_set()이 만든 linear_small 그대로)에
    전역 3x3 선형 컬러 매트릭스 하나만 최소자승으로 맞춰서, "이론상
    최선의 선형 보정만"의 ΔE가 hybrid_engine 현재 ΔE와 비교해 어느
    수준인지 잰다. 병목이 색 매트릭스(raw 베이스라인) 자체 때문인지,
    그 이후의 비선형 처리(톤/채도/hue/공간) 때문인지 분리하는 게
    목적 - core/raw_baseline.py 참고."""
    from hybrid_engine.core.raw_baseline import fit_color_matrix, apply_color_matrix
    from hybrid_engine.utils.evaluate import mean_delta_e

    import json
    profile_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", "profiles", "hasselblad.json")
    with open(profile_path, encoding="utf-8") as f:
        profile = json.load(f)
    profile.pop("_comment", None)

    hybrid_loss = _mean_loss(profile, dataset)
    print(f"hybrid_engine 현재 ΔE (파라메트릭 profile, 참고용): {hybrid_loss:.3f}")

    raw_sources = [d[0] for d in dataset]
    targets = [d[2] for d in dataset]

    no_correction_loss = float(np.mean(
        [mean_delta_e(s, t) for s, t in zip(raw_sources, targets)]))
    print(f"raw 디코드 자체(무보정) ΔE: {no_correction_loss:.3f}")

    matrix = fit_color_matrix(raw_sources, targets)
    in_sample_loss = float(np.mean(
        [mean_delta_e(apply_color_matrix(s, matrix), t) for s, t in zip(raw_sources, targets)]))
    print(f"3x3 매트릭스 보정 ΔE (in-sample): {in_sample_loss:.3f}")

    cv_loss = None
    if len(dataset) >= n_folds:
        rng = np.random.default_rng(seed)
        order = rng.permutation(len(dataset))
        folds = np.array_split(order, n_folds)
        fold_losses = []
        for fold_idx in folds:
            fold_idx_set = set(fold_idx.tolist())
            train_sources = [raw_sources[i] for i in range(len(dataset)) if i not in fold_idx_set]
            train_targets = [targets[i] for i in range(len(dataset)) if i not in fold_idx_set]
            fold_matrix = fit_color_matrix(train_sources, train_targets)
            for i in fold_idx:
                fold_losses.append(mean_delta_e(
                    apply_color_matrix(raw_sources[i], fold_matrix), targets[i]))
        cv_loss = float(np.mean(fold_losses))
        print(f"3x3 매트릭스 보정 ΔE ({n_folds}-fold 교차검증): {cv_loss:.3f}")

    print(f"\n적합된 3x3 매트릭스:\n{matrix}")
    return hybrid_loss, no_correction_loss, in_sample_loss, cv_loss, matrix


def _find_matrix_and_recalibrate(dataset, n_passes=1):
    """Phase 0(raw_baseline_matrix)을 dataset으로 먼저 최소자승 적합한
    뒤, 그 매트릭스를 고정하고 Phase 1(tone_core)/Phase 2(color_core)
    파라미터(_SEARCH_SPACE)를 좌표하강으로 재탐색한다. 사용자 지시:
    "삭제하지 않고 Phase 0=매트릭스, Phase1=tone_core 재학습,
    Phase2=color_core 재학습". 반환: (raw_baseline_matrix 포함된 params
    dict, ΔE).

    normalize_exposure=False로 강제한다 - 진단 실측 결과, 매트릭스
    적용 후 모든 사진의 평균 밝기를 target_gray로 강제로 맞추는 노출
    정규화 단계가 매트릭스의 이득을 거의 다 없앴다(ΔE 8.55 -> 14.62,
    EVALUATION.md 후속 실측 6). Gray World(색치우침 제거)는 오히려
    도움이 돼서 correct_color_cast는 그대로 둠."""
    from hybrid_engine.core.raw_baseline import fit_color_matrix

    raw_sources = [d[0] for d in dataset]
    targets = [d[2] for d in dataset]
    matrix = fit_color_matrix(raw_sources, targets)

    base_params = dict(_DEFAULT_PARAMS)
    base_params["raw_baseline_matrix"] = matrix.tolist()
    base_params["normalize_exposure"] = False
    params, loss = coordinate_descent(dataset, n_passes=n_passes, base_params=base_params)
    return params, loss


def run_raw_baseline_pipeline_mode(dataset, n_folds=4, seed=0, n_passes=1):
    """Phase 0(3x3 raw_baseline 매트릭스) 위에 Phase 1(tone_core)/Phase 2
    (color_core)을 재캘리브레이션하는 전체 파이프라인 모드 - 후속 실측 5
    (raw_baseline 단독 32.6% 개선)에 대한 실제 통합. 기존
    hasselblad.json(파라메트릭 profile)을 참고선으로 두고 비교한다.
    교차검증은 폴드마다 매트릭스 적합부터 좌표하강까지 전부 그 폴드의
    학습 데이터만으로 다시 하는 완전한 nested CV(매트릭스만 고정하고
    파라미터만 재탐색하면 매트릭스 쪽에서 데이터 유출이 생기므로)."""
    import json
    profile_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", "profiles", "hasselblad.json")
    with open(profile_path, encoding="utf-8") as f:
        old_profile = json.load(f)
    old_profile.pop("_comment", None)
    old_loss = _mean_loss(old_profile, dataset)
    print(f"기존 파이프라인 ΔE (현재 hasselblad.json): {old_loss:.3f}")

    new_params, in_sample_loss = _find_matrix_and_recalibrate(dataset, n_passes=n_passes)
    in_sample_improvement = (old_loss - in_sample_loss) / old_loss * 100
    print(f"\n신규 파이프라인 ΔE (in-sample, 매트릭스+재학습 톤/채도): "
          f"{in_sample_loss:.3f} ({in_sample_improvement:+.1f}%)")

    cv_loss = None
    if len(dataset) >= n_folds:
        rng = np.random.default_rng(seed)
        order = rng.permutation(len(dataset))
        folds = np.array_split(order, n_folds)
        fold_losses = []
        for fold_idx in folds:
            fold_idx_set = set(fold_idx.tolist())
            train_set = [d for i, d in enumerate(dataset) if i not in fold_idx_set]
            held_out = [dataset[i] for i in fold_idx]
            fold_params, _ = _find_matrix_and_recalibrate(train_set, n_passes=n_passes)
            fold_losses.append(_mean_loss(fold_params, held_out))
        cv_loss = float(np.mean(fold_losses))
        cv_improvement = (old_loss - cv_loss) / old_loss * 100
        print(f"신규 파이프라인 ΔE ({n_folds}-fold 교차검증): {cv_loss:.3f} "
              f"({cv_improvement:+.1f}%)")

    return old_loss, in_sample_loss, cv_loss, new_params


def run_learned_mode(dataset):
    """학습 LUT 모드: 캘리브레이션된 파라메트릭 profile을 베이스로 톤
    단계만 학습 LUT으로 교체하고 ΔE를 파라메트릭과 비교한다. 더 나을
    때만 채택하라는 게 이 함수를 부르는 쪽(main)의 책임."""
    import json
    profile_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", "profiles", "hasselblad.json")
    with open(profile_path, encoding="utf-8") as f:
        profile = json.load(f)
    profile.pop("_comment", None)
    profile.pop("learned_tone_lut", None)  # 학습 도메인은 항상 파라메트릭 전 단계 기준

    parametric_loss = _mean_loss(profile, dataset)
    print(f"파라메트릭 profile ΔE (기준선): {parametric_loss:.3f}")

    lut = learn_tone_lut(dataset, profile)
    lut_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", "luts", _LEARNED_LUT_FILENAME)
    np.save(lut_path, lut)

    learned_profile = dict(profile, learned_tone_lut=_LEARNED_LUT_FILENAME)
    learned_loss = _mean_loss(learned_profile, dataset)
    print(f"학습 LUT ΔE:                  {learned_loss:.3f}")

    improvement = (parametric_loss - learned_loss) / parametric_loss * 100
    print(f"개선폭: {improvement:+.1f}%")
    return parametric_loss, learned_loss, lut_path


def main():
    import argparse
    parser = argparse.ArgumentParser(description="hybrid_engine profile 캘리브레이션")
    parser.add_argument("--mode",
                         choices=["parametric", "learned", "hue", "hue_chroma", "lab2d", "lab3d",
                                  "spatial", "raw_baseline", "raw_baseline_pipeline", "gray_world",
                                  "gray_world_zoned", "gray_world_strength"],
                         default="parametric",
                         help="parametric: 좌표하강으로 profile 파라미터 탐색(기본) / "
                              "learned: 톤 단계를 픽셀 대응 학습 1D LUT으로 교체하고 ΔE 비교 / "
                              "hue: hue 보정 단계(V0.1엔 없던 축)를 학습 순환 LUT으로 추가하고 ΔE 비교 / "
                              "hue_chroma: hue별 chroma 배율(피부톤 등 특정 hue의 국소 채도 부족)을 학습 순환 LUT으로 추가하고 ΔE 비교 / "
                              "lab2d: a/b 결합 2D 잔차 LUT을 추가하고 in-sample+leave-one-out ΔE 비교 / "
                              "lab3d: L/a/b 결합 3D 잔차 LUT을 추가하고 in-sample+leave-one-out ΔE 비교 / "
                              "spatial: Phase 3 로컬 콘트라스트 파라미터를 좌표하강으로 탐색하고 in-sample+k-fold ΔE 비교 / "
                              "raw_baseline: hybrid_engine을 거치지 않은 순수 raw 디코드에 3x3 매트릭스만 맞춰서 이론적 최선 ΔE 측정(이슈 #4) / "
                              "raw_baseline_pipeline: Phase 0 매트릭스 위에 Phase 1(tone)/Phase 2(color)를 재캘리브레이션한 전체 파이프라인 ΔE 비교(nested CV) / "
                              "gray_world: robust gray world의 saturation percentile을 탐색하고 in-sample+LOO ΔE 비교(후속 실측 10 대응) / "
                              "gray_world_zoned: 밝기 구간별 독립 gray world의 zones 수를 탐색하고 in-sample+LOO ΔE 비교(후속 실측 10/11 대응) / "
                              "gray_world_strength: gray world 보정 강도(자유도 1개, 0~1.4 촘촘한 격자)를 탐색하고 in-sample+LOO ΔE 비교(후속 실측 14)")
    args = parser.parse_args()

    print("raw+jpeg 페어 로드 중 (캘리브레이션용 축소 해상도)...")
    dataset = _load_calib_set()
    print(f"총 {len(dataset)}쌍 로드 완료\n")
    if not dataset:
        print("페어를 못 찾음 - raw_calib_cache/ 확인 필요")
        return

    if args.mode == "learned":
        run_learned_mode(dataset)
        return

    if args.mode == "hue":
        run_hue_mode(dataset)
        return

    if args.mode == "hue_chroma":
        run_hue_chroma_mode(dataset)
        return

    if args.mode == "lab2d":
        run_lab2d_mode(dataset)
        return

    if args.mode == "lab3d":
        run_lab3d_mode(dataset)
        return

    if args.mode == "spatial":
        run_spatial_mode(dataset)
        return

    if args.mode == "raw_baseline":
        run_raw_baseline_mode(dataset)
        return

    if args.mode == "raw_baseline_pipeline":
        run_raw_baseline_pipeline_mode(dataset)
        return

    if args.mode == "gray_world":
        run_gray_world_mode(dataset)
        return

    if args.mode == "gray_world_zoned":
        run_gray_world_zoned_mode(dataset)
        return

    if args.mode == "gray_world_strength":
        run_gray_world_strength_mode(dataset)
        return

    params, final_loss = coordinate_descent(dataset)

    print(f"\n최종 평균 ΔE: {final_loss:.3f}")
    print(f"최종 파라미터: {params}")

    profile_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", "profiles", "hasselblad.json")
    import json
    output = {
        "_comment": (
            f"v1.1 - {len(dataset)}쌍의 실제 핫셀블라드 raw+jpeg 페어(raw_calib_cache/)로 "
            f"hybrid_engine.calibrate_profile의 좌표하강 ΔE 루프를 돌려서 캘리브레이션함. "
            f"최종 평균 ΔE(CIEDE2000)={final_loss:.2f}. brands/hasselblad.py의 apply_hncs와는 "
            "여전히 다른 커브 수식이라 그쪽 파라미터와 직접 비교는 안 됨 - 이 profile 자체의 "
            "실측 기반 최적값이라는 의미."
        ),
        **{k: v for k, v in params.items() if k not in
           ("correct_color_cast", "use_color_unification", "use_spatial")},
        "correct_color_cast": params["correct_color_cast"],
        "use_color_unification": params["use_color_unification"],
        "use_spatial": params["use_spatial"],
    }
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"\n저장: {profile_path}")


if __name__ == "__main__":
    main()
