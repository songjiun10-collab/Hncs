"""
apply_hncs_x2dii()/콤보A(분리감마+채도)가 실제 이미지에서 어떻게
보이는지 눈으로 확인하는 렌더 스크립트 - 지금까지의 검증은 전부
ΔE00/RMSE 숫자였지, 실제 출력 JPG를 본 적은 없었다. X2D II raw 몇
장을 골라 원본 카메라 JPG / apply_hncs(main) / apply_hncs_x2dii /
콤보A(분리감마+채도) 네 개를 나란히 렌더링해서 저장한다.

콤보A는 ΔE00은 크게 개선하지만(+20%) RMSE(b2/w995 percentile)는
크게 악화시켜서(-46%) 하이라이트가 날아갔을 가능성이 있다 - 이
렌더가 그 의심을 눈으로 확인하는 용도. w995(밝은 쪽 0.5% percentile)
숫자도 같이 찍는다.

  python3 -m tools.render_x2dii_comparison
"""
import csv
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brands.hasselblad import apply_hncs
from brands.hasselblad_x2dii import apply_hncs_x2dii
from core.curve import film_curve
from tools.calibrate import load_neutral_render, gray_stats

RAW_DIR = "/Users/songjiun/Documents/raw pair"
MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "datasets", "hasselblad", "dpreview_raw_jpeg_pairs_clean.csv")
OUT_DIR = "/private/tmp/claude-501/-Users-songjiun/2723c108-07c0-42ac-b509-d2a51043de16/scratchpad/x2dii_compare"

SAMPLE_RAW_FILES = [
    "0174976521.3fr",
    "0512413224.3fr",
    "1188410135.3fr",
    "5648738585.3fr",
    "9860222596.3fr",
]

X2DII_TOE_LIFT, X2DII_SHOULDER_START, X2DII_WHITE_POINT, X2DII_CLAHE_CLIP = 0.02, 0.5, 0.95, 1.25
SPLIT_SHADOW_GAMMA, SPLIT_HIGHLIGHT_GAMMA = 0.4, 0.3
COMBO_A_SAT_MULT, COMBO_A_HUE_SHIFT = 1.150, -1.67  # 70쌍 LOO 만장일치값


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


def apply_chroma_correction(img_bgr, sat_mult=COMBO_A_SAT_MULT, hue_shift_deg=COMBO_A_HUE_SHIFT):
    rgb = img_bgr[:, :, ::-1].astype(np.float32) / 255.0
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    hsv[..., 0] = (hsv[..., 0] + hue_shift_deg) % 360.0
    hsv[..., 1] = np.clip(hsv[..., 1] * sat_mult, 0.0, 1.0)
    out_rgb = np.clip(cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB), 0.0, 1.0)
    return (out_rgb * 255 + 0.5).astype(np.uint8)[:, :, ::-1]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rows = {r['raw_file']: r for r in csv.DictReader(open(MANIFEST))}

    for raw_file in SAMPLE_RAW_FILES:
        r = rows[raw_file]
        raw_path = os.path.join(RAW_DIR, raw_file)
        jpg_path = os.path.join(RAW_DIR, r['jpeg_file'])
        stem = os.path.splitext(raw_file)[0]

        neutral = load_neutral_render(raw_path, max_dim=1600)
        main_out = apply_hncs(neutral)
        x2dii_out = apply_hncs_x2dii(neutral)
        combo_a_out = apply_chroma_correction(apply_split_gamma_curve(neutral))
        target = cv2.imread(jpg_path)
        h, w = neutral.shape[:2]
        if target is not None:
            target = cv2.resize(target, (w, h), interpolation=cv2.INTER_AREA)

        cv2.imwrite(os.path.join(OUT_DIR, f"{stem}_1_camera_jpg.jpg"), target)
        cv2.imwrite(os.path.join(OUT_DIR, f"{stem}_2_apply_hncs_main.jpg"), main_out)
        cv2.imwrite(os.path.join(OUT_DIR, f"{stem}_3_apply_hncs_x2dii.jpg"), x2dii_out)
        cv2.imwrite(os.path.join(OUT_DIR, f"{stem}_4_combo_a.jpg"), combo_a_out)

        t_w995 = gray_stats(target)['w995'] if target is not None else float('nan')
        x_w995 = gray_stats(x2dii_out)['w995']
        c_w995 = gray_stats(combo_a_out)['w995']
        x_blown = (cv2.cvtColor(x2dii_out, cv2.COLOR_BGR2GRAY) >= 254).mean() * 100
        c_blown = (cv2.cvtColor(combo_a_out, cv2.COLOR_BGR2GRAY) >= 254).mean() * 100
        print(f"{raw_file}: 저장 완료  |  w995 target={t_w995:.1f} x2dii={x_w995:.1f} "
              f"comboA={c_w995:.1f}  |  254+  x2dii={x_blown:.1f}% comboA={c_blown:.1f}%", flush=True)

    print(f"\n출력 위치: {OUT_DIR}")


if __name__ == "__main__":
    main()
