"""
`tools/evaluate_empirical_tone_curve.py`가 찾아낸 "파라메트릭 film_curve
가정이 실제 카메라 커브와 안 맞는다"(특히 Sigma/Sony/후지 신규 프리셋
RMSE 26~46)는 문제를, 파라미터 3개짜리 곡선 대신 **256bin 학습 LUT**
(raw+jpeg 픽셀에서 직접 뽑은 비파라메트릭 매핑)으로 바꾸면 ΔE00이 실제로
줄어드는지 직접 검증한다 - hasselblad_learned.py의 "파라메트릭 vs 학습
LUT" 비교를 이 세션에서 채택한 함수 전체로 확장한 것.

방법: exposure_gamma(있으면) -> CLAHE까지는 기존 파이프라인과 동일하게
재현(`evaluate_empirical_tone_curve.py`와 같음), 그 뒤 file_curve 대신
256bin LUT을 픽셀수 가중평균으로 학습해서 적용. LOO는 페어별 bin 집계를
미리 캐시해두고 held-out 페어만 빼는 방식(톤커브 그리드서치 때와 동일
패턴) - 256bin이라도 표본 부족 bin은 선형보간으로 채운다.

  python3 -m tools.evaluate_learned_lut \
      --label "X2D II 100C" \
      --manifest datasets/hasselblad/dpreview_raw_jpeg_pairs_clean.csv \
      --raw-dir "/Users/songjiun/local-work" --model "X2D II 100C" \
      --exposure-gamma 0.6 --clahe-clip 1.25 \
      --toe-lift 0.02 --shoulder-start 0.58 --white-point 0.95
"""
import argparse
import csv
import math
import os
import sys

import colour
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.curve import film_curve
from core.validation import is_image_array_usable
from tools.calibrate import load_neutral_render

MAX_DIM = 250
N_BINS = 256
MIN_BIN_SAMPLES = 30  # 이 미만 표본인 bin은 표본 0개인 bin과 동일하게
# 취급해 보간으로 대체한다 - 소수 노이즈 픽셀 평균이 그대로 LUT에 박혀
# 비단조 튐(밴딩)을 만드는 문제 방지. 임계값 자체는 미검증(실측
# 데이터로 재검증 필요), 표본 부족 bin을 보간하는 기존 로직을 재사용.
# tools/fit_final_lut.py의 동일 가드와 값을 맞춤(tools/CLAUDE.md 관례상
# evaluate_*.py끼리도 서로 import 안 하고 각자 복사 유지).


def _resolve(raw_dirs, filename):
    for d in raw_dirs:
        p = os.path.join(d, filename)
        if os.path.exists(p):
            return p
    return None


def pre_curve_l(neutral_bgr, exposure_gamma, clahe_clip):
    lab = cv2.cvtColor(neutral_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    if exposure_gamma is not None and exposure_gamma != 1.0:
        x = np.arange(256, dtype=np.float32) / 255.0
        exp_lut = np.clip((x ** exposure_gamma) * 255, 0, 255).astype(np.uint8)
        l = cv2.LUT(l, exp_lut)
    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)
    return l, a, b


def bgr_u8_to_lab_l(bgr_u8):
    lab = cv2.cvtColor(bgr_u8, cv2.COLOR_BGR2LAB)
    return lab[:, :, 0]


def bgr_u8_to_linear(bgr_u8):
    rgb = bgr_u8[:, :, ::-1].astype(np.float64) / 255.0
    return colour.cctf_decoding(rgb, function="sRGB")


def load_target_linear(jpg_path, shape_hw):
    bgr = cv2.imread(jpg_path)
    bgr = cv2.resize(bgr, (shape_hw[1], shape_hw[0]), interpolation=cv2.INTER_AREA)
    return bgr_u8_to_linear(bgr)


def mean_delta_e(linear_a, linear_b):
    from skimage.color import rgb2lab, deltaE_ciede2000
    a = colour.cctf_encoding(np.clip(linear_a, 0.0, 1.0), function="sRGB")
    b = colour.cctf_encoding(np.clip(linear_b, 0.0, 1.0), function="sRGB")
    return float(np.mean(deltaE_ciede2000(rgb2lab(a), rgb2lab(b))))


def _sign_test_p(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def _build_lut(sum_target, sum_weight):
    lut = np.zeros(N_BINS)
    filled = sum_weight >= MIN_BIN_SAMPLES
    lut[filled] = sum_target[filled] / sum_weight[filled]
    domain = np.arange(N_BINS)
    if not filled.all():
        lut = np.interp(domain, domain[filled], lut[filled])
    return np.clip(lut, 0, 255).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--raw-dir", action="append", required=True, dest="raw_dirs")
    ap.add_argument("--model", action="append", dest="models", default=None)
    ap.add_argument("--film-mode", default=None)
    ap.add_argument("--exposure-gamma", type=float, default=None)
    ap.add_argument("--clahe-clip", type=float, default=1.25)
    ap.add_argument("--toe-lift", type=float, required=True)
    ap.add_argument("--shoulder-start", type=float, required=True)
    ap.add_argument("--white-point", type=float, required=True)
    ap.add_argument("--n-folds", type=int, default=None,
                     help="기본은 LOO(표본 수만큼). 5 등을 주면 k-fold로 낮춰서 재검증 - "
                          "LOO가 표본 늘수록 낙관적으로 보일 수 있다는 이 프로젝트 통계 관례상 체크")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.manifest)))
    if args.models:
        rows = [r for r in rows if r["model"] in args.models]
    if args.film_mode:
        rows = [r for r in rows if r.get("film_mode") == args.film_mode]
    print(f"{args.label} 후보 {len(rows)}개", flush=True)

    x = np.arange(256, dtype=np.float32) / 255.0
    param_lut = np.clip(film_curve(x, args.toe_lift, args.shoulder_start, args.white_point) * 255,
                         0, 255).astype(np.uint8)

    pairs = []
    for i, r in enumerate(rows):
        raw_path = _resolve(args.raw_dirs, r["raw_file"])
        jpg_path = _resolve(args.raw_dirs, r["jpeg_file"])
        if raw_path is None or jpg_path is None:
            continue
        try:
            neutral = load_neutral_render(raw_path, max_dim=MAX_DIM)
        except Exception as e:
            print(f"  [{i+1}/{len(rows)}] {r['raw_file']} 디코드 실패: {e}", flush=True)
            continue
        target_img = cv2.imread(jpg_path)
        if target_img is None or not is_image_array_usable(target_img):
            continue
        target_img = cv2.resize(target_img, (neutral.shape[1], neutral.shape[0]),
                                 interpolation=cv2.INTER_AREA)

        l, a, b = pre_curve_l(neutral, args.exposure_gamma, args.clahe_clip)
        tgt_l = bgr_u8_to_lab_l(target_img)
        target_lin = load_target_linear(jpg_path, neutral.shape[:2])

        # 파라메트릭(기존 채택 값) 후보 - 비교 기준
        param_l = cv2.LUT(l, param_lut)
        param_out = cv2.cvtColor(cv2.merge((param_l, a, b)), cv2.COLOR_LAB2BGR)
        param_de = mean_delta_e(bgr_u8_to_linear(param_out), target_lin)

        sum_target = np.zeros(N_BINS)
        sum_weight = np.zeros(N_BINS)
        np.add.at(sum_target, l.ravel(), tgt_l.ravel().astype(np.float64))
        np.add.at(sum_weight, l.ravel(), 1.0)

        pairs.append(dict(name=r["raw_file"], l=l, a=a, b=b, target_lin=target_lin,
                           param_de=param_de, sum_target=sum_target, sum_weight=sum_weight))
        print(f"  [{i+1}/{len(rows)}] {r['raw_file']} 등록 (파라메트릭 ΔE00={param_de:.3f})", flush=True)

    n = len(pairs)
    print(f"\n사용 가능한 페어: {n}개", flush=True)
    if n < 8:
        print("판정: 표본 8개 미만 - 중단", flush=True)
        return

    total_target = sum(p["sum_target"] for p in pairs)
    total_weight = sum(p["sum_weight"] for p in pairs)

    k = args.n_folds if args.n_folds else n
    k = min(k, n)
    rng = np.random.RandomState(0)
    order = rng.permutation(n)
    fold_groups = np.array_split(order, k)

    print(f"\n=== {k}-fold 검증(LOO={'예' if k==n else '아니오'}) ===", flush=True)
    lut_des = np.zeros(n)
    for fi, held_out_idx in enumerate(fold_groups):
        held_out = set(held_out_idx.tolist())
        train_target = total_target.copy()
        train_weight = total_weight.copy()
        for idx in held_out_idx:
            train_target -= pairs[idx]["sum_target"]
            train_weight -= pairs[idx]["sum_weight"]
        lut = _build_lut(train_target, train_weight)

        for idx in held_out_idx:
            p = pairs[idx]
            lut_l = cv2.LUT(p["l"], lut)
            out = cv2.cvtColor(cv2.merge((lut_l, p["a"], p["b"])), cv2.COLOR_LAB2BGR)
            de = mean_delta_e(bgr_u8_to_linear(out), p["target_lin"])
            lut_des[idx] = de
            print(f"  [폴드 {fi+1}/{k}] {p['name']} 파라메트릭={p['param_de']:.3f} LUT={de:.3f}", flush=True)

    param_des = np.array([p["param_de"] for p in pairs])
    diff = param_des - lut_des
    wins = int((diff > 0).sum())
    losses = int((diff < 0).sum())
    mean_param, mean_lut = float(param_des.mean()), float(lut_des.mean())
    improvement_pct = (mean_param - mean_lut) / mean_param * 100.0 if mean_param else float("nan")

    rng = np.random.RandomState(0)
    boot = np.empty(20000)
    for i in range(20000):
        idx = rng.randint(0, n, n)
        boot[i] = diff[idx].mean()
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
    p_value = _sign_test_p(wins, losses)

    print(f"\n=== {args.label}: 학습 LUT vs 파라메트릭 film_curve (n={n}) ===")
    print(f"평균 파라메트릭 ΔE00={mean_param:.3f}  평균 LUT ΔE00={mean_lut:.3f}  개선폭={improvement_pct:+.2f}%")
    print(f"승/패={wins}/{losses}  부호검정 p={p_value:.4f}")
    print(f"부트스트랩 95% CI(평균차)=[{ci_lo:+.3f}, {ci_hi:+.3f}]")
    if ci_lo <= 0 <= ci_hi:
        print("판정: 보류 (CI가 0 포함)")
    else:
        print(f"판정: {'학습 LUT 우세' if improvement_pct > 0 else '파라메트릭 우세'}")


if __name__ == "__main__":
    main()
