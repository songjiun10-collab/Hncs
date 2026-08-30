"""
/goal "다른 전체 브랜드 평균 e00->10미만으로" - fit_population_body_de00_grid.py가
확인한 대로(Canon: 23.1->22.0, +4.62%뿐) 순수 톤커브 4파라미터
(toe_lift/shoulder_start/white_point/clahe_clip)만으로는 10 근처도 못 간다 -
이 파라미터군은 밝기/대비만 건드리고 색(매트릭스/채도)은 안 건드리기
때문일 가능성. raw 네이티브 화이트밸런스 선형 RGB에 3x3 컬러매트릭스를
최소자승으로 새로 피팅(hncs_structural과 같은 방법)한 뒤, 그 위에
population-fit 톤커브를 적용해서 매트릭스가 실제로 격차를 줄이는지
직접 검증한다.

  python3 -m tools.fit_body_matrix_plus_tone_de00 <brand> [model_filter]
"""
import csv
import math
import multiprocessing
import os
import subprocess
import sys
import time
import json

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

# fit_population_body_de00_grid.py Canon 결과에서 나온 최적 톤 파라미터를 기본값으로 사용
TONE_TOE_LIFT = 0.0
TONE_SHOULDER_START = 0.74
TONE_WHITE_POINT = 1.0
TONE_CLAHE_CLIP = 3.0


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


def read_as_shot_neutral(path):
    out = subprocess.run(["exiftool", "-json", "-AsShotNeutral", "-WB_RGGBLevelsAsShot", path],
                          capture_output=True, text=True, timeout=30)
    data = json.loads(out.stdout) if out.stdout.strip() else [{}]
    row = data[0] if data else {}
    raw_value = row.get("AsShotNeutral")
    if raw_value:
        parts = str(raw_value).replace(",", " ").split()
        try:
            values = [float(p) for p in parts]
        except ValueError:
            return None
        return np.array(values[:3], dtype=np.float64) if len(values) >= 3 else None

    # Canon .cr3 등은 AsShotNeutral이 없고 "WB RGGB Levels As Shot"(R Gr Gb B 게인)만
    # 있다 - AsShotNeutral과 역수 관계(게인이 클수록 그 채널을 더 증폭)라
    # G=1 기준으로 정규화해서 같은 형태(나눗셈으로 화이트밸런스)로 변환.
    rggb = row.get("WB_RGGBLevelsAsShot")
    if rggb:
        parts = str(rggb).replace(",", " ").split()
        try:
            r, gr, gb, b = [float(p) for p in parts[:4]]
        except ValueError:
            return None
        g = (gr + gb) / 2.0
        if g == 0:
            return None
        return np.array([g / r, 1.0, g / b], dtype=np.float64)
    return None


def decode_raw_native(raw_path, max_dim=MAX_DIM):
    with rawpy.imread(raw_path) as raw:
        rgb16 = raw.postprocess(
            use_camera_wb=False, use_auto_wb=False, user_wb=[1.0, 1.0, 1.0, 1.0],
            no_auto_bright=True, output_bps=16, output_color=rawpy.ColorSpace.raw,
            gamma=(1, 1), half_size=True,
        )
    h, w = rgb16.shape[:2]
    scale = max_dim / max(h, w)
    if scale < 1:
        rgb16 = cv2.resize(rgb16, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return rgb16.astype(np.float64) / 65535.0


def load_target_linear(jpg_path, shape_hw):
    bgr = cv2.imread(jpg_path)
    bgr = cv2.resize(bgr, (shape_hw[1], shape_hw[0]), interpolation=cv2.INTER_AREA)
    rgb = bgr[:, :, ::-1].astype(np.float64) / 255.0
    return colour.cctf_decoding(rgb, function="sRGB")


def mean_delta_e(rgb_linear_a, rgb_linear_b):
    from skimage.color import rgb2lab, deltaE_ciede2000
    a = colour.cctf_encoding(np.clip(rgb_linear_a, 0.0, 1.0), function="sRGB")
    b = colour.cctf_encoding(np.clip(rgb_linear_b, 0.0, 1.0), function="sRGB")
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


SAT_MULT_GRID = np.linspace(0.7, 1.4, 15)
HUE_SHIFT_GRID = np.linspace(-10.0, 10.0, 15)


def apply_tone_stage(rgb_linear):
    """population-fit 톤커브(CLAHE + film_curve)를 pure-linear 입력에 적용 -
    apply_population_fit_look과 같은 논리를 raw linear RGB에 직접 적용
    (원래는 8비트 BGR 입력을 전제하므로 인코딩 후 재적용)."""
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
        asn = read_as_shot_neutral(r["raw_path"])
        if asn is None:
            return r["name"], None, None, "no AsShotNeutral"
        native = decode_raw_native(r["raw_path"])
        wb_rgb = native / asn
        target_img = cv2.imread(r["jpeg_path"])
        if target_img is None or not is_image_array_usable(target_img):
            return r["name"], None, None, "target unusable"
        target = load_target_linear(r["jpeg_path"], wb_rgb.shape[:2])
    except Exception as e:
        return r["name"], None, None, str(e)
    return r["name"], wb_rgb, target, None


def main():
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    brand = positional[0]
    model_filter = positional[1] if len(positional) > 1 else None
    rows = collect_contributed_pairs(brand, model_filter)
    print(f"{brand} {model_filter or '(all)'}: manifest {len(rows)}개", flush=True)

    t0 = time.time()
    pairs = []
    with multiprocessing.Pool(3) as pool:
        for i, (name, wb_rgb, target, err) in enumerate(pool.imap_unordered(_decode_one, rows)):
            if err:
                print(f"  {name} 실패: {err}", flush=True)
                continue
            pairs.append(dict(name=name, wb_rgb=wb_rgb, target=target))
            if (i + 1) % 20 == 0:
                print(f"  {i+1}/{len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    n = len(pairs)
    print(f"디코드 완료: {n}개 ({time.time()-t0:.0f}s)", flush=True)
    if n < 10:
        print("표본 부족, 종료")
        return

    # baseline: 매트릭스 없음(항등), 톤커브만
    baseline_des = np.array([mean_delta_e(apply_tone_stage(p['wb_rgb']), p['target']) for p in pairs])

    use_chroma = "--chroma" in sys.argv
    folds = np.array_split(np.random.RandomState(0).permutation(n), N_FOLDS)
    loo_des = np.zeros(n)
    for fi, test_idx in enumerate(folds):
        train_idx = [i for i in range(n) if i not in set(test_idx.tolist())]
        train = [pairs[i] for i in train_idx]
        matrix = fit_color_matrix([p['wb_rgb'] for p in train], [p['target'] for p in train], ridge=1.0)

        sat_mult, hue_shift = 1.0, 0.0
        if use_chroma:
            train_matrixed = [np.clip(p['wb_rgb'] @ matrix, 0.0, None) for p in train]
            train_toned = [apply_tone_stage(m) for m in train_matrixed]
            best_de, best_params = float("inf"), (1.0, 0.0)
            for sm in SAT_MULT_GRID:
                for hs in HUE_SHIFT_GRID:
                    des = [mean_delta_e(apply_chroma_lut(t, sm, hs), p['target'])
                           for t, p in zip(train_toned, train)]
                    mde = float(np.mean(des))
                    if mde < best_de:
                        best_de, best_params = mde, (sm, hs)
            sat_mult, hue_shift = best_params
            print(f"    fold {fi+1} best chroma sat={sat_mult:.2f} hue={hue_shift:+.1f}", flush=True)

        for i in test_idx:
            matrixed = np.clip(pairs[i]['wb_rgb'] @ matrix, 0.0, None)
            toned = apply_tone_stage(matrixed)
            if use_chroma:
                toned = apply_chroma_lut(toned, sat_mult, hue_shift)
            de = mean_delta_e(toned, pairs[i]['target'])
            loo_des[i] = de
        print(f"  fold {fi+1}/{N_FOLDS} 완료", flush=True)

    diff = baseline_des - loo_des
    wins = int((diff > 0).sum())
    losses = int((diff < 0).sum())
    mean_base, mean_loo = float(baseline_des.mean()), float(loo_des.mean())
    improvement = (mean_base - mean_loo) / mean_base * 100.0

    def _sign_test_p(w, l):
        nn = w + l
        if nn == 0:
            return 1.0
        k = min(w, l)
        return min(1.0, 2.0 * sum(math.comb(nn, i) for i in range(k + 1)) / (2.0 ** nn))

    rng = np.random.RandomState(0)
    boot = np.array([diff[rng.randint(0, n, n)].mean() for _ in range(20000)])
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
    p_val = _sign_test_p(wins, losses)

    print(f"\n=== {brand} {model_filter or '(all)'} 매트릭스+톤 결과 (n={n}) ===")
    print(f"톤커브만(매트릭스 없음) ΔE00={mean_base:.3f}  매트릭스+톤(LOO) ΔE00={mean_loo:.3f}  개선폭={improvement:+.2f}%")
    print(f"승/패={wins}/{losses}  부호검정 p={p_val:.4f}  부트스트랩 95% CI=[{ci_lo:+.3f},{ci_hi:+.3f}]")
    print("판정:", "보류(CI 0 포함)" if ci_lo <= 0 <= ci_hi else ("매트릭스 도움됨" if improvement > 0 else "매트릭스 오히려 나쁨"))


if __name__ == "__main__":
    main()
