"""
/goal "다른 전체 브랜드 평균 e00->10미만으로" - 착수 전 현재 위치 파악용.
브랜드/바디별로 현재 shipped 함수(전용 바디 함수가 있으면 그거, 없으면
generic population-fit apply_*_look)의 실측 ΔE00을 한 번에 측정한다.
800px(디코드 속도와 CLAHE 해상도 민감성 사이 타협 - 원본 3000px는
전체 브랜드 규모에서 비현실적, 최종 판정은 개별 후보를 원본 픽셀로
재확인) x 3코어 병렬 디코드.

  python3 -m tools.measure_all_brand_baselines
"""
import multiprocessing
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brands.canon import apply_canon_look
from brands.fuji import apply_provia
from brands.leica import apply_leica_look
from brands.leica.raw import apply_leica_raw_look
from brands.nikon import apply_nikon_look
from brands.sigma import apply_sigma_look
from brands.sigma.bf import apply_sigma_bf_look
from brands.sony import apply_sony_look
from brands.sony.a7rvi import apply_sony_a7rvi_look
from brands.sony.a7v import apply_sony_a7v_look
from core.validation import is_image_array_usable
from tools.calibrate import load_neutral_render
from tools.evaluation_common import (
    bgr_u8_to_linear,
    collect_contributed_pairs,
    load_target_linear,
    mean_delta_e,
)

MAX_DIM = 800


def _decode_one(r):
    try:
        neutral = load_neutral_render(r["raw_path"], max_dim=MAX_DIM)
        return r["name"], neutral, None
    except Exception as e:
        return r["name"], None, str(e)


def measure(label, brand, model_filter, fn):
    pairs = collect_contributed_pairs(brand, model_filter)
    if len(pairs) < 5:
        print(f"{label}: n={len(pairs)} - 표본 부족, 스킵")
        return None
    with multiprocessing.Pool(3) as pool:
        decoded = {}
        for name, neutral, err in pool.imap_unordered(_decode_one, pairs):
            if neutral is not None:
                decoded[name] = neutral
    des = []
    for r in pairs:
        neutral = decoded.get(r["name"])
        if neutral is None:
            continue
        target_img = cv2.imread(r["jpeg_path"])
        if target_img is None or not is_image_array_usable(target_img):
            continue
        target_lin = load_target_linear(r["jpeg_path"], neutral.shape[:2])
        out = fn(neutral)
        des.append(mean_delta_e(bgr_u8_to_linear(out), target_lin))
    if not des:
        print(f"{label}: 디코드 성공 0개")
        return None
    mean_de = float(np.mean(des))
    print(f"{label}: n={len(des)}  평균 ΔE00={mean_de:.3f}  {'<-- 10 미만' if mean_de < 10 else ''}", flush=True)
    return mean_de


def main():
    t0 = time.time()
    results = {}
    jobs = [
        ("Sony (generic, non-a7V/a7RVI)", "sony", None, apply_sony_look),
        ("Sony a7V (dedicated)", "sony", "ILCE-7M5", apply_sony_a7v_look),
        ("Sony a7R VI (dedicated)", "sony", "ILCE-7RM6", apply_sony_a7rvi_look),
        ("Leica (generic)", "leica", None, apply_leica_look),
        ("Leica SL3-P (dedicated)", "leica", "LEICA SL3-P", apply_leica_raw_look),
        ("Leica Q3 43 (dedicated)", "leica", "LEICA Q3 43", apply_leica_raw_look),
        ("Leica SL2 (dedicated)", "leica", "LEICA SL2", apply_leica_raw_look),
        ("Leica M10 (dedicated)", "leica", "LEICA M10", apply_leica_raw_look),
        ("Fuji GFX100RF (dedicated, mixed film modes)", "fuji", "GFX100RF", apply_provia),
        ("Fuji (generic other bodies)", "fuji", None, apply_provia),
        ("Sigma (generic)", "sigma", None, apply_sigma_look),
        ("Sigma BF (dedicated)", "sigma", "Sigma BF", apply_sigma_bf_look),
        ("Canon (generic)", "canon", None, apply_canon_look),
        ("Nikon (generic)", "nikon", None, apply_nikon_look),
    ]
    for label, brand, model_filter, fn in jobs:
        de = measure(label, brand, model_filter, fn)
        if de is not None:
            results[label] = de
    print(f"\n총 소요 {time.time()-t0:.0f}s")
    print("\n=== 요약 ===")
    for label, de in sorted(results.items(), key=lambda kv: -kv[1]):
        print(f"  {de:6.3f}  {'OK' if de < 10 else '>=10'}  {label}")
    over = [(l, d) for l, d in results.items() if d >= 10]
    print(f"\n10 이상인 것: {len(over)}/{len(results)}")


if __name__ == "__main__":
    main()
