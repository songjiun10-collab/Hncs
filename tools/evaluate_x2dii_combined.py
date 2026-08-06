"""
X2D II ΔE00 감소 후보 세 개(학습LUT/분리감마/채도-hue보정, 각각
tools/evaluate_x2dii_reduce_de00.py에서 apply_hncs_x2dii 대비 단독으로
유의미하게 이김 - +23.6%/+25.2%/+2.65%)를 조합했을 때 얼마나 더
낮아지는지 확인한다. 톤 단계(학습LUT vs 분리감마)는 같은 자리를 놓고
겹치는 대안이라 둘 다 채도/hue보정과만 각각 결합:

  콤보 A: 분리감마(shadow_gamma=0.4, highlight_gamma=0.3 - 이전 LOO에서
          41/41 폴드가 전부 이 값에 수렴했으므로 고정) + 채도/hue보정
          (LOO, 분리감마 출력 위에 다시 그리드서치 - 이전 실험의 채도
          그리드는 apply_hncs_x2dii 잔차에 맞춘 거라 재사용 안 함)
  콤보 B: X2D II 전용 학습LUT(LOO, 폴드마다 재학습) + 채도/hue보정
          (폴드마다 그 폴드의 학습LUT 출력 위에 다시 LOO 그리드서치 -
          중첩 LOO라 계산량이 큼)

apply_hncs_x2dii()는 baseline 비교용으로만 쓰고 수정 안 함.

  python3 -m tools.evaluate_x2dii_combined
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

DE00_MAX_DIM = 400
GRID_MAX_DIM = 160
LUT_PIXEL_MAX_DIM = 800

X2DII_TOE_LIFT, X2DII_SHOULDER_START, X2DII_WHITE_POINT, X2DII_CLAHE_CLIP = 0.02, 0.82, 0.95, 1.25
SPLIT_SHADOW_GAMMA, SPLIT_HIGHLIGHT_GAMMA = 0.4, 0.3  # 이전 LOO 41/41 수렴값

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


def apply_split_gamma_curve(img_bgr, shadow_gamma=SPLIT_SHADOW_GAMMA, highlight_gamma=SPLIT_HIGHLIGHT_GAMMA):
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    x = np.arange(256, dtype=np.float32) / 255.0
    with np.errstate(invalid="ignore"):
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


def apply_learned_lut_curve(img_bgr, lut_u8):
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=X2DII_CLAHE_CLIP, tileGridSize=(8, 8))
    l = clahe.apply(l)
    l = cv2.LUT(l, lut_u8)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def apply_chroma_correction(img_bgr, sat_mult, hue_shift_deg):
    rgb = img_bgr[:, :, ::-1].astype(np.float32) / 255.0
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    hsv[..., 0] = (hsv[..., 0] + hue_shift_deg) % 360.0
    hsv[..., 1] = np.clip(hsv[..., 1] * sat_mult, 0.0, 1.0)
    out_rgb = np.clip(cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB), 0.0, 1.0)
    return (out_rgb * 255 + 0.5).astype(np.uint8)[:, :, ::-1]


def build_learned_lut(train_names, lut_neutral_l, lut_target_l):
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
        return None
    xs = np.arange(256)
    lut_filled = np.interp(xs, xs[valid], lut[valid])
    return np.maximum.accumulate(lut_filled).astype(np.uint8)


def main():
    rows = [r for r in csv.DictReader(open(MANIFEST)) if r['model'] == 'X2D II 100C']
    pairs = []
    for r in rows:
        raw_path = os.path.join(RAW_DIR, r['raw_file'])
        jpg_path = os.path.join(RAW_DIR, r['jpeg_file'])
        if os.path.exists(raw_path) and os.path.exists(jpg_path):
            pairs.append(dict(name=r['raw_file'], raw_path=raw_path, target_path=jpg_path))
    n = len(pairs)
    print(f"X2D II 페어 {n}개 - 디코드중...", flush=True)

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

    names = [p['name'] for p in pairs]

    baseline_des = []
    for p in pairs:
        out = apply_hncs_x2dii(de00_neutral[p['name']])
        baseline_des.append(mean_delta_e(bgr_u8_to_linear(out), de00_target[p['name']]))
    print(f"\n베이스라인(apply_hncs_x2dii) 평균 ΔE00={np.mean(baseline_des):.3f}", flush=True)

    # === 콤보 A: 분리감마(고정) + 채도/hue LOO ===
    print("\n=== 콤보 A: 분리감마(고정) + 채도/hue LOO ===", flush=True)
    grid_split_out = {p['name']: apply_split_gamma_curve(grid_neutral[p['name']]) for p in pairs}
    de00_split_out = {p['name']: apply_split_gamma_curve(de00_neutral[p['name']]) for p in pairs}

    chroma_grid_de_a = np.zeros((len(CHROMA_COMBOS), n))
    for ci, (sat_mult, hue_shift) in enumerate(CHROMA_COMBOS):
        for pi, p in enumerate(pairs):
            out = apply_chroma_correction(grid_split_out[p['name']], sat_mult, hue_shift)
            chroma_grid_de_a[ci, pi] = mean_delta_e(bgr_u8_to_linear(out), grid_target[p['name']])
        if ci % 10 == 0:
            print(f"  콤보 {ci}/{len(CHROMA_COMBOS)}", flush=True)

    combo_a_des = []
    chosen_a = {}
    for i in range(n):
        train_mask = np.ones(n, dtype=bool)
        train_mask[i] = False
        best_ci = int(np.argmin(chroma_grid_de_a[:, train_mask].mean(axis=1)))
        chosen_a[CHROMA_COMBOS[best_ci]] = chosen_a.get(CHROMA_COMBOS[best_ci], 0) + 1
        out = apply_chroma_correction(de00_split_out[pairs[i]['name']], *CHROMA_COMBOS[best_ci])
        combo_a_des.append(mean_delta_e(bgr_u8_to_linear(out), de00_target[pairs[i]['name']]))

    summarize_and_print(baseline_des, combo_a_des, "콤보A(분리감마+채도)")
    print("폴드별 선택 채도 조합 상위:")
    for combo, cnt in sorted(chosen_a.items(), key=lambda kv: -kv[1])[:5]:
        print(f"  {cnt:3d}/{n}  sat_mult={combo[0]:.3f}, hue_shift={combo[1]:.2f}")

    # === 콤보 B: 학습LUT(폴드별 재학습) + 채도/hue LOO(중첩) ===
    print("\n=== 콤보 B: 학습LUT(폴드별) + 채도/hue LOO(중첩) ===", flush=True)
    combo_b_des = []
    chosen_b = {}
    for i, held_out in enumerate(pairs):
        train_names = [nm for nm in names if nm != held_out['name']]
        lut_u8 = build_learned_lut(train_names, lut_neutral_l, lut_target_l)
        if lut_u8 is None:
            combo_b_des.append(baseline_des[i])
            continue

        # 이 폴드의 학습LUT을 나머지 40쌍(저해상도)에 적용 -> 그 위에 채도그리드
        grid_lut_out = {nm: apply_learned_lut_curve(grid_neutral[nm], lut_u8) for nm in train_names}
        chroma_de = np.zeros((len(CHROMA_COMBOS), len(train_names)))
        for ci, (sat_mult, hue_shift) in enumerate(CHROMA_COMBOS):
            for pi, nm in enumerate(train_names):
                out = apply_chroma_correction(grid_lut_out[nm], sat_mult, hue_shift)
                chroma_de[ci, pi] = mean_delta_e(bgr_u8_to_linear(out), grid_target[nm])
        best_ci = int(np.argmin(chroma_de.mean(axis=1)))
        chosen_b[CHROMA_COMBOS[best_ci]] = chosen_b.get(CHROMA_COMBOS[best_ci], 0) + 1

        held_lut_out = apply_learned_lut_curve(de00_neutral[held_out['name']], lut_u8)
        out = apply_chroma_correction(held_lut_out, *CHROMA_COMBOS[best_ci])
        de = mean_delta_e(bgr_u8_to_linear(out), de00_target[held_out['name']])
        combo_b_des.append(de)
        print(f"  [{i+1}/{n}] {held_out['name']} ΔE00={de:.3f} (baseline={baseline_des[i]:.3f})",
              flush=True)

    summarize_and_print(baseline_des, combo_b_des, "콤보B(학습LUT+채도)")
    print("폴드별 선택 채도 조합 상위:")
    for combo, cnt in sorted(chosen_b.items(), key=lambda kv: -kv[1])[:5]:
        print(f"  {cnt:3d}/{n}  sat_mult={combo[0]:.3f}, hue_shift={combo[1]:.2f}")

    print(f"\n=== 요약 ===")
    print(f"베이스라인(apply_hncs_x2dii)         평균 ΔE00={np.mean(baseline_des):.3f}")
    print(f"콤보A(분리감마+채도)                 평균 ΔE00={np.mean(combo_a_des):.3f}")
    print(f"콤보B(학습LUT+채도)                  평균 ΔE00={np.mean(combo_b_des):.3f}")


if __name__ == "__main__":
    main()
