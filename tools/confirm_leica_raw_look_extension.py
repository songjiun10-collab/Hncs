"""
/goal - fit_population_body_de00_grid.py가 SL2-S(n=43)에서 LOO 폴드 절반이
`apply_leica_raw_look()`의 기존 기본값(toe=0,ss=0.82,wp=1.0,clip=1.25)과
정확히 같은 조합을 고른 걸 확인 - 새 함수 없이 이 함수의 적용 범위를
SL2-S/CL로 넓히기만 해도 되는지 원본 픽셀로 직접 검증한다
(evaluate_full_pixel_de00_confirm.py의 SL2/M10 확장 때와 같은 방법).

  python3 -m tools.confirm_leica_raw_look_extension
"""
import math
import os
import sys

import colour
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brands.leica import apply_leica_look
from brands.leica_raw import apply_leica_raw_look
from core.validation import is_image_array_usable
from tools.calibrate import load_neutral_render

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NATIVE_MAX_DIM = 3000


def collect_contributed_pairs(brand, model_filter=None):
    import csv
    base = os.path.join(BASE, "datasets", brand, "contributed")
    pairs = []
    seen = set()
    for set_name in sorted(os.listdir(base)):
        manifest = os.path.join(base, set_name, "manifest.csv")
        if not os.path.exists(manifest):
            continue
        for row in csv.DictReader(open(manifest, encoding="utf-8-sig")):
            if row["filename_raw"] in seen:
                continue
            if model_filter and row.get("camera") != model_filter:
                continue
            raw_path = os.path.join(base, set_name, "raw", row["filename_raw"])
            jpg_path = os.path.join(base, set_name, "jpeg", row["filename_jpeg"])
            if not (os.path.exists(raw_path) and os.path.exists(jpg_path)):
                continue
            seen.add(row["filename_raw"])
            pairs.append(dict(name=row["filename_raw"], raw_path=raw_path, jpeg_path=jpg_path))
    return pairs


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


def run(label, model_filter):
    pairs = collect_contributed_pairs("leica", model_filter)
    print(f"\n### {label} - 원본 픽셀(max_dim={NATIVE_MAX_DIM}) n={len(pairs)} ###", flush=True)
    old_des, new_des = [], []
    for i, r in enumerate(pairs):
        try:
            neutral = load_neutral_render(r["raw_path"], max_dim=NATIVE_MAX_DIM)
        except Exception as e:
            print(f"  [{i+1}/{len(pairs)}] {r['name']} 디코드 실패: {e}", flush=True)
            continue
        target_img = cv2.imread(r["jpeg_path"])
        if target_img is None or not is_image_array_usable(target_img):
            continue
        target_lin = load_target_linear_native(r["jpeg_path"], neutral.shape[:2])
        old_de = mean_delta_e(bgr_u8_to_linear(apply_leica_look(neutral)), target_lin)
        new_de = mean_delta_e(bgr_u8_to_linear(apply_leica_raw_look(neutral)), target_lin)
        old_des.append(old_de)
        new_des.append(new_de)
        print(f"  [{i+1}/{len(pairs)}] {r['name']} old(leica_look)={old_de:.3f} "
              f"new(leica_raw_look)={new_de:.3f}", flush=True)

    old = np.array(old_des)
    new = np.array(new_des)
    n = len(old)
    if n == 0:
        print("유효 표본 없음")
        return
    diff = old - new
    wins = int((diff > 0).sum())
    losses = int((diff < 0).sum())
    mean_old, mean_new = float(old.mean()), float(new.mean())
    improvement_pct = (mean_old - mean_new) / mean_old * 100.0 if mean_old else float('nan')
    rng = np.random.RandomState(0)
    boot = np.array([diff[rng.randint(0, n, n)].mean() for _ in range(20000)])
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
    p_value = _sign_test_p(wins, losses)

    print(f"\n=== {label} 원본 픽셀 (n={n}) ===")
    print(f"apply_leica_look(main)={mean_old:.3f}  apply_leica_raw_look={mean_new:.3f}  개선폭={improvement_pct:+.2f}%")
    print(f"승/패={wins}/{losses}  부호검정 p={p_value:.4f}  부트스트랩 95% CI=[{ci_lo:+.3f},{ci_hi:+.3f}]")
    if ci_lo <= 0 <= ci_hi:
        print("판정: 보류 (CI가 0 포함)")
    else:
        print(f"판정: {'leica_raw_look 우세' if improvement_pct > 0 else 'leica_look(main) 우세'}")


def main():
    import sys as _sys
    if "--already10" in _sys.argv:
        # opus 에스컬레이션 권고 - 800px 서베이에서 "이미 10 미만"이라던 3바디를
        # 원본 픽셀로 재확인(SL2-S가 400px 10.277 -> native 11.824로 밀린 것과
        # 같은 해상도 편향이 있는지 확인, 30분 타임박스)
        run("Leica SL2", "LEICA SL2")
        run("Leica SL3-P", "LEICA SL3-P")
        run("Leica M10", "LEICA M10")
    else:
        run("Leica SL2-S", "LEICA SL2-S")
        run("Leica CL", "LEICA CL")


if __name__ == "__main__":
    main()
