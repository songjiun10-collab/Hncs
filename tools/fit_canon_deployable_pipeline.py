"""
/goal - fit_canon_final_params.py가 낸 매트릭스는 raw 네이티브 순수 선형
(AsShotNeutral 수동 화이트밸런스, libraw 컬러매트릭스 미적용) 입력
기준이었다 - 그런데 실제 `apply_canon_look()`은 `load_neutral_render()`가
만드는 다른 입력(libraw use_camera_wb=True, gamma=(2.222,4.5), 8비트
BGR - libraw 자체 컬러매트릭스가 이미 적용된 값)을 받는다. 두 입력
공간이 다르므로 그 매트릭스를 그대로 갖다 쓰면 안 된다 - **같은
`load_neutral_render()` 입력을 기준으로 매트릭스/채도/색조를 다시
피팅**해서 실제 apply_* 시그니처(8비트 BGR in/out)와 호환되는 배포용
파라미터를 낸다. 방법론(3x3 매트릭스 최소자승 + 톤커브 + 채도/색조
LOO)은 fit_body_matrix_plus_tone_de00.py와 동일, 입력 디코드만 교체.

  python3 -m tools.fit_canon_deployable_pipeline [--loo]
"""
import csv
import itertools
import math
import multiprocessing
import os
import sys
import time

import colour
import cv2
import numpy as np
import rawpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.curve import film_curve
from core.validation import is_image_array_usable

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_DIM = 400
N_FOLDS = 5

TONE_TOE_LIFT = 0.0
TONE_SHOULDER_START = 0.74
TONE_WHITE_POINT = 1.0
TONE_CLAHE_CLIP = 3.0

SAT_MULT_GRID = np.linspace(0.7, 1.4, 15)
HUE_SHIFT_GRID = np.linspace(-10.0, 10.0, 15)


def collect_contributed_pairs(brand, model_filter=None):
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


def load_neutral_render(raw_path, max_dim=MAX_DIM):
    """tools.calibrate.load_neutral_render과 완전히 동일한 디코드 설정 -
    apply_canon_look()이 실제로 받는 것과 같은 입력을 재현."""
    with rawpy.imread(raw_path) as raw:
        rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=True,
                               output_bps=8, gamma=(2.222, 4.5))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    h, w = bgr.shape[:2]
    scale = max_dim / max(h, w)
    if scale < 1:
        bgr = cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return bgr


def bgr_u8_to_linear(bgr_u8):
    rgb = bgr_u8[:, :, ::-1].astype(np.float64) / 255.0
    return colour.cctf_decoding(rgb, function="sRGB")


def load_target_linear(jpg_path, shape_hw):
    bgr = cv2.imread(jpg_path)
    bgr = cv2.resize(bgr, (shape_hw[1], shape_hw[0]), interpolation=cv2.INTER_AREA)
    return bgr_u8_to_linear(bgr)


def mean_delta_e(linear_a, linear_b):
    from skimage.color import rgb2lab, deltaE_ciede2000
    a = colour.cctf_encoding(np.clip(linear_a, 0.0, 1.0), function="sRGB")
    b = colour.cctf_encoding(np.clip(linear_b, 0.0, 1.0), function="sRGB")
    return float(np.mean(deltaE_ciede2000(rgb2lab(a), rgb2lab(b))))


def fit_color_matrix(sources, targets, ridge=1.0):
    X = np.concatenate([s.reshape(-1, 3) for s in sources], axis=0)
    Y = np.concatenate([t.reshape(-1, 3) for t in targets], axis=0)
    k = X.shape[1]
    return np.linalg.solve(X.T @ X + ridge * np.eye(k), X.T @ Y)


def apply_chroma_lut(img_rgb_linear, sat_mult, hue_shift_deg):
    clipped = np.clip(img_rgb_linear, 0.0, 1.0).astype(np.float32)
    hsv = cv2.cvtColor(clipped, cv2.COLOR_RGB2HSV)
    hsv[..., 0] = (hsv[..., 0] + hue_shift_deg) % 360.0
    hsv[..., 1] = np.clip(hsv[..., 1] * sat_mult, 0.0, 1.0)
    out = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
    return np.clip(out, 0.0, 1.0).astype(np.float64)


def apply_tone_stage(rgb_linear):
    srgb = colour.cctf_encoding(np.clip(rgb_linear, 0.0, 1.0), function="sRGB")
    u8_bgr = (srgb * 255.0 + 0.5).astype(np.uint8)[:, :, ::-1]
    lab = cv2.cvtColor(u8_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=TONE_CLAHE_CLIP, tileGridSize=(8, 8))
    l = clahe.apply(l)
    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(film_curve(x, TONE_TOE_LIFT, TONE_SHOULDER_START, TONE_WHITE_POINT) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)
    out_bgr = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    return colour.cctf_decoding(out_bgr[:, :, ::-1].astype(np.float64) / 255.0, function="sRGB")


def _decode_one(r):
    try:
        neutral = load_neutral_render(r["raw_path"])
        source = bgr_u8_to_linear(neutral)
        target_img = cv2.imread(r["jpeg_path"])
        if target_img is None or not is_image_array_usable(target_img):
            return r["name"], None, None, "target unusable"
        target = load_target_linear(r["jpeg_path"], neutral.shape[:2])
    except Exception as e:
        return r["name"], None, None, str(e)
    return r["name"], source, target, None


def _sign_test_p(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    return min(1.0, 2.0 * sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n))


def main():
    do_loo = "--loo" in sys.argv
    rows = collect_contributed_pairs("canon", None)
    print(f"canon: manifest {len(rows)}개", flush=True)
    t0 = time.time()
    pairs = []
    with multiprocessing.Pool(3) as pool:
        for i, (name, source, target, err) in enumerate(pool.imap_unordered(_decode_one, rows)):
            if err:
                continue
            pairs.append(dict(name=name, source=source, target=target))
            if (i + 1) % 20 == 0:
                print(f"  {i+1}/{len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    n = len(pairs)
    print(f"디코드 완료: {n}개 ({time.time()-t0:.0f}s)", flush=True)

    if do_loo:
        baseline_des = np.array([mean_delta_e(apply_tone_stage(p['source']), p['target']) for p in pairs])
        folds = np.array_split(np.random.RandomState(0).permutation(n), N_FOLDS)
        loo_des = np.zeros(n)
        for fi, test_idx in enumerate(folds):
            train_idx = [i for i in range(n) if i not in set(test_idx.tolist())]
            train = [pairs[i] for i in train_idx]
            matrix = fit_color_matrix([p['source'] for p in train], [p['target'] for p in train], ridge=1.0)
            train_toned = [apply_tone_stage(np.clip(p['source'] @ matrix, 0.0, None)) for p in train]
            best_de, best_params = float("inf"), (1.0, 0.0)
            for sm in SAT_MULT_GRID:
                for hs in HUE_SHIFT_GRID:
                    des = [mean_delta_e(apply_chroma_lut(t, sm, hs), p['target'])
                           for t, p in zip(train_toned, train)]
                    mde = float(np.mean(des))
                    if mde < best_de:
                        best_de, best_params = mde, (sm, hs)
            sat_mult, hue_shift = best_params
            for i in test_idx:
                matrixed = np.clip(pairs[i]['source'] @ matrix, 0.0, None)
                toned = apply_tone_stage(matrixed)
                loo_des[i] = mean_delta_e(apply_chroma_lut(toned, sat_mult, hue_shift), pairs[i]['target'])
            print(f"  fold {fi+1}/{N_FOLDS} sat={sat_mult:.2f} hue={hue_shift:+.1f}", flush=True)

        diff = baseline_des - loo_des
        wins, losses = int((diff > 0).sum()), int((diff < 0).sum())
        mean_base, mean_loo = float(baseline_des.mean()), float(loo_des.mean())
        improvement = (mean_base - mean_loo) / mean_base * 100.0
        rng = np.random.RandomState(0)
        boot = np.array([diff[rng.randint(0, n, n)].mean() for _ in range(20000)])
        ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
        p_val = _sign_test_p(wins, losses)
        print(f"\n=== LOO 검증(배포용 입력 공간, n={n}) ===")
        print(f"톤만 ΔE00={mean_base:.3f}  매트릭스+톤+채도(LOO) ΔE00={mean_loo:.3f}  개선폭={improvement:+.2f}%")
        print(f"승/패={wins}/{losses}  부호검정 p={p_val:.4f}  부트스트랩 95% CI=[{ci_lo:+.3f},{ci_hi:+.3f}]")
        print("판정:", "보류(CI 0 포함)" if ci_lo <= 0 <= ci_hi else ("개선" if improvement > 0 else "악화"))

    matrix = fit_color_matrix([p['source'] for p in pairs], [p['target'] for p in pairs], ridge=1.0)
    toned = [apply_tone_stage(np.clip(p['source'] @ matrix, 0.0, None)) for p in pairs]
    best_de, best_params = float("inf"), (1.0, 0.0)
    for sm in SAT_MULT_GRID:
        for hs in HUE_SHIFT_GRID:
            des = [mean_delta_e(apply_chroma_lut(t, sm, hs), p['target']) for t, p in zip(toned, pairs)]
            mde = float(np.mean(des))
            if mde < best_de:
                best_de, best_params = mde, (sm, hs)

    print(f"\n=== 최종 배포용 파라미터(전체 표본 피팅, n={n}) ===")
    print("matrix =", matrix.tolist())
    print(f"sat_mult={best_params[0]:.3f}, hue_shift={best_params[1]:+.2f}")
    print(f"tone: toe_lift={TONE_TOE_LIFT}, shoulder_start={TONE_SHOULDER_START}, "
          f"white_point={TONE_WHITE_POINT}, clahe_clip={TONE_CLAHE_CLIP}")
    print(f"in-sample ΔE00={best_de:.3f}")
    baseline_de = np.mean([mean_delta_e(apply_tone_stage(p['source']), p['target']) for p in pairs])
    print(f"참고 - 톤만(매트릭스 없음) in-sample ΔE00={baseline_de:.3f}")


if __name__ == "__main__":
    main()
