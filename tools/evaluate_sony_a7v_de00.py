"""
apply_sony_a7v_look()의 실제 ΔE00(CIEDE2000) - 지금까지 Sony a7V 검증은
전부 b2/w995 percentile RMSE(그리드서치 목적함수)였지, 이 프로젝트 표준
지표인 ΔE00은 안 쟀다. 기존 population-fit(apply_sony_look)과 신규
(apply_sony_a7v_look) 양쪽을 58쌍 전체에 페어드로 비교한다.

  python3 -m tools.evaluate_sony_a7v_de00
"""
import csv
import math
import os
import sys

import colour
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brands.sony import apply_sony_look
from brands.sony_a7v import apply_sony_a7v_look
from core.validation import is_image_array_usable
from tools.calibrate import load_neutral_render, _resize_to_max_dim

RAW_DIR = "/Users/songjiun/Documents/raw pair"
MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "datasets", "sony", "a7v_raw_jpeg_pairs_clean.csv")
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


def _sign_test_p(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def main():
    rows = list(csv.DictReader(open(MANIFEST)))
    print(f"Sony a7V 페어 후보: {len(rows)}개", flush=True)

    old_des, new_des, names = [], [], []
    for i, r in enumerate(rows):
        raw_path = os.path.join(RAW_DIR, r['raw_file'])
        jpg_path = os.path.join(RAW_DIR, r['jpeg_file'])
        if not (os.path.exists(raw_path) and os.path.exists(jpg_path)):
            continue
        try:
            neutral = load_neutral_render(raw_path, max_dim=DE00_MAX_DIM)
        except Exception as e:
            print(f"  [{i+1}/{len(rows)}] {r['raw_file']} 디코드 실패: {e}", flush=True)
            continue
        target_img = cv2.imread(jpg_path)
        if target_img is None or not is_image_array_usable(target_img):
            continue
        target_lin = load_target_linear(jpg_path, neutral.shape[:2])

        old_out = apply_sony_look(neutral)
        new_out = apply_sony_a7v_look(neutral)
        old_de = mean_delta_e(bgr_u8_to_linear(old_out), target_lin)
        new_de = mean_delta_e(bgr_u8_to_linear(new_out), target_lin)
        old_des.append(old_de)
        new_des.append(new_de)
        names.append(r['raw_file'])
        print(f"  [{i+1}/{len(rows)}] {r['raw_file']} old={old_de:.3f} new={new_de:.3f}", flush=True)

    old = np.array(old_des)
    new = np.array(new_des)
    n = len(old)
    diff = old - new
    wins = int((diff > 0).sum())
    losses = int((diff < 0).sum())
    mean_old, mean_new = float(old.mean()), float(new.mean())
    improvement_pct = (mean_old - mean_new) / mean_old * 100.0

    rng = np.random.RandomState(0)
    boot = np.empty(20000)
    for i in range(20000):
        idx = rng.randint(0, n, n)
        boot[i] = diff[idx].mean()
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
    p = _sign_test_p(wins, losses)

    print(f"\n=== apply_sony_a7v_look vs apply_sony_look ΔE00 (n={n}) ===")
    print(f"평균 기존(population-fit) ΔE00={mean_old:.3f}  평균 신규(a7v) ΔE00={mean_new:.3f}  "
          f"개선폭={improvement_pct:+.2f}%")
    print(f"승/패={wins}/{losses}  부호검정 p={p:.4f}")
    print(f"부트스트랩 95% CI(평균차)=[{ci_lo:+.3f}, {ci_hi:+.3f}]")
    if ci_lo <= 0 <= ci_hi:
        print("판정: 보류 (CI가 0 포함)")
    else:
        print(f"판정: {'신규(a7v) 우세' if improvement_pct > 0 else '기존 우세'}")


if __name__ == "__main__":
    main()
