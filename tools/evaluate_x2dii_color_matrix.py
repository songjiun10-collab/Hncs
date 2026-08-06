"""
X2D II 41쌍 자체에서 3x3 컬러 매트릭스를 직접 피팅(LOO)하면 apply_hncs()
(main 기본값)보다 나은지 확인한다. 이전(위 v13 이력, docs/measurements.md
"ColorChecker 매트릭스를 X2D II 실사진 41장에 교차검증")엔 X2D II
**챠트**(kmichels-x2dii-2026-07, ColorChecker 10연사)로 피팅된 매트릭스를
그대로 실사진에 적용만 해봤는데(챠트 매트릭스+톤커브가 톤커브 단독보다
오히려 나빠짐, 11.23->12.32 ΔE00) - 이번엔 챠트가 아니라 **실사진 41장
자체**로 매트릭스를 새로 피팅해서 같은 질문을 다시 묻는다.

tools/evaluate_hncs_structural.py의 독립 재구현 패턴을 그대로 따르되
(tools/CLAUDE.md: evaluate_*.py끼리 서로 import 금지, 로더 복사)
클러스터 분류/chroma LUT 그리드서치는 뺐다 - X2D II 단일 세대만 다루므로
조명 클러스터 분리가 필요 없고(41장 다 같은 카메라), 이번 질문은 "매트릭스
자체가 실사진 기준으로 도움되는가"에 집중한다.

  python3 -m tools.evaluate_x2dii_color_matrix
"""
import csv
import json
import os
import subprocess
import sys

import colour
import cv2
import numpy as np
import rawpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brands.hasselblad import apply_hncs
from core.curve import film_curve

RAW_DIR = "/Users/songjiun/Documents/raw pair"
MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "datasets", "hasselblad", "dpreview_raw_jpeg_pairs_clean.csv")
DOWNSAMPLE_MAX_DIM = 512

# apply_hncs()(main) 톤커브 기본값과 맞춤 - 매트릭스 단계만 통제변수로 뺀
# 공정 비교 (exposure_gamma/CLAHE는 apply_hncs 자체 baseline 쪽에만 있음)
FILM_CURVE_TOE_LIFT = 0.0
FILM_CURVE_SHOULDER_START = 0.5
FILM_CURVE_WHITE_POINT = 1.0


def read_as_shot_neutral(path):
    out = subprocess.run(["exiftool", "-json", "-AsShotNeutral", path],
                          capture_output=True, text=True, timeout=30)
    data = json.loads(out.stdout) if out.stdout.strip() else [{}]
    raw_value = (data[0] if data else {}).get("AsShotNeutral")
    if not raw_value:
        return None
    parts = str(raw_value).replace(",", " ").split()
    try:
        values = [float(p) for p in parts]
    except ValueError:
        return None
    return np.array(values[:3], dtype=np.float64) if len(values) >= 3 else None


def decode_raw_native(raw_path, max_dim=DOWNSAMPLE_MAX_DIM):
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


def decode_raw_libraw(raw_path, max_dim=DOWNSAMPLE_MAX_DIM):
    with rawpy.imread(raw_path) as raw:
        rgb16 = raw.postprocess(
            use_camera_wb=True, no_auto_bright=True, output_bps=16,
            output_color=rawpy.ColorSpace.sRGB, gamma=(1, 1), half_size=True,
        )
    h, w = rgb16.shape[:2]
    scale = max_dim / max(h, w)
    if scale < 1:
        rgb16 = cv2.resize(rgb16, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return rgb16.astype(np.float64) / 65535.0


def decode_and_white_balance(raw_path, max_dim=DOWNSAMPLE_MAX_DIM):
    native_rgb = decode_raw_native(raw_path, max_dim)
    asn = read_as_shot_neutral(raw_path)
    if asn is None:
        raise ValueError(f"AsShotNeutral 없음: {raw_path}")
    return native_rgb / asn


def load_image_linear(path, resize_to):
    bgr = cv2.imread(path)
    if bgr is None:
        raise FileNotFoundError(path)
    bgr = cv2.resize(bgr, (resize_to[1], resize_to[0]), interpolation=cv2.INTER_AREA)
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
    if ridge == 0.0:
        matrix, _, _, _ = np.linalg.lstsq(X, Y, rcond=None)
    else:
        k = X.shape[1]
        matrix = np.linalg.solve(X.T @ X + ridge * np.eye(k), X.T @ Y)
    return matrix


def apply_color_matrix(rgb_linear, matrix):
    return np.clip(rgb_linear @ matrix, 0.0, None)


def shared_film_curve(rgb_linear):
    return film_curve(np.clip(rgb_linear, 0.0, 1.0), toe_lift=FILM_CURVE_TOE_LIFT,
                       shoulder_start=FILM_CURVE_SHOULDER_START,
                       white_point=FILM_CURVE_WHITE_POINT)


def _sign_test_p(wins, losses):
    import math
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def main():
    rows = [r for r in csv.DictReader(open(MANIFEST)) if r['model'] == 'X2D II 100C']
    print(f"X2D II 페어 {len(rows)}개", flush=True)

    pairs = []
    for i, r in enumerate(rows):
        raw_path = os.path.join(RAW_DIR, r['raw_file'])
        jpg_path = os.path.join(RAW_DIR, r['jpeg_file'])
        if not (os.path.exists(raw_path) and os.path.exists(jpg_path)):
            continue
        asn = read_as_shot_neutral(raw_path)
        if asn is None:
            print(f"  [{i+1}/{len(rows)}] {r['raw_file']} AsShotNeutral 없음, 제외")
            continue
        pairs.append(dict(name=r['raw_file'], raw_path=raw_path, target_path=jpg_path))
        print(f"  [{i+1}/{len(rows)}] {r['raw_file']} 등록", flush=True)

    n = len(pairs)
    print(f"\n사용 가능한 페어: {n}개 - 디코드/타깃 로드중...", flush=True)

    wb_cache, target_cache, baseline_cache, target_baseline_cache = {}, {}, {}, {}
    for i, p in enumerate(pairs):
        wb_rgb = decode_and_white_balance(p['raw_path'])
        wb_cache[p['name']] = wb_rgb
        target_cache[p['name']] = load_image_linear(p['target_path'], wb_rgb.shape[:2])

        baseline_rgb = decode_raw_libraw(p['raw_path'])
        baseline_cache[p['name']] = baseline_rgb
        target_baseline_cache[p['name']] = load_image_linear(p['target_path'], baseline_rgb.shape[:2])
        print(f"  [{i+1}/{n}] {p['name']} 디코드 완료", flush=True)

    # apply_hncs() baseline (매트릭스 없음, main 기본값 그대로)
    hncs_des = []
    for p in pairs:
        baseline = baseline_cache[p['name']]
        encoded = colour.cctf_encoding(np.clip(baseline, 0.0, 1.0), function="sRGB")
        u8_bgr = (np.clip(encoded, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)[:, :, ::-1]
        result_bgr = apply_hncs(u8_bgr)
        result_linear = colour.cctf_decoding(result_bgr[:, :, ::-1].astype(np.float64) / 255.0,
                                              function="sRGB")
        hncs_des.append(mean_delta_e(result_linear, target_baseline_cache[p['name']]))
    print(f"apply_hncs(main) 평균 ΔE00={np.mean(hncs_des):.3f}", flush=True)

    # LOO: 매트릭스를 held-out 뺀 40쌍으로 피팅 -> held-out에 적용 + 공유 필름커브
    matrix_des = []
    for i, held_out in enumerate(pairs):
        train = [p for j, p in enumerate(pairs) if j != i]
        sources = [wb_cache[p['name']] for p in train]
        targets = [target_cache[p['name']] for p in train]
        matrix = fit_color_matrix(sources, targets, ridge=1.0)

        matrixed = apply_color_matrix(wb_cache[held_out['name']], matrix)
        result = shared_film_curve(matrixed)
        de = mean_delta_e(result, target_cache[held_out['name']])
        matrix_des.append(de)
        print(f"  [{i+1}/{n}] {held_out['name']} LOO 매트릭스 ΔE00={de:.3f} "
              f"(apply_hncs={hncs_des[i]:.3f})", flush=True)

    hncs = np.array(hncs_des)
    other = np.array(matrix_des)
    diff = hncs - other
    wins = int((diff > 0).sum())
    losses = int((diff < 0).sum())
    mean_hncs, mean_other = float(hncs.mean()), float(other.mean())
    improvement_pct = (mean_hncs - mean_other) / mean_hncs * 100.0

    rng = np.random.RandomState(0)
    boot = np.empty(20000)
    for i in range(20000):
        idx = rng.randint(0, n, n)
        boot[i] = diff[idx].mean()
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
    p_value = _sign_test_p(wins, losses)
    inconclusive = ci_lo <= 0 <= ci_hi

    print(f"\n=== X2D II 전용 LOO 3x3 매트릭스 vs apply_hncs(main) (n={n}) ===")
    print(f"평균 apply_hncs ΔE00={mean_hncs:.3f}  평균 매트릭스+공유필름커브 ΔE00={mean_other:.3f}  "
          f"개선폭={improvement_pct:+.2f}%")
    print(f"승/패={wins}/{losses}  부호검정 p={p_value:.4f}")
    print(f"부트스트랩 95% CI(평균차)=[{ci_lo:+.3f}, {ci_hi:+.3f}]")
    print("판정: 보류 (CI가 0 포함)" if inconclusive else
          f"판정: {'매트릭스 우세' if improvement_pct > 0 else 'apply_hncs 우세'}")


if __name__ == "__main__":
    main()
