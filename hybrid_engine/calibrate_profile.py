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
    """(작은 linear RGB, camera_whitebalance, 작은 타깃 linear RGB) 튜플 리스트."""
    dataset = []
    for raw_path, target_path in _find_pairs():
        print(f"  로드 중: {os.path.basename(raw_path)}")
        linear = decode_raw(raw_path)
        linear_small = _resize_max_dim(linear, CALIB_MAX_DIM)
        camera_wb = color_matrix.extract_camera_metadata(raw_path)["camera_whitebalance"]
        target = load_image_linear(target_path)
        target_small = cv2.resize(target, (linear_small.shape[1], linear_small.shape[0]),
                                   interpolation=cv2.INTER_AREA)
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
    "sat_gain": [0.0, 0.04, 0.08, 0.12, 0.15, 0.2],
    "max_chroma": [90.0, 100.0, 110.0, 120.0, 140.0],
}


def coordinate_descent(dataset, n_passes=2):
    params = dict(_DEFAULT_PARAMS)
    best_loss = _mean_loss(params, dataset)
    print(f"시작 ΔE (V0.1 기본값): {best_loss:.3f}")

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
    보정 단계를 추가하고 ΔE를 비교한다. 더 나을 때만 채택하라는 게 이
    함수를 부르는 쪽(main)의 책임 - B1(학습 톤 LUT)이 +4.9%로 기각됐던
    선례와 같은 기준으로 판단."""
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
    hue_loss = _mean_loss(hue_profile, dataset)
    print(f"hue 보정 후 ΔE:          {hue_loss:.3f}")

    improvement = (baseline_loss - hue_loss) / baseline_loss * 100
    print(f"개선폭: {improvement:+.1f}%")
    return baseline_loss, hue_loss, lut_path


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
    parser.add_argument("--mode", choices=["parametric", "learned", "hue"], default="parametric",
                         help="parametric: 좌표하강으로 profile 파라미터 탐색(기본) / "
                              "learned: 톤 단계를 픽셀 대응 학습 1D LUT으로 교체하고 ΔE 비교 / "
                              "hue: hue 보정 단계(V0.1엔 없던 축)를 학습 순환 LUT으로 추가하고 ΔE 비교")
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
