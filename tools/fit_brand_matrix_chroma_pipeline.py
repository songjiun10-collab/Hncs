"""
Sony/Sigma/Leica의 `apply_<brand>_raw_look()`은 `apply_canon_raw_look()`
과 달리 매트릭스가 없다(`make_population_fit_look()` - 톤커브+CLAHE만,
색 자체는 libraw 내장 매트릭스에 위임). 사용자 지시("소니같은거도 다
매트릭스 만들어", 2026-09-02)로 Canon과 같은 방법론
(`tools/fit_canon_deployable_pipeline.py`: 3x3 컬러매트릭스 최소자승 +
고정 톤커브 + 채도/색조 그리드서치, `load_neutral_render()`가 만드는
8비트 BGR 입력공간 기준)을 브랜드 인자로 일반화해서 재사용한다.

**톤커브는 Canon처럼 고정 상수로 새로 정하지 않고, 그 브랜드가 이미
raw+jpeg ΔE00 직접 그리드서치로 확정한 값을 그대로 쓴다** - Sony/Sigma는
이미 검증됨(`brands/sony_raw.py`/`sigma_raw.py`), 재탐색은 낭비.
매트릭스+채도/색조만 새로 피팅해서 그 위에 얹는다.

  python3 -m tools.fit_brand_matrix_chroma_pipeline <brand> [--loo]
  예: python3 -m tools.fit_brand_matrix_chroma_pipeline sony --loo
"""
import csv
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

SAT_MULT_GRID = np.linspace(0.7, 1.4, 15)
HUE_SHIFT_GRID = np.linspace(-10.0, 10.0, 15)

# 브랜드별: (baseline_module, baseline_func, tone_toe, tone_shoulder, tone_white,
# tone_clahe_clip, film_mode_filter). 톤커브 값은 각 브랜드 파일의 이미 검증된
# 상수를 그대로 가져옴 - 재탐색 안 함. film_mode_filter는 Fuji처럼 필름모드별로
# 다른 JPEG 렌더링이 나오는 브랜드용(EXIF FilmMode 직접 읽음) - 없으면 None.
BRAND_CONFIG = {
    "sony": ("brands.sony_raw", "apply_sony_raw_look", 0.02, 0.82, 1.0, 2.0, None),
    "sigma": ("brands.sigma_raw", "apply_sigma_raw_look", 0.02, 0.82, 1.0, 3.0, None),
    "leica": ("brands.leica_raw", "apply_leica_raw_look", 0.0, 0.82, 1.0, 1.25, None),
    "fuji": ("brands.fuji", "apply_provia", 0.0, 0.82, 1.0, 3.0, "F0/Standard (Provia)"),
}


def _exif_film_mode(jpg_path):
    import subprocess
    out = subprocess.run(["exiftool", "-s3", "-FilmMode", jpg_path],
                          capture_output=True, text=True, timeout=10)
    return out.stdout.strip()


def collect_contributed_pairs(brand, model_filter=None, film_mode_filter=None):
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
            if film_mode_filter and _exif_film_mode(jpg_path) != film_mode_filter:
                continue
            seen.add(row["filename_raw"])
            pairs.append(dict(name=row["filename_raw"], raw_path=raw_path, jpeg_path=jpg_path))
    return pairs


def load_neutral_render(raw_path, max_dim=MAX_DIM):
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


def make_apply_tone_stage(toe, shoulder, white, clip):
    def apply_tone_stage(rgb_linear):
        srgb = colour.cctf_encoding(np.clip(rgb_linear, 0.0, 1.0), function="sRGB")
        u8_bgr = (srgb * 255.0 + 0.5).astype(np.uint8)[:, :, ::-1]
        lab = cv2.cvtColor(u8_bgr, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
        l = clahe.apply(l)
        x = np.arange(256, dtype=np.float32) / 255.0
        lut = np.clip(film_curve(x, toe_lift=toe, shoulder_start=shoulder,
                                  white_point=white) * 255, 0, 255).astype(np.uint8)
        l = cv2.LUT(l, lut)
        out_bgr = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
        return colour.cctf_decoding(out_bgr[:, :, ::-1].astype(np.float64) / 255.0, function="sRGB")
    return apply_tone_stage


def _decode_one(r):
    try:
        neutral = load_neutral_render(r["raw_path"])
        source = bgr_u8_to_linear(neutral)
        target_img = cv2.imread(r["jpeg_path"])
        if target_img is None or not is_image_array_usable(target_img):
            return r["name"], None, None, None, "target unusable"
        target = load_target_linear(r["jpeg_path"], neutral.shape[:2])
    except Exception as e:
        return r["name"], None, None, None, str(e)
    return r["name"], neutral, source, target, None


def _sign_test_p(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    return min(1.0, 2.0 * sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n))


def main():
    brand = sys.argv[1]
    do_loo = "--loo" in sys.argv
    baseline_module, baseline_func_name, toe, shoulder, white, clip, film_mode_filter = BRAND_CONFIG[brand]
    import importlib
    baseline_func = getattr(importlib.import_module(baseline_module), baseline_func_name)
    apply_tone_stage = make_apply_tone_stage(toe, shoulder, white, clip)

    rows = collect_contributed_pairs(brand, film_mode_filter=film_mode_filter)
    print(f"{brand}: manifest {len(rows)}개", flush=True)
    t0 = time.time()
    pairs = []
    with multiprocessing.Pool(3) as pool:
        for i, (name, neutral, source, target, err) in enumerate(pool.imap_unordered(_decode_one, rows)):
            if err:
                continue
            pairs.append(dict(name=name, neutral=neutral, source=source, target=target))
            if (i + 1) % 20 == 0:
                print(f"  {i+1}/{len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    n = len(pairs)
    print(f"디코드 완료: {n}개 ({time.time()-t0:.0f}s)", flush=True)

    baseline_des = np.array([
        mean_delta_e(bgr_u8_to_linear(baseline_func(p['neutral'])), p['target']) for p in pairs
    ])
    print(f"현재 배포 {baseline_func_name}() 기준 ΔE00 = {baseline_des.mean():.4f}")

    if do_loo:
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
        print(f"\n=== {brand} 매트릭스+채도 LOO(n={n}) ===")
        print(f"기존(톤커브만) ΔE00={mean_base:.3f}  매트릭스+채도 LOO ΔE00={mean_loo:.3f}  개선폭={improvement:+.2f}%")
        print(f"승/패={wins}/{losses}  부호검정 p={p_val:.4f}  부트스트랩 95% CI=[{ci_lo:+.3f},{ci_hi:+.3f}]")
        print("판정:", "보류(CI 0 포함)" if ci_lo <= 0 <= ci_hi else ("매트릭스 우세" if improvement > 0 else "기존 우세"))

    matrix = fit_color_matrix([p['source'] for p in pairs], [p['target'] for p in pairs], ridge=1.0)
    toned = [apply_tone_stage(np.clip(p['source'] @ matrix, 0.0, None)) for p in pairs]
    best_de, best_params = float("inf"), (1.0, 0.0)
    for sm in SAT_MULT_GRID:
        for hs in HUE_SHIFT_GRID:
            des = [mean_delta_e(apply_chroma_lut(t, sm, hs), p['target']) for t, p in zip(toned, pairs)]
            mde = float(np.mean(des))
            if mde < best_de:
                best_de, best_params = mde, (sm, hs)

    print(f"\n=== {brand} 최종 배포용 파라미터(전체 표본 피팅, n={n}) ===")
    print("matrix =", matrix.tolist())
    print(f"sat_mult={best_params[0]:.4f}, hue_shift={best_params[1]:+.4f}")
    print(f"tone: toe_lift={toe}, shoulder_start={shoulder}, white_point={white}, clahe_clip={clip}")
    print(f"in-sample ΔE00={best_de:.4f}")


if __name__ == "__main__":
    main()
