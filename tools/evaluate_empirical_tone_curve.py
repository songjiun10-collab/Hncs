"""
실제 카메라 JPEG의 톤 매핑을 경험적으로 뽑아서, 이 세션에서 채택한
`film_curve(toe_lift, shoulder_start, white_point)` 파라메트릭 가정이
실제 모양과 얼마나 맞는지 직접 검증한다 - 지금까지는 "이 파라메트릭
곡선 하에서 최적 파라미터가 뭐냐"만 찾았지, 애초에 곡선 모양 자체가
맞는 가정인지는 확인한 적이 없었다.

방법: 각 함수의 실제 파이프라인 순서(노출 LUT(있으면) -> CLAHE)까지
그대로 재현해서 "커브 적용 직전의 L" 값을 만들고, 이 값을 256개(또는
지정 개수) bin으로 나눠 대응하는 타깃 JPEG의 실제 L 값을 픽셀수 가중
평균으로 집계한다(경험적 곡선) - 그리고 이걸 채택된 `toe_lift/
shoulder_start/white_point`로 계산한 film_curve 예측값과 직접 비교한다
(RMSE, bin별 잔차).

  python3 -m tools.evaluate_empirical_tone_curve \
      --label "X2D II 100C" \
      --manifest datasets/hasselblad/dpreview_raw_jpeg_pairs_clean.csv \
      --raw-dir "/Users/songjiun/local-work" --model "X2D II 100C" \
      --exposure-gamma 0.6 --clahe-clip 1.25 \
      --toe-lift 0.02 --shoulder-start 0.58 --white-point 0.95
"""
import argparse
import csv
import os
import sys

import colour
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.curve import film_curve
from core.validation import is_image_array_usable
from tools.calibrate import load_neutral_render

MAX_DIM = 300
N_BINS = 64


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
    return l


def target_l(bgr_u8):
    lab = cv2.cvtColor(bgr_u8, cv2.COLOR_BGR2LAB)
    return lab[:, :, 0]


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
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.manifest)))
    if args.models:
        rows = [r for r in rows if r["model"] in args.models]
    if args.film_mode:
        rows = [r for r in rows if r.get("film_mode") == args.film_mode]
    print(f"{args.label} 후보 {len(rows)}개", flush=True)

    bin_width = 256.0 / N_BINS
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

        pre_l = pre_curve_l(neutral, args.exposure_gamma, args.clahe_clip)
        tgt_l = target_l(target_img)

        bins = np.minimum((pre_l.ravel().astype(np.float32) / bin_width).astype(int), N_BINS - 1)
        np.add.at(sum_target, bins, tgt_l.ravel().astype(np.float64))
        np.add.at(sum_weight, bins, 1.0)
        n_used += 1
        if (i + 1) % 10 == 0:
            print(f"  [{i+1}/{len(rows)}] 누적중...", flush=True)

    print(f"\n사용된 페어: {n_used}개", flush=True)
    if n_used < 5:
        print("판정: 표본 부족, 중단", flush=True)
        return

    filled = sum_weight > 0
    empirical = np.full(N_BINS, np.nan)
    empirical[filled] = sum_target[filled] / sum_weight[filled]

    centers = (np.arange(N_BINS) + 0.5) * bin_width / 255.0
    predicted = film_curve(centers, args.toe_lift, args.shoulder_start, args.white_point) * 255.0
    predicted = np.clip(predicted, 0, 255)

    diff = empirical - predicted
    valid = filled
    rmse = float(np.sqrt(np.nanmean(diff[valid] ** 2)))
    mae = float(np.nanmean(np.abs(diff[valid])))

    print(f"\n=== {args.label}: 경험적 실측 곡선 vs film_curve 예측 ===")
    print(f"RMSE={rmse:.2f}  MAE={mae:.2f}  (L 스케일 0-255)")
    print("\nbin(입력 L 중심) | 경험적(실측 평균) | 예측(film_curve) | 잔차")
    for i in range(0, N_BINS, 4):
        if not filled[i]:
            continue
        in_l = centers[i] * 255
        print(f"  {in_l:6.1f} | {empirical[i]:6.1f} | {predicted[i]:6.1f} | {diff[i]:+6.1f}")

    # 잔차가 가장 큰 영역(그림자/미드톤/하이라이트) 요약
    shadow = valid[:N_BINS // 3]
    mid = valid[N_BINS // 3:2 * N_BINS // 3]
    highlight = valid[2 * N_BINS // 3:]
    for name, mask, offset in [("그림자", shadow, 0), ("미드톤", mid, N_BINS // 3),
                                 ("하이라이트", highlight, 2 * N_BINS // 3)]:
        idx = np.where(mask)[0] + offset
        if len(idx) == 0:
            continue
        print(f"{name} 평균 잔차: {np.nanmean(diff[idx]):+.2f}")


if __name__ == "__main__":
    main()
