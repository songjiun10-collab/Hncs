"""
tools/evaluate_new_body_de00_grid.py / evaluate_hasselblad_body_de00_grid.py가
저해상도(200px)로 고른 최적 콤보를, 다운샘플 없이(원본 해상도, max_dim=3000
안전 상한 - X2D II 100MP OOM 방지, evaluate_full_pixel_de00_confirm.py와 동일
근거) baseline과 다시 맞대결시켜 확인한다. LOO는 안 함 - 이미 그리드서치
LOO로 폴드 전체 지배(예: 95/95, 41/41)를 확인한 콤보를 픽셀 단위로만
재검증하는 용도.

  python3 -m tools.evaluate_native_pixel_confirm \
      --label "Canon EOS R6 Mark III" \
      --manifest datasets/canon/canon_new_pairs.csv \
      --raw-dir "/Users/songjiun/local-work/raw pair" \
      --baseline brands.canon.apply_canon_look \
      --toe-lift 0.0 --shoulder-start 0.82 --white-point 1.0

--exposure-gamma를 주면 Hasselblad 스타일(exposure LUT 추가)로 후보를 만든다.
"""
import argparse
import csv
import importlib
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

CONFIRM_MAX_DIM = 3000
CLAHE_CLIP = 1.25


def make_candidate(toe_lift, shoulder_start, white_point, exposure_gamma):
    def fn(img_bgr):
        lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        if exposure_gamma is not None and exposure_gamma != 1.0:
            x = np.arange(256, dtype=np.float32) / 255.0
            exp_lut = np.clip((x ** exposure_gamma) * 255, 0, 255).astype(np.uint8)
            l = cv2.LUT(l, exp_lut)
        clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP, tileGridSize=(8, 8))
        l = clahe.apply(l)
        x = np.arange(256, dtype=np.float32) / 255.0
        lut = np.clip(film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                      0, 255).astype(np.uint8)
        l = cv2.LUT(l, lut)
        return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    return fn


def load_target_linear_native(jpg_path, shape_hw):
    bgr = cv2.imread(jpg_path)
    bgr = cv2.resize(bgr, (shape_hw[1], shape_hw[0]), interpolation=cv2.INTER_AREA)
    rgb = bgr[:, :, ::-1].astype(np.float64) / 255.0
    return colour.cctf_decoding(rgb, function="sRGB")


def bgr_u8_to_linear(bgr_u8):
    rgb = bgr_u8[:, :, ::-1].astype(np.float64) / 255.0
    return colour.cctf_decoding(rgb, function="sRGB")


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


def _resolve(raw_dirs, filename):
    for d in raw_dirs:
        p = os.path.join(d, filename)
        if os.path.exists(p):
            return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--raw-dir", action="append", required=True, dest="raw_dirs")
    ap.add_argument("--model", action="append", dest="models", default=None)
    ap.add_argument("--baseline", default=None)
    ap.add_argument("--baseline-identity", action="store_true")
    ap.add_argument("--toe-lift", type=float, required=True)
    ap.add_argument("--shoulder-start", type=float, required=True)
    ap.add_argument("--white-point", type=float, required=True)
    ap.add_argument("--exposure-gamma", type=float, default=None)
    args = ap.parse_args()

    if args.baseline_identity:
        baseline_fn = lambda img: img
        args.baseline = "identity(no-op)"
    else:
        mod_path, fn_name = args.baseline.rsplit(".", 1)
        baseline_fn = getattr(importlib.import_module(mod_path), fn_name)
    candidate_fn = make_candidate(args.toe_lift, args.shoulder_start, args.white_point,
                                   args.exposure_gamma)

    rows = list(csv.DictReader(open(args.manifest)))
    if args.models:
        rows = [r for r in rows if r["model"] in args.models]
    print(f"{args.label} - 후보 {len(rows)}개 (원본 해상도, max_dim={CONFIRM_MAX_DIM})", flush=True)

    old_des, new_des = [], []
    for i, r in enumerate(rows):
        raw_path = _resolve(args.raw_dirs, r["raw_file"])
        jpg_path = _resolve(args.raw_dirs, r["jpeg_file"])
        if raw_path is None or jpg_path is None:
            continue
        try:
            neutral = load_neutral_render(raw_path, max_dim=CONFIRM_MAX_DIM)
        except Exception as e:
            print(f"  [{i+1}/{len(rows)}] {r['raw_file']} 디코드 실패: {e}", flush=True)
            continue
        target_img = cv2.imread(jpg_path)
        if target_img is None or not is_image_array_usable(target_img):
            continue
        target_lin = load_target_linear_native(jpg_path, neutral.shape[:2])

        old_out = baseline_fn(neutral)
        new_out = candidate_fn(neutral)
        old_de = mean_delta_e(bgr_u8_to_linear(old_out), target_lin)
        new_de = mean_delta_e(bgr_u8_to_linear(new_out), target_lin)
        old_des.append(old_de)
        new_des.append(new_de)
        print(f"  [{i+1}/{len(rows)}] {r['raw_file']} ({neutral.shape[1]}x{neutral.shape[0]}) "
              f"old={old_de:.3f} new={new_de:.3f}", flush=True)

    old = np.array(old_des)
    new = np.array(new_des)
    n = len(old)
    diff = old - new
    wins = int((diff > 0).sum())
    losses = int((diff < 0).sum())
    mean_old, mean_new = float(old.mean()), float(new.mean())
    improvement_pct = (mean_old - mean_new) / mean_old * 100.0 if mean_old else float("nan")

    rng = np.random.RandomState(0)
    boot = np.empty(20000)
    for i in range(20000):
        idx = rng.randint(0, n, n)
        boot[i] = diff[idx].mean()
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
    p_value = _sign_test_p(wins, losses)

    print(f"\n=== {args.label} 원본 해상도 재확인 (n={n}) ===")
    print(f"평균 baseline ΔE00={mean_old:.3f}  평균 후보 ΔE00={mean_new:.3f}  개선폭={improvement_pct:+.2f}%")
    print(f"승/패={wins}/{losses}  부호검정 p={p_value:.4f}")
    print(f"부트스트랩 95% CI(평균차)=[{ci_lo:+.3f}, {ci_hi:+.3f}]")
    if ci_lo <= 0 <= ci_hi:
        print("판정: 보류 (CI가 0 포함)")
    else:
        print(f"판정: {'후보 우세' if improvement_pct > 0 else 'baseline 우세'}")


if __name__ == "__main__":
    main()
