"""
apply_provia()(GFX100RF n=89)/apply_sigma_bf_look()(n=83)의 clahe_clip
1.25->3.0 채택은 200px 선택/400px LOO 확정으로 끝났다 - hncs_structural
재검증에서 CLAHE(tileGridSize=(8,8) 고정)가 해상도에 따라 결과를
왜곡한다는 게 확인된 뒤라(사용자 지적, docs/hncs_structural_research.md
"정정" 절), 두 함수도 같은 함정에 빠졌는지 원본 픽셀(다운샘플 최소화,
max_dim=3000 - evaluate_full_pixel_de00_confirm.py와 동일 상한)로
재확인한다. clahe_clip=1.25(구) vs 3.0(신, 현재 shipped 기본값) 직접
맞대결 - 다른 파라미터(shoulder_start 등)는 두 조건 동일.

  python3 -m tools.evaluate_clahe_clip_native_confirm
"""
import math
import os
import sys

import colour
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brands.fuji import apply_provia
from brands.sigma_bf import apply_sigma_bf_look
from core.validation import is_image_array_usable
from tools.calibrate import load_neutral_render
from tools.evaluate_expanded_clahe_shoulder_refit import collect_contributed_pairs, _exif_film_mode

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
    import multiprocessing
    import time
    print(f"디코드 사전계산 중 - {len(pairs)}쌍, {n_workers}코어...", flush=True)
    t0 = time.time()
    result = {}
    with multiprocessing.Pool(n_workers) as pool:
        for i, (name, neutral, err) in enumerate(pool.imap_unordered(_decode_one, pairs)):
            if err:
                print(f"  {name} 디코드 실패: {err}", flush=True)
            else:
                result[name] = neutral
            if (i + 1) % 10 == 0:
                print(f"  {i+1}/{len(pairs)} ({time.time()-t0:.0f}s경과)", flush=True)
    print(f"디코드 완료 ({time.time()-t0:.0f}s, {len(result)}/{len(pairs)} 성공)", flush=True)
    return result


def run(label, pairs, fn, old_kwargs, new_kwargs):
    print(f"\n### {label} - 원본 픽셀(max_dim={NATIVE_MAX_DIM}) n={len(pairs)} ###", flush=True)
    decoded = precompute(pairs, n_workers=3)
    old_des, new_des = [], []
    for i, r in enumerate(pairs):
        neutral = decoded.get(r["name"])
        if neutral is None:
            continue
        target_img = cv2.imread(r["jpeg_path"])
        if target_img is None or not is_image_array_usable(target_img):
            continue
        target_lin = load_target_linear_native(r["jpeg_path"], neutral.shape[:2])
        old_out = fn(neutral, **old_kwargs)
        new_out = fn(neutral, **new_kwargs)
        old_de = mean_delta_e(bgr_u8_to_linear(old_out), target_lin)
        new_de = mean_delta_e(bgr_u8_to_linear(new_out), target_lin)
        old_des.append(old_de)
        new_des.append(new_de)
        print(f"  [{i+1}/{len(pairs)}] {r['name']} ({neutral.shape[1]}x{neutral.shape[0]}) "
              f"old(clip=1.25)={old_de:.3f} new(clip=3.0)={new_de:.3f}", flush=True)

    old = np.array(old_des)
    new = np.array(new_des)
    n = len(old)
    diff = old - new
    wins = int((diff > 0).sum())
    losses = int((diff < 0).sum())
    mean_old, mean_new = float(old.mean()), float(new.mean())
    improvement_pct = (mean_old - mean_new) / mean_old * 100.0 if mean_old else float('nan')

    rng = np.random.RandomState(0)
    boot = np.empty(20000)
    for i in range(20000):
        idx = rng.randint(0, n, n)
        boot[i] = diff[idx].mean()
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
    p_value = _sign_test_p(wins, losses)

    print(f"\n=== {label} 원본 픽셀 재확인 (n={n}) ===")
    print(f"평균 clip=1.25={mean_old:.3f}  평균 clip=3.0={mean_new:.3f}  개선폭={improvement_pct:+.2f}%")
    print(f"승/패={wins}/{losses}  부호검정 p={p_value:.4f}")
    print(f"부트스트랩 95% CI(평균차)=[{ci_lo:+.3f}, {ci_hi:+.3f}]")
    if ci_lo <= 0 <= ci_hi:
        print("판정: 보류 (CI가 0 포함)")
    else:
        print(f"판정: {'clip=3.0 우세' if improvement_pct > 0 else 'clip=1.25 우세'}")


def main():
    gfx_pairs = collect_contributed_pairs("fuji", "GFX100RF")
    gfx_pairs = [p for p in gfx_pairs if _exif_film_mode(p["jpeg_path"]) == "F0/Standard (Provia)"]
    run("GFX100RF Provia (apply_provia)", gfx_pairs, apply_provia,
        dict(clahe_clip=1.25), dict(clahe_clip=3.0))

    sigma_pairs = collect_contributed_pairs("sigma", "Sigma BF")
    run("Sigma BF (apply_sigma_bf_look)", sigma_pairs, apply_sigma_bf_look,
        dict(clahe_clip=1.25), dict(clahe_clip=3.0))


if __name__ == "__main__":
    main()
