"""
apply_hncs_x2dii()의 실제 ΔE00/RMSE를 shoulder_start 정정(0.82->0.5)
이후, 확장된 X2D II 70쌍 전체로 재확인한다 - 이전 측정(ΔE00=14.866,
RMSE=15.643)은 ss=0.82·n=41 기준이라 지금 값과 직접 비교 대상이 아니다.

  python3 -m tools.evaluate_x2dii_de00_check
"""
import csv
import os
import sys

import colour
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brands.hasselblad_x2dii import apply_hncs_x2dii
from tools.calibrate import load_neutral_render, gray_stats

RAW_DIR = "/Users/songjiun/Documents/raw pair"
MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "datasets", "hasselblad", "dpreview_raw_jpeg_pairs_clean.csv")
DE00_MAX_DIM = 400


def load_target_linear(jpg_path, shape_hw):
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


def pair_rmse_err(stats, target, shadow_valid):
    err = (stats['w995'] - target['w995']) ** 2
    if shadow_valid:
        err += (stats['b2'] - target['b2']) ** 2
    return err


def main():
    rows = [r for r in csv.DictReader(open(MANIFEST)) if r['model'] == 'X2D II 100C']
    pairs = []
    for r in rows:
        raw_path = os.path.join(RAW_DIR, r['raw_file'])
        jpg_path = os.path.join(RAW_DIR, r['jpeg_file'])
        if os.path.exists(raw_path) and os.path.exists(jpg_path):
            pairs.append(dict(name=r['raw_file'], raw_path=raw_path, target_path=jpg_path))
    n = len(pairs)
    print(f"X2D II 페어 {n}개", flush=True)

    de00s, rmse_sqs = [], []
    for i, p in enumerate(pairs):
        try:
            neutral = load_neutral_render(p['raw_path'], max_dim=DE00_MAX_DIM)
        except Exception as e:
            print(f"  [{i+1}/{n}] {p['name']} 디코드 실패: {e}", flush=True)
            continue
        target_lin = load_target_linear(p['target_path'], neutral.shape[:2])
        target_bgr = cv2.resize(cv2.imread(p['target_path']),
                                 (neutral.shape[1], neutral.shape[0]),
                                 interpolation=cv2.INTER_AREA)
        target_stats = gray_stats(target_bgr)
        shadow_valid = target_stats['dark_pct'] > 5

        out = apply_hncs_x2dii(neutral)
        de00 = mean_delta_e(bgr_u8_to_linear(out), target_lin)
        rmse_sq = pair_rmse_err(gray_stats(out), target_stats, shadow_valid)
        de00s.append(de00)
        rmse_sqs.append(rmse_sq)
        print(f"  [{i+1}/{n}] {p['name']} ΔE00={de00:.3f}", flush=True)

    de00s = np.array(de00s)
    rmse = np.sqrt(np.mean(rmse_sqs))
    print(f"\n=== apply_hncs_x2dii(shoulder_start=0.5, n={len(de00s)}) ===")
    print(f"평균 ΔE00={de00s.mean():.3f}  중앙값={np.median(de00s):.3f}  "
          f"최소={de00s.min():.3f}  최대={de00s.max():.3f}")
    print(f"RMSE(b2/w995 percentile)={rmse:.3f}")


if __name__ == "__main__":
    main()
