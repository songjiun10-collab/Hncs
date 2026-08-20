"""
콤보A(분리감마 shadow_gamma=0.4/highlight_gamma=0.3 고정 + 채도/hue LOO)의
전체 지표 - 지금까지 ΔE00만 쟀는데, 이 세션 다른 실험들의 1차 지표였던
RMSE(b2/w995 percentile)와 drop-one 민감도까지 같이 측정해서 apply_hncs_x2dii
베이스라인과 나란히 비교한다.

  python3 -m tools.evaluate_x2dii_combo_a_full
"""
import csv
import itertools
import math
import os
import sys

import colour
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brands.hasselblad_x2dii import apply_hncs_x2dii
from core.curve import film_curve
from tools.calibrate import load_neutral_render, gray_stats

RAW_DIR = "/Users/songjiun/Documents/raw pair"
MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "datasets", "hasselblad", "dpreview_raw_jpeg_pairs_clean.csv")

DE00_MAX_DIM = 400
GRID_MAX_DIM = 160

X2DII_TOE_LIFT, X2DII_SHOULDER_START, X2DII_WHITE_POINT, X2DII_CLAHE_CLIP = 0.02, 0.82, 0.95, 1.25
SPLIT_SHADOW_GAMMA, SPLIT_HIGHLIGHT_GAMMA = 0.4, 0.3

SAT_MULT_GRID = np.linspace(0.85, 1.15, 7)
HUE_SHIFT_GRID = np.linspace(-5.0, 5.0, 7)
CHROMA_COMBOS = list(itertools.product(SAT_MULT_GRID, HUE_SHIFT_GRID))


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


def apply_split_gamma_curve(img_bgr, shadow_gamma=SPLIT_SHADOW_GAMMA, highlight_gamma=SPLIT_HIGHLIGHT_GAMMA):
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    x = np.arange(256, dtype=np.float32) / 255.0
    with np.errstate(invalid="ignore"):
        exp = np.where(x < 0.5,
                       0.5 * (x / 0.5) ** shadow_gamma,
                       0.5 + 0.5 * ((x - 0.5) / 0.5) ** highlight_gamma)
    exp_lut = np.clip(exp * 255, 0, 255).astype(np.uint8)
    l = cv2.LUT(l, exp_lut)
    clahe = cv2.createCLAHE(clipLimit=X2DII_CLAHE_CLIP, tileGridSize=(8, 8))
    l = clahe.apply(l)
    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(film_curve(x, X2DII_TOE_LIFT, X2DII_SHOULDER_START, X2DII_WHITE_POINT) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def apply_chroma_correction(img_bgr, sat_mult, hue_shift_deg):
    rgb = img_bgr[:, :, ::-1].astype(np.float32) / 255.0
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    hsv[..., 0] = (hsv[..., 0] + hue_shift_deg) % 360.0
    hsv[..., 1] = np.clip(hsv[..., 1] * sat_mult, 0.0, 1.0)
    out_rgb = np.clip(cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB), 0.0, 1.0)
    return (out_rgb * 255 + 0.5).astype(np.uint8)[:, :, ::-1]


def pair_rmse_err(stats, target, shadow_valid):
    err = (stats['w995'] - target['w995']) ** 2
    if shadow_valid:
        err += (stats['b2'] - target['b2']) ** 2
    return err


def hue_mean_channel(bgr_u8):
    hsv = cv2.cvtColor(bgr_u8, cv2.COLOR_BGR2HSV)
    return hsv[:, :, 0].astype(np.float64)


def main():
    rows = [r for r in csv.DictReader(open(MANIFEST)) if r['model'] == 'X2D II 100C']
    pairs = []
    for r in rows:
        raw_path = os.path.join(RAW_DIR, r['raw_file'])
        jpg_path = os.path.join(RAW_DIR, r['jpeg_file'])
        if os.path.exists(raw_path) and os.path.exists(jpg_path):
            pairs.append(dict(name=r['raw_file'], raw_path=raw_path, target_path=jpg_path))
    n = len(pairs)
    print(f"X2D II 페어 {n}개 - 디코드중...", flush=True)

    de00_neutral, de00_target_lin, de00_target_bgr = {}, {}, {}
    grid_neutral, grid_target_lin = {}, {}

    for i, p in enumerate(pairs):
        neutral_de = load_neutral_render(p['raw_path'], max_dim=DE00_MAX_DIM)
        de00_neutral[p['name']] = neutral_de
        de00_target_lin[p['name']] = load_target_linear(p['target_path'], neutral_de.shape[:2])
        target_bgr = cv2.resize(cv2.imread(p['target_path']),
                                 (neutral_de.shape[1], neutral_de.shape[0]),
                                 interpolation=cv2.INTER_AREA)
        de00_target_bgr[p['name']] = target_bgr

        neutral_grid = load_neutral_render(p['raw_path'], max_dim=GRID_MAX_DIM)
        grid_neutral[p['name']] = neutral_grid
        grid_target_lin[p['name']] = load_target_linear(p['target_path'], neutral_grid.shape[:2])
        print(f"  [{i+1}/{n}] {p['name']} 디코드 완료", flush=True)

    # === 베이스라인 (apply_hncs_x2dii) ===
    baseline_de00, baseline_rmse_sq, baseline_hue_delta = [], [], []
    for p in pairs:
        neutral = de00_neutral[p['name']]
        out = apply_hncs_x2dii(neutral)
        target_bgr = de00_target_bgr[p['name']]
        target_stats = gray_stats(target_bgr)
        shadow_valid = target_stats['dark_pct'] > 5

        baseline_de00.append(mean_delta_e(bgr_u8_to_linear(out), de00_target_lin[p['name']]))
        baseline_rmse_sq.append(pair_rmse_err(gray_stats(out), target_stats, shadow_valid))

        hue_before = hue_mean_channel(neutral)
        hue_after = hue_mean_channel(out)
        baseline_hue_delta.append(float(np.mean(np.abs(hue_after.astype(np.int16)
                                                         - hue_before.astype(np.int16)))))

    # === 콤보A: 분리감마(고정) + 채도/hue LOO ===
    grid_split_out = {p['name']: apply_split_gamma_curve(grid_neutral[p['name']]) for p in pairs}
    de00_split_out = {p['name']: apply_split_gamma_curve(de00_neutral[p['name']]) for p in pairs}

    chroma_grid_de = np.zeros((len(CHROMA_COMBOS), n))
    for ci, (sat_mult, hue_shift) in enumerate(CHROMA_COMBOS):
        for pi, p in enumerate(pairs):
            out = apply_chroma_correction(grid_split_out[p['name']], sat_mult, hue_shift)
            chroma_grid_de[ci, pi] = mean_delta_e(bgr_u8_to_linear(out), grid_target_lin[p['name']])

    combo_a_de00, combo_a_rmse_sq, combo_a_hue_delta = [], [], []
    for i, p in enumerate(pairs):
        train_mask = np.ones(n, dtype=bool)
        train_mask[i] = False
        best_ci = int(np.argmin(chroma_grid_de[:, train_mask].mean(axis=1)))
        sat_mult, hue_shift = CHROMA_COMBOS[best_ci]

        out = apply_chroma_correction(de00_split_out[p['name']], sat_mult, hue_shift)
        target_bgr = de00_target_bgr[p['name']]
        target_stats = gray_stats(target_bgr)
        shadow_valid = target_stats['dark_pct'] > 5

        combo_a_de00.append(mean_delta_e(bgr_u8_to_linear(out), de00_target_lin[p['name']]))
        combo_a_rmse_sq.append(pair_rmse_err(gray_stats(out), target_stats, shadow_valid))

        hue_before = hue_mean_channel(de00_neutral[p['name']])
        hue_after = hue_mean_channel(out)
        combo_a_hue_delta.append(float(np.mean(np.abs(hue_after.astype(np.int16)
                                                        - hue_before.astype(np.int16)))))
        print(f"  [{i+1}/{n}] {p['name']} ΔE00={combo_a_de00[-1]:.3f} "
              f"(baseline={baseline_de00[i]:.3f})", flush=True)

    def drop_one(vals):
        vals = np.array(vals)
        out = []
        for i in range(len(vals)):
            out.append(float(np.delete(vals, i).mean()))
        return min(out), max(out)

    base_rmse = np.sqrt(np.mean(baseline_rmse_sq))
    combo_rmse = np.sqrt(np.mean(combo_a_rmse_sq))
    rmse_improve = (base_rmse - combo_rmse) / base_rmse * 100

    print(f"\n=== 콤보A vs apply_hncs_x2dii - 전체 지표 (n={n}) ===")
    print(f"ΔE00:  베이스라인={np.mean(baseline_de00):.3f}  콤보A={np.mean(combo_a_de00):.3f}  "
          f"개선폭={(np.mean(baseline_de00)-np.mean(combo_a_de00))/np.mean(baseline_de00)*100:+.2f}%")
    lo, hi = drop_one(combo_a_de00)
    print(f"  drop-one 범위(콤보A 평균 ΔE00): [{lo:.3f}, {hi:.3f}]")

    print(f"\nRMSE(b2/w995 percentile):  베이스라인={base_rmse:.3f}  콤보A={combo_rmse:.3f}  "
          f"개선폭={rmse_improve:+.2f}%")

    print(f"\n스킨톤/hue 불변성(원본-출력 hue 채널 평균 |delta|, 0~179 스케일):")
    print(f"  베이스라인(apply_hncs_x2dii): 평균 {np.mean(baseline_hue_delta):.2f}  "
          f"최대 {np.max(baseline_hue_delta):.2f}")
    print(f"  콤보A(분리감마+채도):        평균 {np.mean(combo_a_hue_delta):.2f}  "
          f"최대 {np.max(combo_a_hue_delta):.2f}")


if __name__ == "__main__":
    main()
