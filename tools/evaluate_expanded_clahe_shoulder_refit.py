"""
tools/evaluate_all_brands_clahe_shoulder_grid.py는 datasets/<brand>/*_new_pairs.csv
같은 별도 플랫 CSV(raw_file/jpeg_file/model 3컬럼)를 읽어서, 이번 세션에
datasets/<brand>/contributed/dpreview-*-2026-08/manifest.csv로 새로 추가한
GFX100RF(+63)/Sony a7V(+62)/Leica SL3-P(+15) 데이터를 못 본다. 이 스크립트는
같은 shoulder_start x clahe_clip 42콤보 그리드를 이번엔
datasets/<brand>/contributed/*/manifest.csv 전부(filename_raw/filename_jpeg/
camera 스키마, 하셀블라드 collect_local_pairs()와 같은 dedup 로직)에서
읽어서 확장된 표본으로 재확인한다.

  python3 -m tools.evaluate_expanded_clahe_shoulder_refit
"""
import csv
import itertools
import math
import os
import subprocess
import sys

import colour
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brands.fuji import apply_provia
from brands.leica import apply_leica_look
from brands.leica_raw import apply_leica_raw_look
from brands.sony import apply_sony_look
from brands.sony_a7v import apply_sony_a7v_look
from tools.calibrate import load_neutral_render

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRID_MAX_DIM = 200
CONFIRM_MAX_DIM = 400

_GS_SHOULDER_STARTS = (0.50, 0.58, 0.66, 0.70, 0.74, 0.78, 0.82)
_GS_CLAHE_CLIPS = (0.5, 1.0, 1.25, 1.5, 2.0, 3.0)
_IDENTITY = lambda img, **kw: img


def _exif_film_mode(jpg_path):
    out = subprocess.run(["exiftool", "-s3", "-FilmMode", jpg_path],
                          capture_output=True, text=True, timeout=30)
    return out.stdout.strip()


def collect_contributed_pairs(brand, model_filter=None, film_mode_filter=None):
    """collect_local_pairs()와 같은 dedup(filename_raw 기준, 먼저 나온 세트
    우선) - 하셀블라드 전용이던 걸 브랜드 인자로 일반화. film_mode_filter는
    이 manifest 스키마엔 film_mode 컬럼이 없어서(fuji_new_pairs.csv류
    별도 CSV에만 있음) EXIF FilmMode를 직접 읽어 확인한다."""
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
    verdict = "보류(CI가 0 포함)" if ci_lo <= 0 <= ci_hi else ("new 우세" if improvement_pct > 0 else "old(현재) 우세")
    print(f"    판정: {verdict}")


def verify_body(brand, label, model_filter, current_fn, baseline_fn, fixed_kwargs, film_mode_filter=None):
    print(f"\n{'='*70}\n{label}\n{'='*70}", flush=True)
    rows = collect_contributed_pairs(brand, model_filter, film_mode_filter)
    print(f"  manifest 기준 {len(rows)}개", flush=True)

    pairs = []
    for r in rows:
        try:
            neutral_grid = load_neutral_render(r["raw_path"], max_dim=GRID_MAX_DIM)
            neutral_confirm = load_neutral_render(r["raw_path"], max_dim=CONFIRM_MAX_DIM)
        except Exception as e:
            print(f"  {r['name']} 디코드 실패: {e}", flush=True)
            continue
        target_grid = load_target_linear(r["jpeg_path"], neutral_grid.shape[:2])
        target_confirm = load_target_linear(r["jpeg_path"], neutral_confirm.shape[:2])
        pairs.append(dict(name=r["name"], neutral_grid=neutral_grid, target_grid=target_grid,
                           neutral_confirm=neutral_confirm, target_confirm=target_confirm))
    n = len(pairs)
    print(f"  로컬 페어 {n}개", flush=True)
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
        out = current_fn(pairs[i]['neutral_confirm'], **{**fixed_kwargs, 'shoulder_start': ss, 'clahe_clip': cc})
        loo_des.append(mean_delta_e(bgr_u8_to_linear(out), pairs[i]['target_confirm']))
    loo_des = np.array(loo_des)

    _report("LOO 그리드서치 vs 기존(main/population-fit/raw)", baseline_des, loo_des, n)
    _report("LOO 그리드서치 vs 현재 shipped 함수", current_des, loo_des, n)

    top = sorted(chosen_counts.items(), key=lambda kv: -kv[1])[:3]
    print("  폴드별 선택 조합 상위:", ", ".join(f"{cnt}/{n} ss={ss},clip={cc}" for (ss, cc), cnt in top))


def main():
    verify_body("fuji", "Fuji GFX100RF Provia (apply_provia) - 확장 표본",
                "GFX100RF", apply_provia, _IDENTITY,
                dict(toe_lift=0.0, white_point=1.0), film_mode_filter="F0/Standard (Provia)")

    verify_body("sony", "Sony a7V (apply_sony_a7v_look) - 확장 표본",
                "ILCE-7M5", apply_sony_a7v_look, apply_sony_look,
                dict(toe_lift=0.06, white_point=1.0))

    verify_body("leica", "Leica SL3-P (apply_leica_raw_look) - 확장 표본",
                "LEICA SL3-P", apply_leica_raw_look, apply_leica_look,
                dict(toe_lift=0.0, white_point=1.0))


if __name__ == "__main__":
    main()
