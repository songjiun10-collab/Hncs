"""
`tools/evaluate_learned_lut.py`가 LOO로 검증한 학습 LUT 접근을, 최종
채택본에 구울 256값 LUT을 (홀드아웃 없이) 전체 표본으로 학습해서 뽑아
낸다 - `brands/hasselblad_learned.py`의 `_LEARNED_LUT` 같은 하드코딩
배열 포맷으로 출력.

  python3 -m tools.fit_final_lut \
      --label "Sigma BF" \
      --manifest datasets/sigma/sigma_new_pairs.csv \
      --raw-dir "/Users/songjiun/local-work" --model "Sigma BF" \
      --clahe-clip 1.25
"""
import argparse
import csv
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.validation import is_image_array_usable
from tools.calibrate import load_neutral_render

MAX_DIM = 250
N_BINS = 256
MIN_BIN_SAMPLES = 30  # 이 미만 표본인 bin은 표본 0개인 bin과 동일하게
# 취급해 보간으로 대체한다 - 소수 노이즈 픽셀 평균이 그대로 LUT에 박혀
# 비단조 튐(밴딩)을 만드는 문제 방지. 임계값 자체는 미검증(실측
# 데이터로 재검증 필요), 표본 부족 bin을 보간하는 기존 로직을 재사용.


def _build_lut(sum_target, sum_weight):
    lut = np.zeros(N_BINS)
    filled = sum_weight >= MIN_BIN_SAMPLES
    lut[filled] = sum_target[filled] / sum_weight[filled]
    domain = np.arange(N_BINS)
    if not filled.all():
        lut = np.interp(domain, domain[filled], lut[filled])
    # 보간에 쓴 bin은 실측이 아니라 표본 부족 폴백이라 낮은 가중치(1)로
    # PAVA에 들어가게 함 - 실측 bin(weight=sum_weight)이 우선한다.
    pava_weight = np.where(filled, sum_weight, 1.0)
    lut = _isotonic_regression(lut, pava_weight)
    return np.clip(lut, 0, 255).astype(np.uint8)


def _isotonic_regression(y, w):
    """PAVA(pool adjacent violators) - 가중 최소자승 기준으로 y에 가장
    가까우면서 non-decreasing인 배열을 만든다.

    정정(2026-08 코드리뷰): 순수 bin별 가중평균만 쓰면 등록/노이즈로 인접
    구간에 몇 개만 어긋난 픽셀이 섞여도 그대로 반영돼서 비단조 구간이
    생길 수 있다(Sony a7R VI/a7V LUT에서 확인: 그림자 시작(index 0-2)이
    mid-gray로 튀었다가 index 3에서 급락하는 ~70유닛 절벽 - L=0이 L=3보다
    밝게 렌더링되는 반전). 실제 톤 커브는 물리적으로 단조증가라 이 반전은
    항상 아티팩트다. w(=bin별 누적 픽셀수, sum_weight)로 가중해서 표본이
    많은 bin일수록 더 세게 고정되도록 한다."""
    y = [float(v) for v in y]
    w = [float(v) for v in w]
    n = len(y)
    stack = []  # (value, weight, start, end)
    for i in range(n):
        v, wt, s, e = y[i], w[i], i, i
        while stack and stack[-1][0] > v:
            v2, w2, s2, e2 = stack.pop()
            new_w = w2 + wt
            v = (v2 * w2 + v * wt) / new_w
            wt = new_w
            s = s2
        stack.append((v, wt, s, e))
    out = np.empty(n)
    for v, wt, s, e in stack:
        out[s:e + 1] = v
    return out


def _resolve(raw_dirs, filename):
    for d in raw_dirs:
        p = os.path.join(d, filename)
        if os.path.exists(p):
            return p
    return None


def pre_curve_l(neutral_bgr, exposure_gamma, clahe_clip):
    lab = cv2.cvtColor(neutral_bgr, cv2.COLOR_BGR2LAB)
    l = lab[:, :, 0]
    if exposure_gamma is not None and exposure_gamma != 1.0:
        x = np.arange(256, dtype=np.float32) / 255.0
        exp_lut = np.clip((x ** exposure_gamma) * 255, 0, 255).astype(np.uint8)
        l = cv2.LUT(l, exp_lut)
    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    return clahe.apply(l)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--raw-dir", action="append", required=True, dest="raw_dirs")
    ap.add_argument("--model", action="append", dest="models", default=None)
    ap.add_argument("--film-mode", default=None)
    ap.add_argument("--exposure-gamma", type=float, default=None)
    ap.add_argument("--clahe-clip", type=float, default=1.25)
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.manifest)))
    if args.models:
        rows = [r for r in rows if r["model"] in args.models]
    if args.film_mode:
        rows = [r for r in rows if r.get("film_mode") == args.film_mode]
    print(f"{args.label} 후보 {len(rows)}개", flush=True)

    sum_target = np.zeros(N_BINS)
    sum_weight = np.zeros(N_BINS)
    n_used = 0
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

        l = pre_curve_l(neutral, args.exposure_gamma, args.clahe_clip)
        tgt_l = cv2.cvtColor(target_img, cv2.COLOR_BGR2LAB)[:, :, 0]

        np.add.at(sum_target, l.ravel(), tgt_l.ravel().astype(np.float64))
        np.add.at(sum_weight, l.ravel(), 1.0)
        n_used += 1
        if (i + 1) % 10 == 0:
            print(f"  [{i+1}/{len(rows)}] 누적중...", flush=True)

    print(f"\n사용된 페어: {n_used}개", flush=True)

    lut = _build_lut(sum_target, sum_weight)

    print(f"\n_LEARNED_LUT = np.array([")
    for i in range(0, N_BINS, 16):
        print("    " + ", ".join(str(v) for v in lut[i:i + 16]) + ",")
    print("], dtype=np.uint8)")


if __name__ == "__main__":
    main()
