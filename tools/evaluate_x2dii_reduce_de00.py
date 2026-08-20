"""
apply_hncs_x2dii()의 실제 ΔE00 베이스라인을 재고, 더 낮출 수 있는 세
가지 후보를 X2D II 41쌍(전부 클린)에 LOO로 검증한다:

  0. 베이스라인: apply_hncs_x2dii(neutral) vs target, ΔE00
  1. X2D II 전용 학습 LUT (apply_hncs_learned 패턴, L채널 256bin 중앙값
     매핑을 X2D II 41쌍에만 - CFV가 학습LUT을 이기던 문제(고ISO 편차)가
     X2D II엔 없어서 재시도할 근거가 있음)
  2. 하이라이트/섀도우 분리 감마 (exposure_gamma 한 값 대신 중간톤
     기준으로 shadow_gamma/highlight_gamma 두 값 - X2D II가 요구하는
     감마(0.3)가 워낙 극단적이라 단일 전역 파워커브의 한계를 의심)
  3. 전역 채도/hue 보정 (apply_hncs_x2dii 톤커브 위에 HSV sat_mult/
     hue_shift만 얹음 - 매트릭스(공간 왜곡 전체)는 이미 기각됐지만
     더 작은 스코프의 색상 보정은 안 해봤음)

전부 apply_hncs_x2dii()(brands/hasselblad_x2dii.py)를 baseline으로 페어드
비교. apply_hncs()/apply_hncs_x2dii() 둘 다 이 실험으로 수정하지 않는다.

  python3 -m tools.evaluate_x2dii_reduce_de00
"""
import csv
import itertools
import math
import os
import sys

import colour
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brands.hasselblad_x2dii import apply_hncs_x2dii
from core.curve import film_curve
from tools.calibrate import load_neutral_render, _resize_to_max_dim

RAW_DIR = "/Users/songjiun/Documents/raw pair"
MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "datasets", "hasselblad", "dpreview_raw_jpeg_pairs_clean.csv")

DE00_MAX_DIM = 400          # ΔE00 이미지 비교용
LUT_PIXEL_MAX_DIM = 800     # 학습 LUT 픽셀 통계용 (calibrate.py run_learn_curve 관례)
GRID_MAX_DIM = 160          # LOO 그리드서치(다수 콤보 반복)용 초저해상도

X2DII_TOE_LIFT, X2DII_SHOULDER_START, X2DII_WHITE_POINT, X2DII_CLAHE_CLIP = 0.02, 0.82, 0.95, 1.25

SPLIT_GAMMAS = (0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0)
SPLIT_COMBOS = list(itertools.product(SPLIT_GAMMAS, SPLIT_GAMMAS))  # (shadow_gamma, highlight_gamma)

SAT_MULT_GRID = np.linspace(0.85, 1.15, 7)
HUE_SHIFT_GRID = np.linspace(-5.0, 5.0, 7)
CHROMA_COMBOS = list(itertools.product(SAT_MULT_GRID, HUE_SHIFT_GRID))


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


def summarize_and_print(baseline_des, other_des, label):
    baseline = np.array(baseline_des)
    other = np.array(other_des)
    diff = baseline - other
    n = len(diff)
    wins = int((diff > 0).sum())
    losses = int((diff < 0).sum())
    mean_baseline, mean_other = float(baseline.mean()), float(other.mean())
    improvement_pct = (mean_baseline - mean_other) / mean_baseline * 100.0

    rng = np.random.RandomState(0)
    boot = np.empty(20000)
    for i in range(20000):
        idx = rng.randint(0, n, n)
        boot[i] = diff[idx].mean()
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
    p = _sign_test_p(wins, losses)
    inconclusive = ci_lo <= 0 <= ci_hi

    print(f"\n=== {label} vs apply_hncs_x2dii (n={n}) ===")
    print(f"평균 apply_hncs_x2dii ΔE00={mean_baseline:.3f}  평균 {label} ΔE00={mean_other:.3f}  "
          f"개선폭={improvement_pct:+.2f}%")
    print(f"승/패={wins}/{losses}  부호검정 p={p:.4f}")
    print(f"부트스트랩 95% CI(평균차)=[{ci_lo:+.3f}, {ci_hi:+.3f}]")
    print("판정: 보류 (CI가 0 포함)" if inconclusive else
          f"판정: {label + ' 우세' if improvement_pct > 0 else 'apply_hncs_x2dii 우세'}")


def apply_split_gamma_curve(img_bgr, shadow_gamma, highlight_gamma):
    """apply_hncs_x2dii와 동일 구조(exposure LUT -> CLAHE -> film_curve),
    exposure 단계만 중간톤(0.5) 기준 이분 감마로 교체."""
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    x = np.arange(256, dtype=np.float32) / 255.0
    exp = np.where(x < 0.5,
                   0.5 * (x / 0.5) ** shadow_gamma,
                   0.5 + 0.5 * ((x - 0.5) / 0.5) ** highlight_gamma)
    exp_lut = np.clip(exp * 255, 0, 255).astype(np.uint8)
    l = cv2.LUT(l, exp_lut)

    clahe = cv2.createCLAHE(clipLimit=X2DII_CLAHE_CLIP, tileGridSize=(8, 8))
    l = clahe.apply(l)

    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(film_curve(x, X2DII_TOE_LIFT, X2DII_SHOULDER_START, X2DII_WHITE_POINT) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def apply_chroma_correction(img_bgr, sat_mult, hue_shift_deg):
    """apply_hncs_x2dii 출력 위에 HSV sat_mult/hue_shift만 얹는다."""
    rgb = img_bgr[:, :, ::-1].astype(np.float32) / 255.0
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    hsv[..., 0] = (hsv[..., 0] + hue_shift_deg) % 360.0
    hsv[..., 1] = np.clip(hsv[..., 1] * sat_mult, 0.0, 1.0)
    out_rgb = np.clip(cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB), 0.0, 1.0)
    return (out_rgb * 255 + 0.5).astype(np.uint8)[:, :, ::-1]


def main():
    rows = [r for r in csv.DictReader(open(MANIFEST)) if r['model'] == 'X2D II 100C']
    print(f"X2D II 페어 {len(rows)}개", flush=True)

    pairs = []
    for i, r in enumerate(rows):
        raw_path = os.path.join(RAW_DIR, r['raw_file'])
        jpg_path = os.path.join(RAW_DIR, r['jpeg_file'])
        if os.path.exists(raw_path) and os.path.exists(jpg_path):
            pairs.append(dict(name=r['raw_file'], raw_path=raw_path, target_path=jpg_path))
    n = len(pairs)
    print(f"사용 가능한 페어: {n}개 - 디코드중...", flush=True)

    de00_neutral, de00_target = {}, {}
    grid_neutral, grid_target = {}, {}
    lut_neutral_l, lut_target_l = {}, {}

    for i, p in enumerate(pairs):
        neutral_de = load_neutral_render(p['raw_path'], max_dim=DE00_MAX_DIM)
        de00_neutral[p['name']] = neutral_de
        de00_target[p['name']] = load_target_linear(p['target_path'], neutral_de.shape[:2])

        neutral_grid = load_neutral_render(p['raw_path'], max_dim=GRID_MAX_DIM)
        grid_neutral[p['name']] = neutral_grid
        grid_target[p['name']] = load_target_linear(p['target_path'], neutral_grid.shape[:2])

        neutral_lut = load_neutral_render(p['raw_path'], max_dim=LUT_PIXEL_MAX_DIM)
        target_lut = _resize_to_max_dim(cv2.imread(p['target_path']), LUT_PIXEL_MAX_DIM)
        target_lut = cv2.resize(target_lut, (neutral_lut.shape[1], neutral_lut.shape[0]),
                                 interpolation=cv2.INTER_AREA)
        lut_neutral_l[p['name']] = cv2.cvtColor(neutral_lut, cv2.COLOR_BGR2LAB)[:, :, 0]
        lut_target_l[p['name']] = cv2.cvtColor(target_lut, cv2.COLOR_BGR2LAB)[:, :, 0]

        print(f"  [{i+1}/{n}] {p['name']} 디코드 완료", flush=True)

    # === 0. 베이스라인: apply_hncs_x2dii ===
    baseline_des = []
    for p in pairs:
        out = apply_hncs_x2dii(de00_neutral[p['name']])
        baseline_des.append(mean_delta_e(bgr_u8_to_linear(out), de00_target[p['name']]))
    print(f"\n=== 0. apply_hncs_x2dii 베이스라인 (n={n}) ===")
    print(f"평균 ΔE00={np.mean(baseline_des):.3f}  중앙값={np.median(baseline_des):.3f}")

    # === 1. X2D II 전용 학습 LUT (LOO) ===
    print("\n1. X2D II 전용 학습 LUT LOO 계산중...", flush=True)
    names = [p['name'] for p in pairs]
    lut_des = []
    for i, held_out in enumerate(pairs):
        train_names = [nm for nm in names if nm != held_out['name']]
        neutral_l_all = np.concatenate([lut_neutral_l[nm].ravel() for nm in train_names])
        target_l_all = np.concatenate([lut_target_l[nm].ravel() for nm in train_names])

        lut = np.zeros(256, dtype=np.float32)
        counts = np.zeros(256, dtype=np.int64)
        for v in range(256):
            mask = neutral_l_all == v
            counts[v] = mask.sum()
            if counts[v] > 0:
                lut[v] = np.median(target_l_all[mask])
        valid = counts > 20
        if valid.sum() < 2:
            lut_des.append(baseline_des[i])
            continue
        xs = np.arange(256)
        lut_filled = np.interp(xs, xs[valid], lut[valid])
        lut_mono = np.maximum.accumulate(lut_filled).astype(np.uint8)

        neutral = de00_neutral[held_out['name']]
        lab = cv2.cvtColor(neutral, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=X2DII_CLAHE_CLIP, tileGridSize=(8, 8))
        l = clahe.apply(l)
        l = cv2.LUT(l, lut_mono)
        out = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
        lut_des.append(mean_delta_e(bgr_u8_to_linear(out), de00_target[held_out['name']]))
        print(f"  [{i+1}/{n}] {held_out['name']} ΔE00={lut_des[-1]:.3f} "
              f"(baseline={baseline_des[i]:.3f})", flush=True)

    summarize_and_print(baseline_des, lut_des, "X2D II 전용 학습LUT")

    # === 2. 하이라이트/섀도우 분리 감마 (LOO, 저해상도 그리드) ===
    print(f"\n2. 분리감마 LOO 계산중 ({len(SPLIT_COMBOS)}콤보 x {n}쌍, 저해상도)...", flush=True)
    split_grid_de = np.zeros((len(SPLIT_COMBOS), n))
    for ci, (sg, hg) in enumerate(SPLIT_COMBOS):
        for pi, p in enumerate(pairs):
            out = apply_split_gamma_curve(grid_neutral[p['name']], sg, hg)
            split_grid_de[ci, pi] = mean_delta_e(bgr_u8_to_linear(out), grid_target[p['name']])
        if ci % 10 == 0:
            print(f"  콤보 {ci}/{len(SPLIT_COMBOS)}", flush=True)

    split_des = []
    chosen_split = {}
    for i in range(n):
        train_mask = np.ones(n, dtype=bool)
        train_mask[i] = False
        train_means = split_grid_de[:, train_mask].mean(axis=1)
        best_ci = int(np.argmin(train_means))
        chosen_split[SPLIT_COMBOS[best_ci]] = chosen_split.get(SPLIT_COMBOS[best_ci], 0) + 1
        out = apply_split_gamma_curve(de00_neutral[pairs[i]['name']], *SPLIT_COMBOS[best_ci])
        split_des.append(mean_delta_e(bgr_u8_to_linear(out), de00_target[pairs[i]['name']]))

    summarize_and_print(baseline_des, split_des, "분리감마")
    print("폴드별 선택 조합 상위:")
    for combo, cnt in sorted(chosen_split.items(), key=lambda kv: -kv[1])[:5]:
        print(f"  {cnt:3d}/{n}  shadow_gamma={combo[0]}, highlight_gamma={combo[1]}")

    # === 3. 전역 채도/hue 보정 (apply_hncs_x2dii 위에, LOO 저해상도 그리드) ===
    print(f"\n3. 채도/hue 보정 LOO 계산중 ({len(CHROMA_COMBOS)}콤보 x {n}쌍, 저해상도)...", flush=True)
    grid_x2dii_out = {p['name']: apply_hncs_x2dii(grid_neutral[p['name']]) for p in pairs}
    chroma_grid_de = np.zeros((len(CHROMA_COMBOS), n))
    for ci, (sat_mult, hue_shift) in enumerate(CHROMA_COMBOS):
        for pi, p in enumerate(pairs):
            out = apply_chroma_correction(grid_x2dii_out[p['name']], sat_mult, hue_shift)
            chroma_grid_de[ci, pi] = mean_delta_e(bgr_u8_to_linear(out), grid_target[p['name']])

    chroma_des = []
    chosen_chroma = {}
    de00_x2dii_out = {p['name']: apply_hncs_x2dii(de00_neutral[p['name']]) for p in pairs}
    for i in range(n):
        train_mask = np.ones(n, dtype=bool)
        train_mask[i] = False
        train_means = chroma_grid_de[:, train_mask].mean(axis=1)
        best_ci = int(np.argmin(train_means))
        chosen_chroma[CHROMA_COMBOS[best_ci]] = chosen_chroma.get(CHROMA_COMBOS[best_ci], 0) + 1
        out = apply_chroma_correction(de00_x2dii_out[pairs[i]['name']], *CHROMA_COMBOS[best_ci])
        chroma_des.append(mean_delta_e(bgr_u8_to_linear(out), de00_target[pairs[i]['name']]))

    summarize_and_print(baseline_des, chroma_des, "채도/hue보정")
    print("폴드별 선택 조합 상위:")
    for combo, cnt in sorted(chosen_chroma.items(), key=lambda kv: -kv[1])[:5]:
        print(f"  {cnt:3d}/{n}  sat_mult={combo[0]:.3f}, hue_shift={combo[1]:.2f}")


if __name__ == "__main__":
    main()
