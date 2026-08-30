"""
tools/evaluate_x2dii_clahe_shoulder_grid.py에서 확인한 것처럼, raw+jpeg로
직접 캘리브레이션된 바디별 apply_* 함수들이 `clahe_clip=1.25`를 전부
population-fit 기본값에서 그대로 차용했을 뿐 한 번도 그리드서치 변수로
넣어본 적이 없다(각 파일 docstring에 "미검증"으로 명시돼 있음 - X2D II도
같은 상태였다가 재검증 결과 이미 최적값이었음을 확인). shoulder_start도
같이 흔들어서 상호작용이 있는지 같은 방법으로 raw+jpeg 데이터가 있는
나머지 바디 전부(사용자 지시 "브랜드 전체") 재검증한다.

exposure_gamma/toe_lift/white_point(있는 경우)는 각 바디에서 이미 별도로
확정된 값 그대로 고정 - 이번엔 shoulder_start x clahe_clip 2D만 훑는다.

  python3 -m tools.evaluate_all_brands_clahe_shoulder_grid
"""
import csv
import math
import os
import sys

import colour
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brands.fuji import apply_provia
from brands.hasselblad import apply_hncs
from brands.hasselblad_x1d50c import apply_hncs_x1d50c
from brands.leica import apply_leica_look
from brands.leica_raw import apply_leica_raw_look
from brands.sigma import apply_sigma_look
from brands.sigma_bf import apply_sigma_bf_look
from brands.sony import apply_sony_look
from brands.sony_a7rvi import apply_sony_a7rvi_look
from brands.sony_a7v import apply_sony_a7v_look
from tools.calibrate import load_neutral_render

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRID_MAX_DIM = 200
CONFIRM_MAX_DIM = 400  # tools/evaluate_x2dii_clahe_shoulder_grid.py와 동일 - 3000px는 너무 느림

_GS_SHOULDER_STARTS = (0.50, 0.58, 0.66, 0.70, 0.74, 0.78, 0.82)
_GS_CLAHE_CLIPS = (0.5, 1.0, 1.25, 1.5, 2.0, 3.0)
_IDENTITY = lambda img, **kw: img


def _build_filename_index(brand):
    idx = {}
    for base, _dirs, files in os.walk(os.path.join(BASE, "datasets", brand, "contributed")):
        for f in files:
            idx.setdefault(f, os.path.join(base, f))
    return idx


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


def _report(label, old, new, n):
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
    print(f"  {label} (n={n}): old={mean_old:.3f} new={mean_new:.3f} "
          f"개선폭={improvement_pct:+.2f}% 승/패={wins}/{losses} p={p_value:.4f} "
          f"CI=[{ci_lo:+.3f},{ci_hi:+.3f}]", flush=True)
    if ci_lo <= 0 <= ci_hi:
        verdict = "보류(CI가 0 포함)"
    else:
        verdict = "new 우세" if improvement_pct > 0 else "old(현재) 우세"
    print(f"    판정: {verdict}")
    return verdict


def verify_body(brand, label, manifest_path, model_filter, current_fn, baseline_fn,
                 fixed_kwargs, film_mode_filter=None):
    print(f"\n{'='*70}\n{label}\n{'='*70}", flush=True)
    rows = list(csv.DictReader(open(manifest_path)))
    key = 'model' if 'model' in rows[0] else 'camera'
    if model_filter:
        rows = [r for r in rows if r.get(key) == model_filter]
    if film_mode_filter:
        rows = [r for r in rows if r.get('film_mode') == film_mode_filter]
    index = _build_filename_index(brand)

    pairs = []
    for r in rows:
        raw_path = index.get(r['raw_file'])
        jpg_path = index.get(r['jpeg_file'])
        if not (raw_path and jpg_path):
            continue
        try:
            neutral_grid = load_neutral_render(raw_path, max_dim=GRID_MAX_DIM)
            neutral_confirm = load_neutral_render(raw_path, max_dim=CONFIRM_MAX_DIM)
        except Exception as e:
            print(f"  {r['raw_file']} 디코드 실패: {e}", flush=True)
            continue
        target_grid = load_target_linear(jpg_path, neutral_grid.shape[:2])
        target_confirm = load_target_linear(jpg_path, neutral_confirm.shape[:2])
        pairs.append(dict(name=r['raw_file'], neutral_grid=neutral_grid, target_grid=target_grid,
                           neutral_confirm=neutral_confirm, target_confirm=target_confirm))
    n = len(pairs)
    print(f"  로컬 페어 {n}개 (manifest {len(rows)}개 중)", flush=True)
    if n < 10:
        print("  표본 10 미만 - 스킵")
        return

    combos = [(ss, cc) for ss in _GS_SHOULDER_STARTS for cc in _GS_CLAHE_CLIPS]
    de00 = np.zeros((len(combos), n))
    for ci, (ss, cc) in enumerate(combos):
        for pi, p in enumerate(pairs):
            out = current_fn(p['neutral_grid'], **{**fixed_kwargs, 'shoulder_start': ss, 'clahe_clip': cc})
            de00[ci, pi] = mean_delta_e(bgr_u8_to_linear(out), p['target_grid'])

    baseline_des = np.array([mean_delta_e(
        bgr_u8_to_linear(baseline_fn(p['neutral_confirm'])), p['target_confirm']) for p in pairs])
    current_des = np.array([mean_delta_e(
        bgr_u8_to_linear(current_fn(p['neutral_confirm'])), p['target_confirm']) for p in pairs])

    loo_des = []
    chosen_counts = {}
    for i in range(n):
        train_mask = np.ones(n, dtype=bool)
        train_mask[i] = False
        best_ci = int(np.argmin(de00[:, train_mask].mean(axis=1)))
        chosen_counts[combos[best_ci]] = chosen_counts.get(combos[best_ci], 0) + 1
        ss, cc = combos[best_ci]
        out = current_fn(pairs[i]['neutral_confirm'],
                          **{**fixed_kwargs, 'shoulder_start': ss, 'clahe_clip': cc})
        loo_des.append(mean_delta_e(bgr_u8_to_linear(out), pairs[i]['target_confirm']))
    loo_des = np.array(loo_des)

    _report("LOO 그리드서치 vs 기존(main/population-fit/raw)", baseline_des, loo_des, n)
    _report("LOO 그리드서치 vs 현재 shipped 함수", current_des, loo_des, n)

    top = sorted(chosen_counts.items(), key=lambda kv: -kv[1])[:3]
    print("  폴드별 선택 조합 상위:", ", ".join(
        f"{cnt}/{n} ss={ss},clip={cc}" for (ss, cc), cnt in top))


def main():
    verify_body(
        "hasselblad", "Hasselblad X1D-50c (apply_hncs_x1d50c)",
        os.path.join(BASE, "datasets", "hasselblad", "hasselblad_new_pairs.csv"),
        "Hasselblad X1D-50c", apply_hncs_x1d50c, apply_hncs,
        dict(toe_lift=0.0, white_point=1.0, exposure_gamma=0.7))

    verify_body(
        "sony", "Sony a7V (apply_sony_a7v_look)",
        os.path.join(BASE, "datasets", "sony", "a7v_raw_jpeg_pairs_clean.csv"),
        None, apply_sony_a7v_look, apply_sony_look,
        dict(toe_lift=0.06, white_point=1.0))

    verify_body(
        "sony", "Sony a7R VI (apply_sony_a7rvi_look)",
        os.path.join(BASE, "datasets", "sony", "sony_new_pairs.csv"),
        "ILCE-7RM6", apply_sony_a7rvi_look, apply_sony_look,
        dict(toe_lift=0.09, white_point=0.85))

    verify_body(
        "leica", "Leica SL3-P (apply_leica_raw_look)",
        os.path.join(BASE, "datasets", "leica", "sl3p_raw_jpeg_pairs_clean.csv"),
        None, apply_leica_raw_look, apply_leica_look,
        dict(toe_lift=0.0, white_point=1.0))

    verify_body(
        "leica", "Leica Q3 43 (apply_leica_raw_look)",
        os.path.join(BASE, "datasets", "leica", "q343_raw_jpeg_pairs_clean.csv"),
        None, apply_leica_raw_look, apply_leica_look,
        dict(toe_lift=0.0, white_point=1.0))

    verify_body(
        "leica", "Leica SL2 (apply_leica_raw_look)",
        os.path.join(BASE, "datasets", "leica", "leica_new_pairs.csv"),
        "LEICA SL2", apply_leica_raw_look, apply_leica_look,
        dict(toe_lift=0.0, white_point=1.0))

    verify_body(
        "leica", "Leica M10 (apply_leica_raw_look)",
        os.path.join(BASE, "datasets", "leica", "leica_new_pairs.csv"),
        "LEICA M10", apply_leica_raw_look, apply_leica_look,
        dict(toe_lift=0.0, white_point=1.0))

    verify_body(
        "fuji", "Fuji GFX100RF Provia (apply_provia)",
        os.path.join(BASE, "datasets", "fuji", "fuji_new_pairs.csv"),
        "GFX100RF", apply_provia, _IDENTITY,
        dict(toe_lift=0.0, white_point=1.0),
        film_mode_filter="F0/Standard (Provia)")

    verify_body(
        "fuji", "Fuji X-T30 III Provia (apply_provia)",
        os.path.join(BASE, "datasets", "fuji", "fuji_new_pairs.csv"),
        "X-T30 III", apply_provia, _IDENTITY,
        dict(toe_lift=0.0, white_point=1.0),
        film_mode_filter="F0/Standard (Provia)")

    verify_body(
        "sigma", "Sigma BF (apply_sigma_bf_look)",
        os.path.join(BASE, "datasets", "sigma", "sigma_new_pairs.csv"),
        None, apply_sigma_bf_look, apply_sigma_look,
        dict(toe_lift=0.09, white_point=1.0))


if __name__ == "__main__":
    main()
