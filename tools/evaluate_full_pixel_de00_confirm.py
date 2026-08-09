"""
이 프로젝트에서 확정한 모든 raw+jpeg 기반 신규 함수의 ΔE00을 - 그리드서치/
LOO 선택 단계에서는 전부 저해상도(160~400px)로 계산했으니 - **원본
해상도(다운샘플 없음)**로 한 번에 재확인한다. 그리드서치 자체를 원본
해상도로 재실행하는 건 아니고(콤보 수 x 페어 수 x 원본해상도라
비현실적), 이미 확정된 파라미터 1개씩만 원본 픽셀로 재측정 - 다운샘플이
결론을 왜곡했는지 확인하는 용도. 채택 안 한 함수(Sony a7R VI 전용값,
Sigma BF, Hasselblad X2D 100C/CFV)는 포함 안 함 - shipped apply_*만 대상.

  python3 -m tools.evaluate_full_pixel_de00_confirm

**갱신(2026-08)**: 로컬 raw+jpeg 라이브러리가 `~/Documents/raw pair`에서
`~/local-work`로 옮겨져서 RAW_DIR을 갱신, apply_hncs_x1d50c/
apply_leica_raw_look(SL2·M10 확장)/apply_provia 3건을 추가했다.
"""
import csv
import os
import sys

import colour
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brands.fuji import apply_provia
from brands.hasselblad import apply_hncs
from brands.hasselblad_x1d50c import apply_hncs_x1d50c
from brands.hasselblad_x2dii import apply_hncs_x2dii
from brands.leica import apply_leica_look
from brands.leica_raw import apply_leica_raw_look
from brands.sigma import apply_sigma_look
from brands.sigma_bf import apply_sigma_bf_look
from brands.sony import apply_sony_look
from brands.sony_a7rvi import apply_sony_a7rvi_look
from brands.sony_a7v import apply_sony_a7v_look
from core.validation import is_image_array_usable
from tools.calibrate import load_neutral_render

RAW_DIR = "/Users/songjiun/local-work"
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_IDENTITY = lambda img: img


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


def run(label, manifest_path, model_filter, old_fn, new_fn, film_mode_filter=None):
    rows = list(csv.DictReader(open(manifest_path)))
    if model_filter:
        rows = [r for r in rows if r['model'] == model_filter]
    if film_mode_filter:
        # fuji_new_pairs.csv 전용 컬럼 - 같은 바디라도 촬영자가 필름모드를
        # 섞어 쓰면(Provia/Pro Neg Std/Reala 등) apply_provia는 Provia하고만
        # 비교해야 함 - 안 걸러지면 X-T30 III 27개(Provia 20 + 다른 모드 7)
        # 그대로 섞여 들어갔던 버그가 재발한다.
        rows = [r for r in rows if r['film_mode'] == film_mode_filter]
    print(f"\n### {label} - 후보 {len(rows)}개 (원본 해상도, 다운샘플 없음) ###", flush=True)

    old_des, new_des = [], []
    for i, r in enumerate(rows):
        raw_path = os.path.join(RAW_DIR, r['raw_file'])
        jpg_path = os.path.join(RAW_DIR, r['jpeg_file'])
        if not (os.path.exists(raw_path) and os.path.exists(jpg_path)):
            continue
        try:
            # 완전 무제한(max_dim=100000)은 X2D II 100MP 등에서 float64
            # 중간 배열이 누적돼 OOM(exit 137)으로 죽는 걸 확인 - 지금까지
            # 쓴 200~400px보다 훨씬 크지만 안전한 상한(3000px)으로 낮춤
            neutral = load_neutral_render(raw_path, max_dim=3000)
        except Exception as e:
            print(f"  [{i+1}/{len(rows)}] {r['raw_file']} 디코드 실패: {e}", flush=True)
            continue
        target_img = cv2.imread(jpg_path)
        if target_img is None or not is_image_array_usable(target_img):
            continue
        target_lin = load_target_linear_native(jpg_path, neutral.shape[:2])

        old_out = old_fn(neutral)
        new_out = new_fn(neutral)
        old_de = mean_delta_e(bgr_u8_to_linear(old_out), target_lin)
        new_de = mean_delta_e(bgr_u8_to_linear(new_out), target_lin)
        old_des.append(old_de)
        new_des.append(new_de)
        print(f"  [{i+1}/{len(rows)}] {r['raw_file']} ({neutral.shape[1]}x{neutral.shape[0]}) "
              f"old={old_de:.3f} new={new_de:.3f}", flush=True)

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

    print(f"\n=== {label} 원본 해상도 재확인 (n={n}) ===")
    print(f"평균 기존 ΔE00={mean_old:.3f}  평균 신규 ΔE00={mean_new:.3f}  개선폭={improvement_pct:+.2f}%")
    print(f"승/패={wins}/{losses}")
    print(f"부트스트랩 95% CI(평균차)=[{ci_lo:+.3f}, {ci_hi:+.3f}]")
    if ci_lo <= 0 <= ci_hi:
        print("판정: 보류 (CI가 0 포함)")
    else:
        print(f"판정: {'신규 우세' if improvement_pct > 0 else '기존 우세'}")


def main():
    run("X2D II (apply_hncs vs apply_hncs_x2dii)",
        os.path.join(BASE, "datasets", "hasselblad", "dpreview_raw_jpeg_pairs_clean.csv"),
        "X2D II 100C",
        apply_hncs,
        apply_hncs_x2dii)

    run("Hasselblad X1D-50c (apply_hncs vs apply_hncs_x1d50c)",
        os.path.join(BASE, "datasets", "hasselblad", "hasselblad_new_pairs.csv"),
        "Hasselblad X1D-50c",
        apply_hncs,
        apply_hncs_x1d50c)

    run("Sony a7V (apply_sony_look vs apply_sony_a7v_look)",
        os.path.join(BASE, "datasets", "sony", "a7v_raw_jpeg_pairs_clean.csv"),
        None,
        apply_sony_look,
        apply_sony_a7v_look)

    run("Leica SL3-P (apply_leica_look vs apply_leica_raw_look)",
        os.path.join(BASE, "datasets", "leica", "sl3p_raw_jpeg_pairs_clean.csv"),
        None,
        apply_leica_look,
        apply_leica_raw_look)

    run("Leica Q3 43 (apply_leica_look vs apply_leica_raw_look)",
        os.path.join(BASE, "datasets", "leica", "q343_raw_jpeg_pairs_clean.csv"),
        None,
        apply_leica_look,
        apply_leica_raw_look)

    run("Leica SL2 (apply_leica_look vs apply_leica_raw_look)",
        os.path.join(BASE, "datasets", "leica", "leica_new_pairs.csv"),
        "LEICA SL2",
        apply_leica_look,
        apply_leica_raw_look)

    run("Leica M10 (apply_leica_look vs apply_leica_raw_look)",
        os.path.join(BASE, "datasets", "leica", "leica_new_pairs.csv"),
        "LEICA M10",
        apply_leica_look,
        apply_leica_raw_look)

    run("Fuji GFX100RF Provia (raw 무가공 vs apply_provia)",
        os.path.join(BASE, "datasets", "fuji", "fuji_new_pairs.csv"),
        "GFX100RF",
        _IDENTITY,
        apply_provia,
        film_mode_filter="F0/Standard (Provia)")

    run("Fuji X-T30 III Provia (raw 무가공 vs apply_provia)",
        os.path.join(BASE, "datasets", "fuji", "fuji_new_pairs.csv"),
        "X-T30 III",
        _IDENTITY,
        apply_provia,
        film_mode_filter="F0/Standard (Provia)")

    run("Sony a7R VI (apply_sony_look vs apply_sony_a7rvi_look)",
        os.path.join(BASE, "datasets", "sony", "sony_new_pairs.csv"),
        "ILCE-7RM6",
        apply_sony_look,
        apply_sony_a7rvi_look)

    run("Sigma BF (apply_sigma_look vs apply_sigma_bf_look)",
        os.path.join(BASE, "datasets", "sigma", "sigma_new_pairs.csv"),
        None,
        apply_sigma_look,
        apply_sigma_bf_look)


if __name__ == "__main__":
    main()
