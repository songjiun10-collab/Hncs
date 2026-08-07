"""
X2D II 70쌍 그리드서치를 ΔE00(CIEDE2000) 자체를 목적함수로 다시 돌린다 -
지금까지 apply_hncs_x2dii()의 모든 검증(evaluate_x2dii_generation_loo.py
등)이 b2/w995 percentile RMSE 기준이었는데, apply_hncs()(main) 대
apply_hncs_x2dii()를 원본 해상도 ΔE00으로 직접 맞대결시켜보니 오히려
보류(-5.13%, CI가 0 포함, tools/evaluate_full_pixel_de00_confirm.py)로
나왔다 - Sony a7V 때 겪은 것과 같은 목적함수 문제가 X2D II 핵심
파라미터(exposure_gamma/shoulder_start)에도 있었다는 뜻. ΔE00을 직접
목적함수로 그리드서치를 재검증한다.

  python3 -m tools.evaluate_x2dii_de00_grid
"""
import csv
import math
import os
import sys

import colour
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brands.hasselblad import apply_hncs
from tools.calibrate import load_neutral_render, _grid_search_combos

RAW_DIR = "/Users/songjiun/Documents/raw pair"
MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "datasets", "hasselblad", "dpreview_raw_jpeg_pairs_clean.csv")

GRID_MAX_DIM = 200
CONFIRM_MAX_DIM = 3000  # tools/evaluate_full_pixel_de00_confirm.py와 동일 상한(OOM 방지)


def load_target_linear(jpg_path, shape_hw):
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


def main():
    rows = [r for r in csv.DictReader(open(MANIFEST)) if r['model'] == 'X2D II 100C']
    print(f"X2D II 페어 {len(rows)}개", flush=True)

    pairs = []
    for i, r in enumerate(rows):
        raw_path = os.path.join(RAW_DIR, r['raw_file'])
        jpg_path = os.path.join(RAW_DIR, r['jpeg_file'])
        if not (os.path.exists(raw_path) and os.path.exists(jpg_path)):
            continue
        try:
            neutral_grid = load_neutral_render(raw_path, max_dim=GRID_MAX_DIM)
            neutral_confirm = load_neutral_render(raw_path, max_dim=CONFIRM_MAX_DIM)
        except Exception as e:
            print(f"  [{i+1}/{len(rows)}] {r['raw_file']} 디코드 실패: {e}", flush=True)
            continue
        target_grid = load_target_linear(jpg_path, neutral_grid.shape[:2])
        target_confirm = load_target_linear(jpg_path, neutral_confirm.shape[:2])
        pairs.append(dict(name=r['raw_file'], neutral_grid=neutral_grid, target_grid=target_grid,
                           neutral_confirm=neutral_confirm, target_confirm=target_confirm))
        print(f"  [{i+1}/{len(rows)}] {r['raw_file']} 등록", flush=True)

    n = len(pairs)
    print(f"\n사용 가능한 페어: {n}개", flush=True)

    combos = _grid_search_combos()  # (exposure_gamma, toe_lift, shoulder_start, white_point), 441개
    print(f"\n{len(combos)}개 조합 x {n}쌍 - ΔE00 행렬 계산중(저해상도)...", flush=True)
    de00 = np.zeros((len(combos), n))
    for ci, (eg, tl, ss, wp) in enumerate(combos):
        for pi, p in enumerate(pairs):
            out = apply_hncs(p['neutral_grid'], toe_lift=tl, shoulder_start=ss,
                              white_point=wp, exposure_gamma=eg)
            de00[ci, pi] = mean_delta_e(bgr_u8_to_linear(out), p['target_grid'])
        if ci % 50 == 0:
            print(f"  콤보 {ci}/{len(combos)}", flush=True)

    main_des = []
    for p in pairs:
        out = apply_hncs(p['neutral_confirm'])  # main 기본값
        main_des.append(mean_delta_e(bgr_u8_to_linear(out), p['target_confirm']))
    main_des = np.array(main_des)

    print(f"\n=== LOO 검증({n}폴드, 선택은 저해상도 / 평가는 3000px) ===", flush=True)
    loo_des = []
    chosen_counts = {}
    for i in range(n):
        train_mask = np.ones(n, dtype=bool)
        train_mask[i] = False
        best_ci = int(np.argmin(de00[:, train_mask].mean(axis=1)))
        chosen_counts[combos[best_ci]] = chosen_counts.get(combos[best_ci], 0) + 1
        eg, tl, ss, wp = combos[best_ci]
        out = apply_hncs(pairs[i]['neutral_confirm'], toe_lift=tl, shoulder_start=ss,
                          white_point=wp, exposure_gamma=eg)
        de = mean_delta_e(bgr_u8_to_linear(out), pairs[i]['target_confirm'])
        loo_des.append(de)
        print(f"  [{i+1}/{n}] {pairs[i]['name']} ΔE00={de:.3f} (main={main_des[i]:.3f})", flush=True)

    loo_des = np.array(loo_des)
    diff = main_des - loo_des
    wins = int((diff > 0).sum())
    losses = int((diff < 0).sum())
    mean_main, mean_new = float(main_des.mean()), float(loo_des.mean())
    improvement_pct = (mean_main - mean_new) / mean_main * 100.0

    rng = np.random.RandomState(0)
    boot = np.empty(20000)
    for i in range(20000):
        idx = rng.randint(0, n, n)
        boot[i] = diff[idx].mean()
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
    p_value = _sign_test_p(wins, losses)

    print(f"\n=== X2D II: LOO ΔE00 그리드서치 vs apply_hncs(main) (n={n}) ===")
    print(f"평균 main ΔE00={mean_main:.3f}  평균 LOO ΔE00={mean_new:.3f}  개선폭={improvement_pct:+.2f}%")
    print(f"승/패={wins}/{losses}  부호검정 p={p_value:.4f}")
    print(f"부트스트랩 95% CI(평균차)=[{ci_lo:+.3f}, {ci_hi:+.3f}]")
    if ci_lo <= 0 <= ci_hi:
        print("판정: 보류 (CI가 0 포함)")
    else:
        print(f"판정: {'LOO 그리드서치 우세' if improvement_pct > 0 else 'main 우세'}")

    print("\n폴드별 선택 조합 상위:")
    for combo, cnt in sorted(chosen_counts.items(), key=lambda kv: -kv[1])[:5]:
        print(f"  {cnt:3d}/{n}  exposure_gamma={combo[0]}, toe_lift={combo[1]}, "
              f"shoulder_start={combo[2]}, white_point={combo[3]}")


if __name__ == "__main__":
    main()
