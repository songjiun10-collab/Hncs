"""HNCS 조명 블렌딩(illuminant blend) 실험 - hncs_structural.py의
하드-클러스터 구조 실험(cluster_a/cluster_b 하드 분류)을, 연속
블렌딩(Lightroom dual-illuminant DCP 방식과 유사, Luminous Landscape
포럼의 HNCS 메커니즘 분석이 시사하는 실제 구조)으로 바꾸면 ΔE가
낮아지는지 leave-one-out 교차검증으로 확인한다. 설계 근거:
docs/superpowers/specs/2026-07-31-hncs-illuminant-blend-design.md

  python3 -m tools.evaluate_hncs_blend

두 가지 블렌딩 가중치 공식(R/B 비율 선형, CCT/mired)을 각각 독립적으로
평가하고, 마지막에 둘을 직접 비교한다. 하드-클러스터 쪽은 재실행하지
않는다 - hybrid_engine/EVALUATION.md의 "HNCS 구조 실험" 절에 이미
기록된 13개 폴드 값을 HARD_CLUSTER_DE 상수로 그대로 가져와 쓴다.

매트릭스/chroma LUT 둘 다 **가중 최소자승**으로 피팅한다: 13쌍 전부가
두 앵커(A/B) 피팅에 다 기여하되, 각 페어의 블렌딩 가중치가 그대로
그 페어의 기여도가 된다 - 기존 하드-클러스터 버전에서 소수 클러스터
(cluster_b, 3쌍뿐)의 매트릭스가 사실상 2쌍(LOO 기준)으로만 피팅되던
문제를 근본적으로 해결한다.
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

from core.curve import film_curve
from hybrid_engine.core.raw_baseline import apply_color_matrix, fit_color_matrix
from hybrid_engine.research.hncs_structural import (
    apply_chroma_lut, compute_blend_weight_cct, compute_blend_weight_rb,
    decode_and_white_balance,
)
from hybrid_engine.utils.evaluate import mean_delta_e
from hybrid_engine.utils.exif import read_as_shot_neutral
from hybrid_engine.utils.io import load_image_linear

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(_ROOT, "raw_calib_cache")
CSV_PATH = os.path.join(_ROOT, "datasets", "hasselblad", "hasselblad_raw_jpeg_pairs.csv")

_SRGB = colour.RGB_COLOURSPACES["sRGB"]

SAT_MULT_GRID = [0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15]
HUE_SHIFT_GRID = [-6.0, -4.0, -2.0, 0.0, 2.0, 4.0, 6.0]
MATRIX_RIDGE = 1.0

FILM_CURVE_TOE_LIFT = 0.001
FILM_CURVE_SHOULDER_START = 0.78
FILM_CURVE_WHITE_POINT = 1.0

DOWNSAMPLE_MAX_DIM = 512

# hybrid_engine/EVALUATION.md "HNCS 구조 실험" 절, "폴드별 상세" 표에서
# 그대로 옮겨적은 하드-클러스터 구조 실험의 실측 ΔE(재실행 안 함).
HARD_CLUSTER_DE = {
    "x1d-II-sample-02.jpg": 10.787,
    "x1d-II-sample-09.jpg": 5.249,
    "B0000994.jpg": 14.223,
    "B0001395.jpg": 18.412,
    "x1d-xcd45-01.jpg": 13.194,
    "x1d-xcd45-03.jpg": 8.342,
    "x1d-xcd45-04.jpg": 4.729,
    "x1d-ii-xcd45p-01.jpg": 10.126,
    "x1d-ii-xcd45p-02.jpg": 11.055,
    "x1d-II-sample-01.jpg": 6.452,
    "x1d-II-sample-06.jpg": 11.726,
    "02709.jpg": 13.074,
    "00378.jpg": 5.115,
}

_PAIR_DATA_CACHE = {}


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


def load_pairs(csv_path=CSV_PATH, cache_dir=CACHE_DIR):
    """CSV의 jpeg_url basename 13개를 읽어 raw/target 경로와 함께
    dict 리스트로 반환."""
    pairs = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            name = os.path.basename(row["jpeg_url"])
            matches = [m for m in glob.glob(os.path.join(cache_dir, name + ".*"))
                       if not m.endswith(".target.jpg")]
            if len(matches) != 1:
                raise FileNotFoundError(f"raw for {name}: expected 1 match, got {matches}")
            pairs.append({
                "name": name,
                "raw_path": matches[0],
                "target_path": os.path.join(cache_dir, name + ".target.jpg"),
            })
    return pairs


def _pair_data(pair):
    """(디코드+WB+축소본, 축소된 타깃) - 페어명으로 캐시. 두 가중치
    방식(rb/cct) 모두 같은 캐시를 공유한다(디코드는 가중치 공식과
    무관)."""
    name = pair["name"]
    if name not in _PAIR_DATA_CACHE:
        wb_rgb = _resize_max_dim(decode_and_white_balance(pair["raw_path"]),
                                  DOWNSAMPLE_MAX_DIM)
        target = load_image_linear(pair["target_path"], resize_to=wb_rgb.shape[:2])
        _PAIR_DATA_CACHE[name] = (wb_rgb, target)
    return _PAIR_DATA_CACHE[name]


def _cct_mired(as_shot_neutral):
    rgb = np.array(as_shot_neutral[:3], dtype=np.float64)
    xyz = colour.RGB_to_XYZ(rgb, _SRGB, apply_cctf_decoding=False)
    xy = colour.XYZ_to_xy(xyz)
    cct = colour.temperature.xy_to_CCT(xy, method="McCamy 1992")
    return 1e6 / cct


def compute_population_bounds(pairs):
    """13쌍 전체에서 R/B 비율과 CCT(mired) 최솟값/최댓값을 한 번만
    계산 - LOO 폴드마다 다시 계산하지 않는다(정규화 범위가 폴드별로
    흔들리면 폴드 간 비교가 무의미해짐)."""
    r_over_bs, mireds = [], []
    for p in pairs:
        asn = read_as_shot_neutral(p["raw_path"])
        r_over_bs.append(asn[0] / asn[2])
        mireds.append(_cct_mired(asn))
    return {
        "rb_min": min(r_over_bs), "rb_max": max(r_over_bs),
        "mired_min": min(mireds), "mired_max": max(mireds),
    }


def pair_weight_rb(pair, bounds):
    asn = read_as_shot_neutral(pair["raw_path"])
    return compute_blend_weight_rb(asn, bounds["rb_min"], bounds["rb_max"])


def pair_weight_cct(pair, bounds):
    asn = read_as_shot_neutral(pair["raw_path"])
    return compute_blend_weight_cct(asn, bounds["mired_min"], bounds["mired_max"])


def fit_weighted_matrices(train_pairs, weight_fn, bounds):
    """train_pairs 전부가 매트릭스 A/B 피팅 둘 다에 기여(가중 최소자승)
    - 각 페어의 블렌딩 가중치가 그대로 그 페어의 피팅 기여도가 된다.

    weight_fn이 [0,1] 밖의 값을 낼 수도 있다(compute_blend_weight_*는
    관측 범위 밖 값에 대해 의도적으로 외삽을 허용) - 여기서는 [0,1]로
    clip한다. 피팅 가중치가 음수면 fit_color_matrix() 내부의
    sqrt(weight)가 NaN이 되어(예외 없이 RuntimeWarning만 내고 조용히
    깨진 매트릭스를 반환) 디버깅하기 어려운 실패를 만들기 때문 - 이
    실험(bounds가 13쌍 전체 population min/max라 모든 페어의 가중치가
    항상 [0,1] 안)에서는 실제로 발동하지 않지만, 이 함수를 다른
    bounds로 재사용할 미래 호출부를 위한 방어."""
    weights_b = [min(1.0, max(0.0, weight_fn(p, bounds))) for p in train_pairs]
    sources = [_pair_data(p)[0] for p in train_pairs]
    targets = [_pair_data(p)[1] for p in train_pairs]
    w_a = [np.full(s.shape[:2], 1.0 - w) for s, w in zip(sources, weights_b)]
    w_b = [np.full(s.shape[:2], w) for s, w in zip(sources, weights_b)]
    matrix_a = fit_color_matrix(sources, targets, weights=w_a, ridge=MATRIX_RIDGE)
    matrix_b = fit_color_matrix(sources, targets, weights=w_b, ridge=MATRIX_RIDGE)
    return matrix_a, matrix_b


def fit_weighted_chroma_lut(train_pairs, weight_fn, bounds, matrix_a, matrix_b):
    """앵커A/B용 (sat_mult, hue_shift_deg)를 각각 가중 평균 ΔE 최소화로
    그리드서치. 매트릭스는 이미 그 폴드에서 피팅된 blended matrix(각
    페어 자기 가중치로 블렌딩)를 먼저 적용한 뒤 후보 chroma 파라미터를
    얹어 평가한다 - apply_hncs_structural_blend()가 예측 시 실제로
    하는 순서와 일치시키기 위함."""
    entries = []
    for p in train_pairs:
        w = weight_fn(p, bounds)
        wb_rgb, target = _pair_data(p)
        blended_matrix = (1.0 - w) * matrix_a + w * matrix_b
        matrixed = apply_color_matrix(wb_rgb, blended_matrix)
        entries.append((w, matrixed, target))

    best_a, best_a_score = (1.0, 0.0), float("inf")
    best_b, best_b_score = (1.0, 0.0), float("inf")
    for sat_mult, hue_shift_deg in itertools.product(SAT_MULT_GRID, HUE_SHIFT_GRID):
        sum_a, total_a, sum_b, total_b = 0.0, 0.0, 0.0, 0.0
        for w, matrixed, target in entries:
            chroma_applied = apply_chroma_lut(matrixed, sat_mult, hue_shift_deg)
            result = film_curve(chroma_applied, toe_lift=FILM_CURVE_TOE_LIFT,
                                 shoulder_start=FILM_CURVE_SHOULDER_START,
                                 white_point=FILM_CURVE_WHITE_POINT)
            de = mean_delta_e(result, target)
            sum_a += (1.0 - w) * de
            total_a += (1.0 - w)
            sum_b += w * de
            total_b += w
        if total_a > 0:
            score_a = sum_a / total_a
            if score_a < best_a_score:
                best_a_score, best_a = score_a, (sat_mult, hue_shift_deg)
        if total_b > 0:
            score_b = sum_b / total_b
            if score_b < best_b_score:
                best_b_score, best_b = score_b, (sat_mult, hue_shift_deg)
    return best_a, best_b


def run_loocv(weight_fn_name):
    """weight_fn_name: "rb" 또는 "cct". 13개 폴드 전부에 대해
    (name, de_hard, de_blend, weight) 튜플 리스트를 반환한다."""
    pairs = load_pairs()
    bounds = compute_population_bounds(pairs)
    weight_fn = pair_weight_rb if weight_fn_name == "rb" else pair_weight_cct

    per_fold = []
    for i, held_out in enumerate(pairs):
        train = pairs[:i] + pairs[i + 1:]
        matrix_a, matrix_b = fit_weighted_matrices(train, weight_fn, bounds)
        chroma_a, chroma_b = fit_weighted_chroma_lut(train, weight_fn, bounds,
                                                       matrix_a, matrix_b)

        w_held = weight_fn(held_out, bounds)
        wb_rgb, target = _pair_data(held_out)
        blended_matrix = (1.0 - w_held) * matrix_a + w_held * matrix_b
        matrixed = apply_color_matrix(wb_rgb, blended_matrix)
        sat_a, hue_a = chroma_a
        sat_b, hue_b = chroma_b
        sat_mult = (1.0 - w_held) * sat_a + w_held * sat_b
        hue_shift_deg = (1.0 - w_held) * hue_a + w_held * hue_b
        chroma_applied = apply_chroma_lut(matrixed, sat_mult, hue_shift_deg)
        result = film_curve(chroma_applied, toe_lift=FILM_CURVE_TOE_LIFT,
                             shoulder_start=FILM_CURVE_SHOULDER_START,
                             white_point=FILM_CURVE_WHITE_POINT)
        de_blend = mean_delta_e(result, target)
        de_hard = HARD_CLUSTER_DE[held_out["name"]]

        per_fold.append((held_out["name"], de_hard, de_blend, w_held))
        print(f"  [{held_out['name']}] hard-cluster ΔE={de_hard:.3f} "
              f"blend({weight_fn_name}) ΔE={de_blend:.3f} "
              f"weight={w_held:.3f}", flush=True)
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
    """페어드 비교 통계. per_fold의 각 행은 (name, value_a, value_b, ...)
    형태(추가 필드는 무시) - value_a가 기준, value_b가 비교 대상이다.
    개선폭/verdict는 value_b가 value_a보다 작을 때(=b가 더 좋음, ΔE
    낮을수록 좋음) 양수가 되도록 정의한다. 평균 차이 하나로 승패를
    선언하지 않는다 - 부호검정, 부트스트랩 신뢰구간, drop-one 민감도를
    같이 내고 0을 포함하면 '판정 보류'로 보고한다."""
    a = np.array([row[1] for row in per_fold], dtype=np.float64)
    b = np.array([row[2] for row in per_fold], dtype=np.float64)
    n = len(per_fold)
    diff = a - b  # 양수 = b가 그 폴드에서 더 좋음(ΔE 감소)
    mean_a = float(a.mean())
    mean_b = float(b.mean())
    improvement_pct = (mean_a - mean_b) / mean_a * 100.0

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
        boot_pct.append(float((a[idx].mean() - b[idx].mean())
                              / a[idx].mean() * 100.0))
    ci_diff = tuple(float(v) for v in np.percentile(boot_diff, [2.5, 97.5]))
    ci_pct = tuple(float(v) for v in np.percentile(boot_pct, [2.5, 97.5]))

    dropone = []
    for i in range(n):
        keep = np.ones(n, dtype=bool)
        keep[i] = False
        dropone.append(float((a[keep].mean() - b[keep].mean())
                             / a[keep].mean() * 100.0))

    inconclusive = ci_diff[0] <= 0.0 <= ci_diff[1]
    if inconclusive:
        verdict = ("판정 보류 - 평균 차이가 0과 구분되지 않는다"
                   "(95% 부트스트랩 CI가 0을 포함)")
    elif improvement_pct > 0:
        verdict = "B가 이겼다"
    else:
        verdict = "A가 더 낫다"

    return {
        "n": n,
        "mean_a": mean_a,
        "mean_b": mean_b,
        "mean_diff": float(diff.mean()),
        "median_diff": float(np.median(diff)),
        "improvement_pct": improvement_pct,
        "b_wins": wins,
        "a_wins": losses,
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


def print_summary(s, label_a="A", label_b="B"):
    print()
    print(f"평균 {label_a} ΔE (CIEDE2000, n={s['n']}): {s['mean_a']:.3f}")
    print(f"평균 {label_b} ΔE (CIEDE2000, n={s['n']}): {s['mean_b']:.3f}")
    print(f"개선폭({label_b} 기준): {s['improvement_pct']:.1f}%")
    print(f"폴드 승패: {label_b} {s['b_wins']}승 {label_a} {s['a_wins']}패")
    print(f"페어드 차이({label_a}-{label_b}): 평균 {s['mean_diff']:+.3f} / 중앙값 "
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
    print("=== R/B 선형 블렌딩 vs 하드-클러스터 ===")
    per_fold_rb = run_loocv("rb")
    summary_rb = summarize(per_fold_rb)
    print_summary(summary_rb, label_a="하드클러스터", label_b="RB블렌딩")

    print()
    print("=== CCT/mired 블렌딩 vs 하드-클러스터 ===")
    per_fold_cct = run_loocv("cct")
    summary_cct = summarize(per_fold_cct)
    print_summary(summary_cct, label_a="하드클러스터", label_b="CCT블렌딩")

    print()
    print("=== RB블렌딩 vs CCT블렌딩 직접 비교 ===")
    per_fold_direct = [(r[0], r[2], c[2]) for r, c in zip(per_fold_rb, per_fold_cct)]
    summary_direct = summarize(per_fold_direct)
    print_summary(summary_direct, label_a="RB블렌딩", label_b="CCT블렌딩")


if __name__ == "__main__":
    main()
