"""
tools/fit_population_body_de00_grid.py는 200px 콤보선택/400px LOO확정으로
끝난다 - CLAHE(tileGridSize=(8,8) 고정)가 해상도에 따라 결과를 왜곡한다는
게 이 세션 hncs_structural 재검증에서 확인된 뒤라(clahe_clip이 특히
민감), 새 population-fit raw_look 후보를 원본 픽셀(max_dim=3000,
evaluate_full_pixel_de00_confirm.py/evaluate_clahe_clip_native_confirm.py와
동일 상한)로 재확인한다 - 기존 shipped `apply_<brand>_look()` vs 후보
파라미터(toe_lift/shoulder_start/white_point/clahe_clip) 직접 맞대결.

  python3 -m tools.evaluate_population_raw_look_native_confirm <brand> <toe_lift> <shoulder_start> <white_point> <clahe_clip>
  예: python3 -m tools.evaluate_population_raw_look_native_confirm sony 0.02 0.82 1.0 2.0
"""
import importlib
import math
import multiprocessing
import os
import sys
import time

import colour
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.validation import is_image_array_usable
from tools.calibrate import load_neutral_render
from tools.evaluate_expanded_clahe_shoulder_refit import collect_contributed_pairs

NATIVE_MAX_DIM = 3000


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


def _decode_one(r):
    try:
        neutral = load_neutral_render(r["raw_path"], max_dim=NATIVE_MAX_DIM)
        return r["name"], neutral, None
    except Exception as e:
        return r["name"], None, str(e)


def precompute(pairs, n_workers=3):
    print(f"디코드 사전계산 중 - {len(pairs)}쌍, {n_workers}코어...", flush=True)
    t0 = time.time()
    result = {}
    with multiprocessing.Pool(n_workers) as pool:
        for i, (name, neutral, err) in enumerate(pool.imap_unordered(_decode_one, pairs)):
            if err:
                print(f"  {name} 디코드 실패: {err}", flush=True)
            else:
                result[name] = neutral
            if (i + 1) % 20 == 0:
                print(f"  {i+1}/{len(pairs)} ({time.time()-t0:.0f}s경과)", flush=True)
    print(f"디코드 완료 ({time.time()-t0:.0f}s, {len(result)}/{len(pairs)} 성공)", flush=True)
    return result


def main():
    brand = sys.argv[1]
    toe_lift, shoulder_start, white_point, clahe_clip = (float(x) for x in sys.argv[2:6])
    shipped_look = getattr(importlib.import_module(f"brands.{brand}"), f"apply_{brand}_look")

    pairs = collect_contributed_pairs(brand)
    print(f"{brand}: manifest {len(pairs)}쌍", flush=True)
    decoded = precompute(pairs, n_workers=3)

    old_des, new_des = [], []
    for r in pairs:
        neutral = decoded.get(r["name"])
        if neutral is None:
            continue
        target_img = cv2.imread(r["jpeg_path"])
        if target_img is None or not is_image_array_usable(target_img):
            continue
        target_lin = load_target_linear_native(r["jpeg_path"], neutral.shape[:2])
        old_out = shipped_look(neutral)
        new_out = shipped_look(neutral, toe_lift=toe_lift, shoulder_start=shoulder_start,
                                white_point=white_point, clahe_clip=clahe_clip)
        old_des.append(mean_delta_e(bgr_u8_to_linear(old_out), target_lin))
        new_des.append(mean_delta_e(bgr_u8_to_linear(new_out), target_lin))

    old_des, new_des = np.array(old_des), np.array(new_des)
    n = len(old_des)
    diff = old_des - new_des
    wins, losses = int((diff > 0).sum()), int((diff < 0).sum())
    mean_old, mean_new = float(old_des.mean()), float(new_des.mean())
    improvement = (mean_old - mean_new) / mean_old * 100.0
    rng = np.random.RandomState(0)
    boot = np.array([diff[rng.randint(0, n, n)].mean() for _ in range(20000)])
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
    p_val = _sign_test_p(wins, losses)

    print(f"\n=== {brand} 원본 픽셀(max_dim={NATIVE_MAX_DIM}) 재확인 (n={n}) ===")
    print(f"기존(shipped apply_{brand}_look) ΔE00={mean_old:.3f}  후보(toe={toe_lift},ss={shoulder_start},"
          f"wp={white_point},clip={clahe_clip}) ΔE00={mean_new:.3f}  개선폭={improvement:+.2f}%")
    print(f"승/패={wins}/{losses}  부호검정 p={p_val:.4f}  부트스트랩 95% CI=[{ci_lo:+.3f},{ci_hi:+.3f}]")
    print("판정:", "보류(CI 0 포함)" if ci_lo <= 0 <= ci_hi else ("후보 우세" if improvement > 0 else "기존 우세"))


if __name__ == "__main__":
    main()
