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

    lut = np.zeros(N_BINS)
    filled = sum_weight > 0
    lut[filled] = sum_target[filled] / sum_weight[filled]
    domain = np.arange(N_BINS)
    if not filled.all():
        lut = np.interp(domain, domain[filled], lut[filled])
    lut = np.clip(lut, 0, 255).astype(np.uint8)

    print(f"\n_LEARNED_LUT = np.array([")
    for i in range(0, N_BINS, 16):
        print("    " + ", ".join(str(v) for v in lut[i:i + 16]) + ",")
    print("], dtype=np.uint8)")


if __name__ == "__main__":
    main()
