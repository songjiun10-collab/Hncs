"""
hybrid_engine의 production 체인(hybrid_engine/main.py)을 그대로 따라가 보면:

  1. utils/io.decode_raw() - rawpy use_camera_wb=True로 카메라 자체
     화이트밸런스(광원 추정)를 이미 적용해서 linear RGB를 뽑는다.
  2. core/color_matrix.estimate_source_white_xy(camera_whitebalance) -
     방금 1번에서 rawpy가 쓴 것과 **같은** camera_whitebalance 메타데이터로
     광원 백색점을 추정.
  3. core/color_matrix.unify_to_d65() - 2번 백색점 -> D65로 Bradford
     색순응 변환(pipeline/engine.py의 to_normalized_lab, use_color_unification
     기본 True).
  4. core/normalizer.gray_world_normalize() - 그 위에 또 Gray World
     정규화(correct_color_cast 기본 True) - normalizer.py.

같은 화이트밸런스 추정치를 1번(rawpy 내부)과 3번(Bradford)이 **두 번**
쓰고, 그 위에 4번(Gray World)까지 걸리는 구조라 실제로 이중/삼중
보정인지 아니면 서로 다른 잔차를 잡아내는 정당한 단계인지 raw+jpeg
페어의 실측 ΔE00으로 직접 확인한다.

  A = rawpy camera WB only         (decode_raw, 그 이상 없음)
  B = rawpy camera WB + Bradford   (decode_raw + unify_to_d65,
                                     현재 production 기본과 동일한 조합)
  C = native/no-WB + Bradford      (decode_raw_native + unify_to_d65,
                                     camera_whitebalance로 색순응만 1번)
  D = native/no-WB + Gray World    (decode_raw_native + gray_world_normalize,
                                     메타데이터 없이 장면 통계만으로 1번)

각 변형에 hybrid_engine/calibrate_profile.py의 run_raw_baseline_mode와
동일한 방법론(전역 3x3 컬러 매트릭스를 최소자승으로 피팅 - 톤/채도
커브는 전혀 안 거침, "이 색 기초가 얼마나 좋은가"만 분리해서 측정)을
적용하고 leave-one-out 교차검증 ΔE00으로 비교한다.
hybrid_engine.utils.evaluate는 이 환경에서 colour-science 버전
불일치로 임포트가 깨져 있어(기존에 알려진 24개 베이스라인 에러 중 하나)
mean_delta_e를 이 파일 안에 직접 구현한다(tools/evaluate_*.py 관례).

데이터: raw_calib_cache/의 공식 13쌍(tools/calibrate.py의 collect_pairs()가
받아오는 것과 동일 - 없으면 먼저 그 스크립트로 다운로드해야 함).
9쌍은 tools/calibrate.py가 EXIF Software 태그로 걸러낸 편집(Photoshop/
Lightroom) 오염 타깃이라 절대 ΔE 값 자체는 부풀려져 있을 수 있지만,
A/B/C/D 네 변형이 전부 같은 13쌍·같은 타깃을 쓰므로 상대 비교(어느
변형이 이기는지)에는 영향 없다.

  python3 -m tools.evaluate_wb_pipeline_variants
"""
import glob
import math
import os
import sys

import colour
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hybrid_engine.core import color_matrix, normalizer
from hybrid_engine.core.raw_baseline import fit_color_matrix, apply_color_matrix
from hybrid_engine.utils.io import decode_raw, decode_raw_native, load_image_linear

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "raw_calib_cache")
CALIB_MAX_DIM = 500


def _resize_max_dim(img, max_dim):
    import cv2
    h, w = img.shape[:2]
    scale = max_dim / max(h, w)
    if scale >= 1:
        return img
    return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def _find_pairs():
    raw_paths = sorted(glob.glob(os.path.join(CACHE_DIR, "*.3FR")) +
                        glob.glob(os.path.join(CACHE_DIR, "*.fff")))
    pairs = []
    for raw_path in raw_paths:
        base = raw_path.rsplit(".", 1)[0]
        target_path = base + ".target.jpg"
        if os.path.exists(target_path):
            pairs.append((raw_path, target_path))
    return pairs


def mean_delta_e(linear_a, linear_b):
    from skimage.color import rgb2lab, deltaE_ciede2000
    a = colour.cctf_encoding(np.clip(linear_a, 0.0, 1.0), function="sRGB")
    b = colour.cctf_encoding(np.clip(linear_b, 0.0, 1.0), function="sRGB")
    return float(np.mean(deltaE_ciede2000(rgb2lab(a), rgb2lab(b))))


_SRGB = colour.RGB_COLOURSPACES["sRGB"]


def _bradford(rgb_linear, camera_whitebalance):
    """pipeline/engine.py의 to_normalized_lab()이 하는 것과 동일한
    호출(estimate_source_white_xy + unify_to_d65) - RGB<->XYZ 변환은 항상
    apply_cctf_(de|en)coding=False로, decode_raw*()의 출력이 이미 linear라
    감마를 다시 걸면 안 된다."""
    source_white_xy = color_matrix.estimate_source_white_xy(camera_whitebalance)
    xyz = colour.RGB_to_XYZ(rgb_linear, _SRGB, apply_cctf_decoding=False)
    xyz = color_matrix.unify_to_d65(xyz, source_white_xy)
    return np.clip(colour.XYZ_to_RGB(xyz, _SRGB, apply_cctf_encoding=False), 0.0, None)


def _load_variants():
    """각 페어에 대해 (A, B, C, D, target) linear RGB 소스를 만든다 -
    전부 CALIB_MAX_DIM으로 축소해서 계산량을 억제한다(_load_calib_set()과
    동일한 축소 정책)."""
    variants = {"A": [], "B": [], "C": [], "D": []}
    targets = []
    names = []
    for raw_path, target_path in _find_pairs():
        name = os.path.basename(raw_path)
        print(f"  로드 중: {name}", flush=True)
        camera_wb = color_matrix.extract_camera_metadata(raw_path)["camera_whitebalance"]

        wb_linear = _resize_max_dim(decode_raw(raw_path), CALIB_MAX_DIM)
        native_linear = _resize_max_dim(decode_raw_native(raw_path), CALIB_MAX_DIM)
        target_small = load_image_linear(target_path, resize_to=wb_linear.shape[:2])

        variants["A"].append(wb_linear)
        variants["B"].append(_bradford(wb_linear, camera_wb))
        variants["C"].append(_bradford(native_linear, camera_wb))
        variants["D"].append(normalizer.gray_world_normalize(native_linear))
        targets.append(target_small)
        names.append(name)
    return variants, targets, names


def _loo_delta_es(sources, targets):
    """run_raw_baseline_mode와 동일한 절차 - 페어별로 자신을 뺀 나머지로
    3x3 매트릭스를 피팅하고, 자신에게 적용해 ΔE00을 낸다(진짜
    leave-one-out, 표본이 13개뿐이라 in-sample 과최적화를 피하려면
    이게 맞다)."""
    n = len(sources)
    des = np.zeros(n)
    for held_out in range(n):
        train_sources = [sources[i] for i in range(n) if i != held_out]
        train_targets = [targets[i] for i in range(n) if i != held_out]
        matrix = fit_color_matrix(train_sources, train_targets)
        pred = apply_color_matrix(sources[held_out], matrix)
        des[held_out] = mean_delta_e(pred, targets[held_out])
    return des


def _sign_test_p(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def summarize(label_a, des_a, label_b, des_b, n_bootstrap=20000, seed=0):
    """페어드 비교 - des_b가 des_a보다 작으면(=더 좋으면) 양수 improvement.
    tools/calibrate.py의 summarize()와 같은 통계(부트스트랩 CI, 부호검정) -
    evaluate_*.py는 형제 스크립트를 import하지 않는 컨벤션이라 복붙."""
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
        idx = rng.integers(0, n, n)
        boot[i] = diff[idx].mean()
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


def main():
    pairs = _find_pairs()
    print(f"raw_calib_cache 페어 {len(pairs)}개 발견", flush=True)
    if len(pairs) < 4:
        print("표본이 너무 적어(< 4) LOO를 못 함 - raw_calib_cache 확인 필요")
        return

    variants, targets, names = _load_variants()

    print("\n각 변형에 leave-one-out 3x3 매트릭스 ΔE00 계산 중...", flush=True)
    loo = {}
    for label in ("A", "B", "C", "D"):
        loo[label] = _loo_delta_es(variants[label], targets)
        print(f"  {label}: 평균 LOO ΔE00 = {loo[label].mean():.3f} "
              f"(개별: {', '.join(f'{v:.2f}' for v in loo[label])})")

    print("\n" + "=" * 60)
    print("A vs B - rawpy camera WB에 Bradford를 더 걸면(현재 production 조합) "
          "이득인지 손해인지(이중처리 핵심 질문)")
    summarize("A", loo["A"], "B", loo["B"])

    print("\n" + "=" * 60)
    print("A vs C - camera WB를 아예 건너뛰고 Bradford만 쓰면 camera WB보다 나은지")
    summarize("A", loo["A"], "C", loo["C"])

    print("\n" + "=" * 60)
    print("A vs D - camera WB만 쓰는 것과 native+Gray World 비교")
    summarize("A", loo["A"], "D", loo["D"])

    print("\n" + "=" * 60)
    print("C vs D - native에서 출발할 때 Bradford(메타데이터 기반) vs "
          "Gray World(장면 통계 기반)")
    summarize("C", loo["C"], "D", loo["D"])

    print("\n" + "=" * 60)
    print("B vs D - 현재 production 조합(A+Bradford) vs native+Gray World")
    summarize("B", loo["B"], "D", loo["D"])

    means = {label: float(loo[label].mean()) for label in loo}
    best = min(means, key=means.get)
    print("\n" + "=" * 60)
    print(f"평균 LOO ΔE00 최소: {best} ({means[best]:.3f}) - "
          f"전체: {', '.join(f'{k}={v:.3f}' for k, v in means.items())}")


if __name__ == "__main__":
    main()
