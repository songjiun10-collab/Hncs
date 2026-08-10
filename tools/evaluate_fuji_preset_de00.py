"""
후지 필름시뮬레이션 프리셋(brands/fuji.py)을 raw+jpeg 페어로 직접 검증한다 -
apply_provia와 달리 apply_classic_negative/apply_nostalgic_neg/
apply_eterna_cinema 등은 toe_lift/shoulder_start/white_point 형태가
아니라 각자 다른 파라미터(sat_mult/contrast_n 등)를 쓰는 손튜닝 구현이라
tools/evaluate_new_body_de00_grid.py의 그리드서치 구조를 그대로 못 쓴다 -
대신 raw 무가공 렌더 대비 기존 프리셋이 실제로 ΔE00을 줄이는지만
직접 측정한다(그리드서치 아님, 이미 있는 프리셋의 실측 검증).

  python3 -m tools.evaluate_fuji_preset_de00 \
      "Fuji GFX50S II Classic Negative" /tmp/fuji_classic_negative.csv \
      brands.fuji.apply_classic_negative
"""
import csv
import importlib
import os
import sys

import colour
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.validation import is_image_array_usable
from tools.calibrate import load_neutral_render

RAWDIR = "/Users/songjiun/local-work"
CONFIRM_MAX_DIM = 400


def load_target_linear(jpg_path, shape_hw):
    bgr = cv2.imread(jpg_path)
    bgr = cv2.resize(bgr, (shape_hw[1], shape_hw[0]), interpolation=cv2.INTER_AREA)
    rgb = bgr[:, :, ::-1].astype(np.float64) / 255.0
    return colour.cctf_decoding(rgb, function="sRGB")


def bgr_u8_to_linear(bgr_u8):
    rgb = bgr_u8[:, :, ::-1].astype(np.float64) / 255.0
    return colour.cctf_decoding(rgb, function="sRGB")


def mean_delta_e(a, b):
    from skimage.color import rgb2lab, deltaE_ciede2000
    ae = colour.cctf_encoding(np.clip(a, 0.0, 1.0), function="sRGB")
    be = colour.cctf_encoding(np.clip(b, 0.0, 1.0), function="sRGB")
    return float(np.mean(deltaE_ciede2000(rgb2lab(ae), rgb2lab(be))))


def main():
    label, manifest, fn_path = sys.argv[1], sys.argv[2], sys.argv[3]
    mod_path, fn_name = fn_path.rsplit(".", 1)
    fn = getattr(importlib.import_module(mod_path), fn_name)

    rows = list(csv.DictReader(open(manifest)))
    print(f"{label} 후보 {len(rows)}개 (preset={fn_path})", flush=True)

    old_des, new_des = [], []
    for i, r in enumerate(rows):
        raw_path = os.path.join(RAWDIR, r["raw_file"])
        jpg_path = os.path.join(RAWDIR, r["jpeg_file"])
        if not (os.path.exists(raw_path) and os.path.exists(jpg_path)):
            continue
        try:
            neutral = load_neutral_render(raw_path, max_dim=CONFIRM_MAX_DIM)
        except Exception as e:
            print(f"  [{i+1}/{len(rows)}] {r['raw_file']} 디코드 실패: {e}", flush=True)
            continue
        target_img = cv2.imread(jpg_path)
        if target_img is None or not is_image_array_usable(target_img):
            continue
        target_lin = load_target_linear(jpg_path, neutral.shape[:2])

        out = fn(neutral)
        if out.ndim == 2:
            out = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
        old_de = mean_delta_e(bgr_u8_to_linear(neutral), target_lin)
        new_de = mean_delta_e(bgr_u8_to_linear(out), target_lin)
        old_des.append(old_de)
        new_des.append(new_de)
        print(f"  [{i+1}/{len(rows)}] {r['raw_file']} raw={old_de:.3f} preset={new_de:.3f}", flush=True)

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

    print(f"\n=== {label} raw 무가공 vs 기존 프리셋 (n={n}) ===")
    print(f"평균 raw ΔE00={mean_old:.3f}  평균 preset ΔE00={mean_new:.3f}  개선폭={improvement_pct:+.2f}%")
    print(f"승/패={wins}/{losses}")
    print(f"부트스트랩 95% CI(평균차)=[{ci_lo:+.3f}, {ci_hi:+.3f}]")
    if ci_lo <= 0 <= ci_hi:
        print("판정: 보류 (CI가 0 포함)")
    else:
        print(f"판정: {'프리셋이 raw보다 우세' if improvement_pct > 0 else 'raw가 프리셋보다 우세(프리셋 방향이 틀림)'}")


if __name__ == "__main__":
    main()
