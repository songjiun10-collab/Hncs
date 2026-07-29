"""hybrid_engine/research/hncs_structural.py(HNCS 실제 4단계 구조를
미러링한 실험 모듈)과 apply_hncs()의 ΔE를 같은 13쌍에서 비교한다
(leave-one-out 교차검증). 설계 근거:
docs/superpowers/specs/2026-07-28-hncs-structural-research-design.md

  python3 -m tools.evaluate_hncs_structural

**이 스크립트가 답하지 못하는 것**(결과를 읽을 때 반드시 같이 볼 것):

- 두 방식은 "구조(3단계 vs 4단계)"만 다른 게 아니다. 구조 실험 쪽은
  (a) 입력 디코드가 다르고(카메라 네이티브+AsShotNeutral WB vs
  libraw sRGB), (b) 3x3 매트릭스를 타깃 JPEG에 맞춰 **피팅**하고,
  (c) chroma 파라미터도 피팅한다. apply_hncs()는 이 실험 안에서 아무것도
  피팅하지 않는 고정 함수다. 따라서 차이가 나더라도 그게 "조명별
  구조" 덕분인지 "매트릭스를 데이터에 맞췄기 때문"인지 이 설계로는
  분리되지 않는다 - 1-클러스터 전역 매트릭스 대조군이 없다.
- 타깃은 카메라 내장 JPEG이지 Phocus/HNCS의 출력이 아니다. 이 실험은
  "카메라 JPEG에 얼마나 가까운가"를 재는 것이지 "진짜 HNCS에 얼마나
  가까운가"를 재는 게 아니다.
- apply_hncs()의 파라미터(exposure_gamma=0.7 등)는 과거에 바로 이
  페어들(당시 10쌍)로 그리드서치해 정한 값이라, 이 비교에서 apply_hncs()
  쪽은 부분적으로 in-sample이다.
"""
import csv
import glob
import itertools
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import colour
import cv2
import numpy as np

from brands.hasselblad import apply_hncs
from core.curve import film_curve
from hybrid_engine.core.raw_baseline import apply_color_matrix, fit_color_matrix
from hybrid_engine.research.hncs_structural import (
    apply_chroma_lut, classify_illuminant_cluster, decode_and_white_balance,
)
from hybrid_engine.utils.evaluate import load_image_linear_for_evaluate, mean_delta_e
from hybrid_engine.utils.exif import read_as_shot_neutral
from hybrid_engine.utils.io import decode_raw, decode_raw_native, load_image_linear

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(_ROOT, "raw_calib_cache")
CSV_PATH = os.path.join(_ROOT, "datasets", "hasselblad", "hasselblad_raw_jpeg_pairs.csv")

SAT_MULT_GRID = [0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15]
HUE_SHIFT_GRID = [-6.0, -4.0, -2.0, 0.0, 2.0, 4.0, 6.0]

# 4단계(공유 필름커브)는 **피팅하지 않는다** - film_curve()의 기본값이자
# apply_hncs()가 v11에서 채택한 값 그대로 고정이다. 설계 스펙 초안은 이
# 단계를 "13쌍 전체로 공유 피팅"한다고 썼지만 실제 구현은 안 그랬고,
# 그래서 "4단계 구조 미러링"이라 해도 데이터로 정해진 건 3단계(매트릭스,
# chroma LUT, 그리고 클러스터 분류)뿐이다. 두 방식이 같은 톤커브를 쓰게
# 되어 톤 단계를 통제변수로 묶는 효과는 있지만, 그 값 자체가 과거에
# 이 13쌍(당시 10쌍)으로 손보정된 값이라 구조 실험도 이 단계에 한해서는
# out-of-sample이 아니다. (EVALUATION.md "HNCS 구조 실험"의 한계 참고)
FILM_CURVE_TOE_LIFT = 0.001
FILM_CURVE_SHOULDER_START = 0.78
FILM_CURVE_WHITE_POINT = 1.0

# 주의: 이 값은 실측상 **사실상 무효(no-op)**다. fit_color_matrix()의
# ridge는 픽셀을 전부 쌓은 정규방정식 X^T X에 더해지는데, 다운샘플
# 이미지라도 클러스터당 픽셀이 수십만 개라 trace(X^T X)가 1e4~1e5
# 규모다(실측: cluster_b 3쌍 589,824픽셀에서 ridge/trace = 1.2e-5).
# ridge=1.0과 ridge=0.0의 피팅 결과 차이는 계수 최대 0.16%로, 결과 수치는
# 사실상 정규화 없는 최소자승과 같다. 즉 "ridge로 과적합을 억제했다"고
# 말할 수 없다 - 애초에 여기서 걱정할 과적합은 픽셀 수 대비 자유도가
# 아니라 **장면 수**(클러스터당 3~10장) 대비 일반화이고, pooled 픽셀에
# 거는 L2는 그걸 건드리지 않는다. 값을 바꾸지 않고 그대로 두는 이유는
# 기록된 실측치와의 재현성 때문이다.
MATRIX_RIDGE = 1.0

# 그리드서치+ΔE 루프가 폴드당 수백 번 반복되므로 축소본으로 처리한다 -
# 3x3 매트릭스와 2-파라미터 chroma LUT는 둘 다 공간 정보가 아니라 색
# 분포에만 의존하는 전역 변환이라 축소가 피팅 품질에 실질적 영향이
# 없다(결과 기록에 한계로 명시).
DOWNSAMPLE_MAX_DIM = 512

_PAIR_DATA_CACHE = {}
_BASELINE_CACHE = {}


def _pair_names():
    """CSV의 jpeg_url basename 목록(13개, 확장자 .jpg 포함) - 실제
    사진 페어만 담고 있고 raw_calib_cache/의 x2dii-chart-* 2개(다른
    데이터셋)는 여기 없다."""
    names = []
    with open(CSV_PATH, newline="") as f:
        for row in csv.DictReader(f):
            names.append(os.path.basename(row["jpeg_url"]))
    return names


def _raw_path_for(jpeg_name):
    matches = [m for m in glob.glob(os.path.join(CACHE_DIR, jpeg_name + ".*"))
               if not m.endswith(".target.jpg")]
    if len(matches) != 1:
        raise FileNotFoundError(f"raw for {jpeg_name}: expected 1 match, got {matches}")
    return matches[0]


def _target_path_for(jpeg_name):
    return os.path.join(CACHE_DIR, jpeg_name + ".target.jpg")


def _resize_max_dim(img, max_dim):
    """긴 변이 max_dim을 넘으면 종횡비 유지한 채 축소. 이미 작으면
    그대로 반환(no-op)."""
    h, w = img.shape[:2]
    scale = min(1.0, max_dim / max(h, w))
    if scale >= 1.0:
        return img
    new_w, new_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    resized = cv2.resize(img.astype(np.float32), (new_w, new_h),
                          interpolation=cv2.INTER_AREA)
    return resized.astype(np.float64)


def load_pairs():
    """13쌍 전부를 dict 리스트로 반환: name/raw_path/target_path/cluster."""
    pairs = []
    for jpeg_name in _pair_names():
        raw_path = _raw_path_for(jpeg_name)
        as_shot_neutral = read_as_shot_neutral(raw_path)
        cluster = classify_illuminant_cluster(as_shot_neutral)
        pairs.append({
            "name": jpeg_name, "raw_path": raw_path,
            "target_path": _target_path_for(jpeg_name), "cluster": cluster,
        })
    return pairs


def _pair_data(pair):
    """(wb_rgb, target_linear) 축소본을 캐시 - RAW 디코드가 느리고
    그리드서치가 같은 페어를 폴드마다 반복 사용하므로 이름으로 캐시."""
    name = pair["name"]
    if name not in _PAIR_DATA_CACHE:
        wb_rgb = _resize_max_dim(decode_and_white_balance(pair["raw_path"]),
                                  DOWNSAMPLE_MAX_DIM)
        target = load_image_linear(pair["target_path"], resize_to=wb_rgb.shape[:2])
        _PAIR_DATA_CACHE[name] = (wb_rgb, target)
    return _PAIR_DATA_CACHE[name]


def _hncs_baseline_and_target(pair):
    """apply_hncs() 공정 비교용 - decode_raw()(WB+libraw sRGB 매트릭스,
    "일반 카메라 JPEG" 근사) 기반 축소본 캐시."""
    name = pair["name"]
    if name not in _BASELINE_CACHE:
        baseline = _resize_max_dim(decode_raw(pair["raw_path"]), DOWNSAMPLE_MAX_DIM)
        target = load_image_linear(pair["target_path"], resize_to=baseline.shape[:2])
        _BASELINE_CACHE[name] = (baseline, target)
    return _BASELINE_CACHE[name]


def fit_matrices(train_pairs):
    """클러스터별 3x3 매트릭스 피팅 (ridge=MATRIX_RIDGE)."""
    by_cluster = {}
    for cluster in ("cluster_a", "cluster_b"):
        cluster_pairs = [p for p in train_pairs if p["cluster"] == cluster]
        sources = [_pair_data(p)[0] for p in cluster_pairs]
        targets = [_pair_data(p)[1] for p in cluster_pairs]
        by_cluster[cluster] = fit_color_matrix(sources, targets, ridge=MATRIX_RIDGE)
    return by_cluster


def fit_chroma_lut_params(train_pairs, matrices):
    """클러스터별 (sat_mult, hue_shift_deg) 그리드서치 - 매트릭스 +
    chroma LUT + 공유 필름커브까지 다 적용한 뒤 타깃과의 평균
    ΔE(CIEDE2000)가 최소인 조합을 그 클러스터의 학습 페어 평균으로
    고른다."""
    by_cluster = {}
    for cluster, matrix in matrices.items():
        cluster_pairs = [p for p in train_pairs if p["cluster"] == cluster]
        best_params, best_de = (1.0, 0.0), float("inf")
        for sat_mult, hue_shift_deg in itertools.product(SAT_MULT_GRID, HUE_SHIFT_GRID):
            des = []
            for p in cluster_pairs:
                wb_rgb, target = _pair_data(p)
                matrixed = apply_color_matrix(wb_rgb, matrix)
                chroma_applied = apply_chroma_lut(matrixed, sat_mult, hue_shift_deg)
                result = film_curve(chroma_applied, toe_lift=FILM_CURVE_TOE_LIFT,
                                     shoulder_start=FILM_CURVE_SHOULDER_START,
                                     white_point=FILM_CURVE_WHITE_POINT)
                des.append(mean_delta_e(result, target))
            mean_de = float(np.mean(des))
            if mean_de < best_de:
                best_de, best_params = mean_de, (sat_mult, hue_shift_deg)
        by_cluster[cluster] = best_params
    return by_cluster


def structural_delta_e(test_pair, matrices, chroma_lut_params):
    wb_rgb, target = _pair_data(test_pair)
    cluster = test_pair["cluster"]
    matrixed = apply_color_matrix(wb_rgb, matrices[cluster])
    sat_mult, hue_shift_deg = chroma_lut_params[cluster]
    chroma_applied = apply_chroma_lut(matrixed, sat_mult, hue_shift_deg)
    result = film_curve(chroma_applied, toe_lift=FILM_CURVE_TOE_LIFT,
                         shoulder_start=FILM_CURVE_SHOULDER_START,
                         white_point=FILM_CURVE_WHITE_POINT)
    return mean_delta_e(result, target)


def _linear_to_uint8_bgr(rgb_linear):
    clipped = np.clip(rgb_linear, 0.0, 1.0)
    encoded = colour.cctf_encoding(clipped, function="sRGB")
    u8 = (np.clip(encoded, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    return u8[:, :, ::-1]


def _uint8_bgr_to_linear(bgr_uint8):
    rgb = bgr_uint8[:, :, ::-1].astype(np.float64) / 255.0
    return colour.cctf_decoding(rgb, function="sRGB")


def apply_hncs_delta_e(test_pair):
    """공정 비교: apply_hncs()도 같은 raw 기반 baseline(decode_raw())에
    적용해서 같은 13쌍 target에 대해 ΔE를 잰다 - 기존 v8~v12 이력의
    RMSE 23.3은 다른 표본/다른 측정 방식이라 그대로 갖다 쓰지 않고 이
    실험 안에서 재측정한다."""
    baseline, target = _hncs_baseline_and_target(test_pair)
    bgr_uint8 = _linear_to_uint8_bgr(baseline)
    result_bgr = apply_hncs(bgr_uint8)
    result_linear = _uint8_bgr_to_linear(result_bgr)
    return mean_delta_e(result_linear, target)


def run_loocv():
    pairs = load_pairs()
    per_fold = []
    for i, held_out in enumerate(pairs):
        train = pairs[:i] + pairs[i + 1:]
        matrices = fit_matrices(train)
        chroma_params = fit_chroma_lut_params(train, matrices)
        de_structural = structural_delta_e(held_out, matrices, chroma_params)
        de_hncs = apply_hncs_delta_e(held_out)
        per_fold.append((held_out["name"], held_out["cluster"], de_structural, de_hncs))
        print(f"  [{held_out['name']}] cluster={held_out['cluster']} "
              f"structural ΔE={de_structural:.3f} apply_hncs ΔE={de_hncs:.3f}",
              flush=True)
    return per_fold


def _sign_test_p(wins, losses):
    """부호검정 양측 p값(정확 이항, 무승부 제외). scipy 의존 없이
    math.comb으로 직접 계산한다."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def summarize(per_fold, n_bootstrap=20000, seed=0):
    """폴드별 결과 -> 요약 통계 dict.

    평균 차이 하나로 승패를 선언하지 않는다: n=13짜리 페어드 비교에서
    평균 ΔE 차이는 폴드 간 산포에 비해 훨씬 작을 수 있어서, 부호검정,
    부트스트랩 신뢰구간, drop-one 민감도를 같이 낸 뒤 **0을 포함하면
    '판정 보류'**로 보고한다. 순수 함수라 기록된 폴드 결과만으로도
    재현할 수 있다(tests/test_evaluate_hncs_structural.py)."""
    structural = np.array([row[2] for row in per_fold], dtype=np.float64)
    hncs = np.array([row[3] for row in per_fold], dtype=np.float64)
    n = len(per_fold)
    diff = hncs - structural  # 양수 = 구조 실험이 그 폴드에서 더 좋음
    mean_structural = float(structural.mean())
    mean_hncs = float(hncs.mean())
    improvement_pct = (mean_hncs - mean_structural) / mean_hncs * 100.0

    wins = int((diff > 0).sum())
    losses = int((diff < 0).sum())
    sd_diff = float(diff.std(ddof=1)) if n > 1 else 0.0
    sem_diff = sd_diff / math.sqrt(n) if n > 1 else 0.0
    t_stat = float(diff.mean() / sem_diff) if sem_diff > 0 else 0.0

    rng = np.random.default_rng(seed)
    boot_diff, boot_pct = [], []
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, n)
        boot_diff.append(float(diff[idx].mean()))
        boot_pct.append(float((hncs[idx].mean() - structural[idx].mean())
                              / hncs[idx].mean() * 100.0))
    ci_diff = tuple(float(v) for v in np.percentile(boot_diff, [2.5, 97.5]))
    ci_pct = tuple(float(v) for v in np.percentile(boot_pct, [2.5, 97.5]))

    dropone = []
    for i in range(n):
        keep = np.ones(n, dtype=bool)
        keep[i] = False
        dropone.append(float((hncs[keep].mean() - structural[keep].mean())
                             / hncs[keep].mean() * 100.0))

    inconclusive = ci_diff[0] <= 0.0 <= ci_diff[1]
    if inconclusive:
        verdict = ("판정 보류 - 평균 차이가 0과 구분되지 않는다"
                   "(95% 부트스트랩 CI가 0을 포함)")
    elif improvement_pct > 0:
        verdict = "구조적 실험이 이겼다"
    else:
        verdict = "apply_hncs()가 더 낫다"

    return {
        "n": n,
        "mean_structural": mean_structural,
        "mean_hncs": mean_hncs,
        "mean_diff": float(diff.mean()),
        "median_diff": float(np.median(diff)),
        "improvement_pct": improvement_pct,
        "structural_wins": wins,
        "hncs_wins": losses,
        "sd_diff": sd_diff,
        "sem_diff": sem_diff,
        "t_stat": t_stat,
        "sign_test_p": _sign_test_p(wins, losses),
        "ci_diff": ci_diff,
        "ci_pct": ci_pct,
        "dropone_pct_min": min(dropone),
        "dropone_pct_max": max(dropone),
        "dropone_flips_sign": min(dropone) <= 0.0 <= max(dropone),
        "inconclusive": inconclusive,
        "verdict": verdict,
    }


def print_summary(s):
    print()
    print(f"평균 structural ΔE (CIEDE2000, n={s['n']}): {s['mean_structural']:.3f}")
    print(f"평균 apply_hncs ΔE (CIEDE2000, n={s['n']}): {s['mean_hncs']:.3f}")
    print(f"개선폭: {s['improvement_pct']:.1f}%")
    print(f"폴드 승패: 구조 실험 {s['structural_wins']}승 {s['hncs_wins']}패")
    print(f"페어드 차이: 평균 {s['mean_diff']:+.3f} / 중앙값 "
          f"{s['median_diff']:+.3f} / 표준편차 {s['sd_diff']:.3f} "
          f"(t={s['t_stat']:.2f}, df={s['n'] - 1})")
    print(f"부호검정 양측 p = {s['sign_test_p']:.3f}")
    print(f"부트스트랩 95% CI - 평균 ΔE 차이: "
          f"[{s['ci_diff'][0]:+.3f}, {s['ci_diff'][1]:+.3f}] / "
          f"개선폭: [{s['ci_pct'][0]:+.1f}%, {s['ci_pct'][1]:+.1f}%]")
    print(f"drop-one 민감도: 한 쌍을 빼면 개선폭이 "
          f"{s['dropone_pct_min']:.1f}% ~ {s['dropone_pct_max']:.1f}% 사이로 움직인다"
          + (" (부호가 뒤집힌다)" if s["dropone_flips_sign"] else ""))
    print(f"판정: {s['verdict']}")


def main():
    per_fold = run_loocv()
    print_summary(summarize(per_fold))


if __name__ == "__main__":
    main()
