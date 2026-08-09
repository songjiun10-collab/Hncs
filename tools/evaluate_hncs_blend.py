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
기록된 74개 폴드 값(2026-08, 공식 13 + 로컬 기여 61 재실행분)을
HARD_CLUSTER_DE 상수로 그대로 가져와 쓴다.

매트릭스/chroma LUT 둘 다 **가중 최소자승**으로 피팅한다: 74쌍 전부가
두 앵커(A/B) 피팅에 다 기여하되, 각 페어의 블렌딩 가중치가 그대로
그 페어의 기여도가 된다 - 기존 하드-클러스터 버전에서 소수 클러스터
(cluster_b)의 매트릭스가 사실상 학습쌍 몇 개로만 피팅되던 문제를
근본적으로 해결한다.

**74쌍으로 확장하며 추가한 병렬화(2026-08)**: `fit_weighted_chroma_lut()`의
49콤보 그리드서치가 폴드(74) x 가중치공식(rb/cct) 두 번 반복되면
단일 스레드로 감당이 안 되는 시간이 걸린다(추정 10시간 안팎). 콤보
단위로 프로세스 풀에 분산한다(evaluate_hncs_structural.py와 동일한
"워커가 시작할 때 전체 페어를 한 번씩 디코드해 로컬 캐시를 채워둔다"
패턴). 블렌딩 가중치도 폴드마다/콤보마다 다시 계산하지 않도록
`compute_weights_by_name()`으로 페어당 한 번만 구해 dict로 넘긴다
(원래도 폴드당 재계산이었지 콤보와는 무관한 값이라 이 캐싱은 순수
속도 최적화 - 계산 결과는 바뀌지 않는다).
"""
import argparse
import csv
import glob
import itertools
import math
import multiprocessing as mp
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
from hybrid_engine.utils.pairs import combine_pairs

N_WORKERS = max(1, min(3, (os.cpu_count() or 3) - 2))  # 16GB 메모리에서 워커당 페어 전체 캐시(~1.3GB)를 감당할 만큼만

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

# tools/evaluate_hncs_structural.py의 2026-08 74쌍(공식 13 + 로컬 기여
# 61) 재실행 결과에서 그대로 옮겨적은 하드-클러스터 구조 실험의 실측
# ΔE(재실행 안 함). 이전엔 공식 13쌍만 있어서 로컬 페어가 held-out으로
# 걸리면 KeyError가 났다.
HARD_CLUSTER_DE = {
    "x1d-II-sample-02.jpg": 11.587,
    "x1d-II-sample-09.jpg": 17.884,
    "B0000994.jpg": 14.709,
    "B0001395.jpg": 17.294,
    "x1d-xcd45-01.jpg": 12.580,
    "x1d-xcd45-03.jpg": 6.912,
    "x1d-xcd45-04.jpg": 4.654,
    "x1d-ii-xcd45p-01.jpg": 8.589,
    "x1d-ii-xcd45p-02.jpg": 10.575,
    "x1d-II-sample-01.jpg": 8.588,
    "x1d-II-sample-06.jpg": 14.069,
    "02709.jpg": 14.487,
    "00378.jpg": 5.558,
    "local-mixed-2026-07__6507810936": 8.607,
    "local-mixed-2026-07__0149725587": 6.327,
    "local-mixed-2026-07__8204307982": 6.941,
    "local-mixed-2026-07__3832345792": 8.458,
    "local-mixed-2026-07__5537240075": 7.599,
    "local-mixed-2026-07__0587181218": 5.840,
    "local-mixed-2026-07__7971015535": 5.763,
    "local-mixed-2026-07__6311094775": 5.144,
    "local-mixed-2026-07__6787000086": 12.546,
    "local-mixed-2026-07__7826992126": 5.898,
    "local-mixed-2026-07__5533274085": 4.597,
    "local-mixed-2026-07__1094220000": 6.607,
    "local-mixed-2026-07__8082395282": 7.480,
    "local-mixed-2026-07__1932636179": 6.098,
    "local-mixed-2026-07__3953661245": 5.921,
    "local-mixed-2026-07__8127122405": 5.846,
    "local-mixed-2026-07__5746737497": 8.995,
    "local-mixed-2026-07__9515423899": 7.915,
    "local-mixed-2026-07__6454535758": 9.402,
    "local-mixed-2026-07__8742913299": 6.527,
    "local-mixed-2026-07__7492975828": 5.219,
    "local-mixed-2026-07__7321006825": 11.814,
    "local-mixed-2026-07__6660888354": 33.718,
    "local-mixed-2026-07__4236625428": 6.285,
    "local-mixed-2026-07__8581844385": 14.510,
    "local-mixed-2026-07__7121592185": 12.170,
    "local-mixed-2026-07__3766372330": 8.209,
    "local-mixed-2026-07__7732046028": 4.795,
    "local-mixed-2026-07__0908944042": 5.514,
    "local-mixed-2026-07__1917191504": 4.922,
    "local-mixed-2026-07__9011626130": 12.049,
    "local-mixed-2026-07__5310704161": 22.590,
    "local-mixed-2026-07__3683076943": 8.212,
    "local-mixed-2026-07__7406451876": 5.852,
    "local-mixed-2026-07__6519755969": 4.820,
    "local-mixed-2026-07__3333340029": 10.758,
    "local-mixed-2026-07__9479682988": 8.227,
    "local-mixed-2026-07__5385314660": 12.598,
    "local-mixed-2026-07__9247740424": 4.806,
    "local-mixed-2026-07__5715595764": 9.708,
    "local-mixed-2026-07__6704898202": 15.312,
    "local-mixed-2026-07__6340134840": 5.114,
    "local-mixed-2026-07__9928856380": 4.369,
    "local-mixed-2026-07__0758706524": 4.351,
    "local-mixed-2026-07__4087418227": 4.684,
    "local-mixed-2026-07__1063588653": 5.330,
    "local-mixed-2026-07__1755788551": 36.934,
    "local-mixed-2026-07__9070200412": 6.551,
    "local-mixed-2026-07__9318140329": 6.806,
    "local-mixed-2026-07__4589763049": 12.054,
    "local-mixed-2026-07__0229019868": 23.267,
    "local-mixed-2026-07__9063680763": 17.887,
    "local-mixed-2026-07__0550549226": 5.074,
    "local-mixed-2026-07__3153320186": 7.105,
    "local-mixed-2026-07__6762931572": 9.219,
    "local-mixed-2026-07__6661213999": 12.155,
    "local-mixed-2026-07__5983653715": 11.781,
    "local-mixed-2026-07__1372685658": 9.451,
    "local-mixed-2026-07__3528755502": 6.257,
    "local-mixed-2026-07__7278483295": 27.887,
    "local-mixed-2026-07__8647104982": 8.939,
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
        wb_rgb = _resize_max_dim(decode_and_white_balance(pair["raw_path"], half_size=True),
                                  DOWNSAMPLE_MAX_DIM)
        target = load_image_linear(pair["target_path"], resize_to=wb_rgb.shape[:2])
        _PAIR_DATA_CACHE[name] = (wb_rgb, target)
    return _PAIR_DATA_CACHE[name]


def _init_worker(pairs):
    """풀 워커 시작 시 한 번만 실행 - 전체 페어를 디코드해 이 워커의
    _PAIR_DATA_CACHE를 채워둔다(이후 모든 폴드x콤보 태스크가 재디코드
    없이 이 캐시를 쓴다)."""
    for p in pairs:
        _pair_data(p)


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


def compute_weights_by_name(pairs, weight_fn, bounds):
    """페어별 블렌딩 가중치를 한 번만 계산해 name -> weight dict로 반환.
    weight_fn(p, bounds)는 매 호출마다 exiftool 서브프로세스를 띄워
    AsShotNeutral을 다시 읽는데, 그 값은 폴드/콤보와 무관하므로 폴드마다
    (게다가 그리드서치 콤보마다) 다시 부르면 낭비다. 74쌍으로 늘면서
    이 낭비가 무시할 수 없어져 페어당 1회로 캐시한다(계산 결과는
    이전과 동일)."""
    return {p["name"]: weight_fn(p, bounds) for p in pairs}


def fit_weighted_matrices(train_pairs, weights):
    """train_pairs 전부가 매트릭스 A/B 피팅 둘 다에 기여(가중 최소자승)
    - 각 페어의 블렌딩 가중치가 그대로 그 페어의 피팅 기여도가 된다.

    weights의 값이 [0,1] 밖일 수도 있다(compute_blend_weight_*는 관측
    범위 밖 값에 대해 의도적으로 외삽을 허용) - 여기서는 [0,1]로
    clip한다. 피팅 가중치가 음수면 fit_color_matrix() 내부의
    sqrt(weight)가 NaN이 되어(예외 없이 RuntimeWarning만 내고 조용히
    깨진 매트릭스를 반환) 디버깅하기 어려운 실패를 만들기 때문 - 이
    실험(bounds가 전체 population min/max라 모든 페어의 가중치가 항상
    [0,1] 안)에서는 실제로 발동하지 않지만, 이 함수를 다른 bounds로
    재사용할 미래 호출부를 위한 방어."""
    weights_b = [min(1.0, max(0.0, weights[p["name"]])) for p in train_pairs]
    sources = [_pair_data(p)[0] for p in train_pairs]
    targets = [_pair_data(p)[1] for p in train_pairs]
    w_a = [np.full(s.shape[:2], 1.0 - w) for s, w in zip(sources, weights_b)]
    w_b = [np.full(s.shape[:2], w) for s, w in zip(sources, weights_b)]
    matrix_a = fit_color_matrix(sources, targets, weights=w_a, ridge=MATRIX_RIDGE)
    matrix_b = fit_color_matrix(sources, targets, weights=w_b, ridge=MATRIX_RIDGE)
    return matrix_a, matrix_b


def _blend_combo_mean(names, weights, matrix_a, matrix_b, sat_mult, hue_shift_deg,
                       kL=1.0, kC=1.0, kH=1.0):
    sum_a, total_a, sum_b, total_b = 0.0, 0.0, 0.0, 0.0
    for name in names:
        w = weights[name]
        wb_rgb, target = _PAIR_DATA_CACHE[name]
        blended_matrix = (1.0 - w) * matrix_a + w * matrix_b
        matrixed = apply_color_matrix(wb_rgb, blended_matrix)
        chroma_applied = apply_chroma_lut(matrixed, sat_mult, hue_shift_deg)
        result = film_curve(chroma_applied, toe_lift=FILM_CURVE_TOE_LIFT,
                             shoulder_start=FILM_CURVE_SHOULDER_START,
                             white_point=FILM_CURVE_WHITE_POINT)
        de = mean_delta_e(result, target, kL=kL, kC=kC, kH=kH)
        sum_a += (1.0 - w) * de
        total_a += (1.0 - w)
        sum_b += w * de
        total_b += w
    return sum_a, total_a, sum_b, total_b


def _blend_combo_task(args):
    names, weights, matrix_a, matrix_b, sat_mult, hue_shift_deg, kL, kC, kH = args
    sum_a, total_a, sum_b, total_b = _blend_combo_mean(
        names, weights, matrix_a, matrix_b, sat_mult, hue_shift_deg, kL, kC, kH)
    return (sat_mult, hue_shift_deg), sum_a, total_a, sum_b, total_b


def fit_weighted_chroma_lut(train_pairs, weights, matrix_a, matrix_b, pool=None,
                             kL=1.0, kC=1.0, kH=1.0):
    """앵커A/B용 (sat_mult, hue_shift_deg)를 각각 가중 평균 ΔE 최소화로
    그리드서치. 매트릭스는 이미 그 폴드에서 피팅된 blended matrix(각
    페어 자기 가중치로 블렌딩)를 먼저 적용한 뒤 후보 chroma 파라미터를
    얹어 평가한다 - apply_hncs_structural_blend()가 예측 시 실제로
    하는 순서와 일치시키기 위함. pool이 있으면 49개 콤보를 워커들에
    나눠 계산한다(결과는 직렬 실행과 수학적으로 동일). kL/kC/kH는
    이 그리드서치의 선택 기준 자체를 바꾼다 - 기본(1,1,1)에서 벗어나면
    최적 (sat_mult, hue_shift_deg)도 달라질 수 있다."""
    names = [p["name"] for p in train_pairs]
    combos = list(itertools.product(SAT_MULT_GRID, HUE_SHIFT_GRID))
    if pool is None:
        results = [((s, h), *_blend_combo_mean(names, weights, matrix_a, matrix_b, s, h,
                                                 kL, kC, kH))
                   for s, h in combos]
    else:
        tasks = [(names, weights, matrix_a, matrix_b, s, h, kL, kC, kH) for s, h in combos]
        results = pool.map(_blend_combo_task, tasks)

    best_a, best_a_score = (1.0, 0.0), float("inf")
    best_b, best_b_score = (1.0, 0.0), float("inf")
    for combo, sum_a, total_a, sum_b, total_b in results:
        if total_a > 0:
            score_a = sum_a / total_a
            if score_a < best_a_score:
                best_a_score, best_a = score_a, combo
        if total_b > 0:
            score_b = sum_b / total_b
            if score_b < best_b_score:
                best_b_score, best_b = score_b, combo
    return best_a, best_b


def run_loocv(weight_fn_name, pool=None, kL=1.0, kC=1.0, kH=1.0):
    """weight_fn_name: "rb" 또는 "cct". 74개 폴드 전부에 대해
    (name, de_hard, de_blend, weight) 튜플 리스트를 반환한다. kL/kC/kH가
    (1,1,1)이 아니면 de_hard는 None이다 - HARD_CLUSTER_DE는 (1,1,1)
    기준으로 측정된 상수라 다른 가중치에서는 안 맞다(사용하려면
    evaluate_hncs_structural.py를 그 가중치로 다시 돌려야 하는데, 그
    스크립트는 이 환경에서 실행 불가 - docs/superpowers/specs/2026-08-09-ciede2000-weighted-reverification-design.md
    참고)."""
    pairs = combine_pairs(load_pairs())
    bounds = compute_population_bounds(pairs)
    weight_fn = pair_weight_rb if weight_fn_name == "rb" else pair_weight_cct
    weights = compute_weights_by_name(pairs, weight_fn, bounds)
    is_weighted = (kL, kC, kH) != (1.0, 1.0, 1.0)

    per_fold = []
    for i, held_out in enumerate(pairs):
        train = pairs[:i] + pairs[i + 1:]
        matrix_a, matrix_b = fit_weighted_matrices(train, weights)
        chroma_a, chroma_b = fit_weighted_chroma_lut(train, weights, matrix_a, matrix_b, pool,
                                                       kL, kC, kH)

        w_held = weights[held_out["name"]]
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
        de_blend = mean_delta_e(result, target, kL=kL, kC=kC, kH=kH)
        de_hard = None if is_weighted else HARD_CLUSTER_DE[held_out["name"]]

        per_fold.append((held_out["name"], de_hard, de_blend, w_held))
        hard_str = "N/A(가중 모드)" if is_weighted else f"{de_hard:.3f}"
        print(f"  [{held_out['name']}] hard-cluster ΔE={hard_str} "
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kl", type=float, default=1.0, help="CIEDE2000 kL 가중치 (기본 1.0)")
    parser.add_argument("--kc", type=float, default=1.0, help="CIEDE2000 kC 가중치 (기본 1.0)")
    parser.add_argument("--kh", type=float, default=1.0, help="CIEDE2000 kH 가중치 (기본 1.0)")
    args = parser.parse_args()
    kL, kC, kH = args.kl, args.kc, args.kh
    is_weighted = (kL, kC, kH) != (1.0, 1.0, 1.0)

    pairs = combine_pairs(load_pairs())
    print(f"페어 {len(pairs)}개 - 디코드 캐시 준비 중(메인 프로세스)", flush=True)
    _init_worker(pairs)  # 메인 프로세스도 fit_weighted_matrices()/held-out 평가용으로 필요
    pool = mp.Pool(processes=N_WORKERS, initializer=_init_worker, initargs=(pairs,)) \
        if N_WORKERS > 1 else None
    if pool is not None:
        print(f"워커 {N_WORKERS}개에 디코드 캐시 배포 중 (RB/CCT 두 실행이 공유)", flush=True)
    try:
        if is_weighted:
            print(f"=== 가중 모드 (kL={kL}, kC={kC}, kH={kH}) - 하드클러스터 비교 생략 ===")
        else:
            print("=== R/B 선형 블렌딩 vs 하드-클러스터 ===")
        per_fold_rb = run_loocv("rb", pool, kL, kC, kH)
        if not is_weighted:
            summary_rb = summarize(per_fold_rb)
            print_summary(summary_rb, label_a="하드클러스터", label_b="RB블렌딩")

        print()
        if not is_weighted:
            print("=== CCT/mired 블렌딩 vs 하드-클러스터 ===")
        per_fold_cct = run_loocv("cct", pool, kL, kC, kH)
        if not is_weighted:
            summary_cct = summarize(per_fold_cct)
            print_summary(summary_cct, label_a="하드클러스터", label_b="CCT블렌딩")
    finally:
        if pool is not None:
            pool.close()
            pool.join()

    print()
    print("=== RB블렌딩 vs CCT블렌딩 직접 비교 ===")
    per_fold_direct = [(r[0], r[2], c[2]) for r, c in zip(per_fold_rb, per_fold_cct)]
    summary_direct = summarize(per_fold_direct)
    print_summary(summary_direct, label_a="RB블렌딩", label_b="CCT블렌딩")


if __name__ == "__main__":
    main()
