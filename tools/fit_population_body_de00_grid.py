"""
/goal "다른 전체 브랜드 평균 e00->10미만으로" - population-fit 브랜드
(toe_lift/shoulder_start/white_point/clahe_clip 4파라미터, make_population_fit_look
구조)에 ΔE00 직접 목적함수 그리드서치+LOO를 브랜드별로 돌려서 현재
generic apply_*_look 대비 얼마나 좁혀지는지 확인한다. X2D II/X1D-50c 등에서
쓴 것과 같은 방법론(200px 콤보 선택, 400px LOO 확정) - 다른 점은 population-fit
쪽엔 exposure_gamma가 없어서 4파라미터만 훑는다.

  python3 -m tools.fit_population_body_de00_grid <brand> [model_filter]

**정정(2026-09-01)**: "기존" 대비값을 (toe=0.0, ss=0.5, wp=1.0, clip=1.25)로
하드코딩했었는데, 이건 어느 브랜드의 실제 shipped 상수와도 일치하지
않는 임의값이었다(예: `brands/sony.py`의 실제 값은 toe=9.1/255,
ss=0.78, wp=228.6/255) - 그리드서치가 고르는 최적 콤보 자체는 이
버그와 무관(항상 실측 ΔE00을 최소화하는 콤보를 고름)하지만, 출력에
찍히는 "개선폭"/"판정"은 허수아비 대비였다. 이번 세션의 Canon 결과
(23.109→22.041, +4.62%)는 그 최적 콤보 자체가 이후
`fit_canon_deployable_pipeline.py`에서 재검증됐으므로 안전하지만,
이 정정 이전에 다른 브랜드에 이 스크립트를 돌려 "판정: 개선/보류"
문구만 보고 결론 낸 적이 있다면 재확인 필요. 이제 `brands.<brand>`의
실제 `apply_<brand>_look()`을 직접 호출해서 비교한다."""
import csv
import itertools
import math
import os
import sys
import time
import multiprocessing

import colour
import cv2
import importlib
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine import apply_population_fit_look
from core.validation import is_image_array_usable
from tools.calibrate import load_neutral_render

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRID_MAX_DIM = 200
CONFIRM_MAX_DIM = 400

_GS_TOE_LIFTS = (0.0, 0.02, 0.09)
_GS_SHOULDER_STARTS = (0.50, 0.58, 0.66, 0.70, 0.74, 0.78, 0.82)
_GS_WHITE_POINTS = (0.85, 0.95, 1.0)
_GS_CLAHE_CLIPS = (1.0, 1.25, 2.0, 3.0)
COMBOS = list(itertools.product(_GS_TOE_LIFTS, _GS_SHOULDER_STARTS, _GS_WHITE_POINTS, _GS_CLAHE_CLIPS))  # 252개

N_FOLDS = 5


def collect_contributed_pairs(brand, model_filter=None):
    base = os.path.join(BASE, "datasets", brand, "contributed")
    pairs = []
    seen = set()
    if not os.path.isdir(base):
        return pairs
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


def _decode_pair(r):
    try:
        neutral_grid = load_neutral_render(r["raw_path"], max_dim=GRID_MAX_DIM)
        neutral_confirm = load_neutral_render(r["raw_path"], max_dim=CONFIRM_MAX_DIM)
        target_img = cv2.imread(r["jpeg_path"])
        if target_img is None or not is_image_array_usable(target_img):
            return r["name"], None, None, None, None, "target jpeg unusable"
        target_grid = load_target_linear(r["jpeg_path"], neutral_grid.shape[:2])
        target_confirm = load_target_linear(r["jpeg_path"], neutral_confirm.shape[:2])
    except Exception as e:
        return r["name"], None, None, None, None, str(e)
    return r["name"], neutral_grid, target_grid, neutral_confirm, target_confirm, None


def main():
    brand = sys.argv[1]
    model_filter = sys.argv[2] if len(sys.argv) > 2 else None
    rows = collect_contributed_pairs(brand, model_filter)
    print(f"{brand} {model_filter or '(all)'}: manifest {len(rows)}개", flush=True)

    t0 = time.time()
    pairs = []
    with multiprocessing.Pool(3) as pool:
        for i, (name, ng, tg, nc, tc, err) in enumerate(pool.imap_unordered(_decode_pair, rows)):
            if err:
                print(f"  {name} 실패: {err}", flush=True)
                continue
            pairs.append(dict(name=name, neutral_grid=ng, target_grid=tg,
                               neutral_confirm=nc, target_confirm=tc))
            if (i + 1) % 20 == 0:
                print(f"  디코드 {i+1}/{len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    n = len(pairs)
    print(f"디코드 완료: {n}개 ({time.time()-t0:.0f}s)", flush=True)
    if n < 10:
        print("표본 부족, 종료")
        return

    print(f"그리드: {len(COMBOS)}콤보 x {n}쌍 (저해상도 선택)", flush=True)
    de00 = np.zeros((len(COMBOS), n))
    t1 = time.time()
    for ci, (tl, ss, wp, cc) in enumerate(COMBOS):
        for pi, p in enumerate(pairs):
            out = apply_population_fit_look(p['neutral_grid'], tl, ss, wp, cc)
            de00[ci, pi] = mean_delta_e(bgr_u8_to_linear(out), p['target_grid'])
        if ci % 100 == 0:
            print(f"  콤보 {ci}/{len(COMBOS)} ({time.time()-t1:.0f}s)", flush=True)
    print(f"그리드 완료 ({time.time()-t1:.0f}s)", flush=True)

    # 실제 shipped apply_<brand>_look()을 직접 호출 - 이전에는 (0.0, 0.5,
    # 1.0, 1.25)를 "기존"으로 하드코딩했었는데, 이건 어느 브랜드의 실제
    # 상수와도 안 맞는 임의값이라(예: Sony 실제 _TOE_LIFT=9.1/255,
    # _SHOULDER_START=0.78, _WHITE_POINT=228.6/255) "개선폭"이 진짜
    # 배포된 함수 대비가 아니라 허수아비 대비였다 - 정정(2026-09-01).
    shipped_look = getattr(importlib.import_module(f"brands.{brand}"), f"apply_{brand}_look")
    baseline_des = np.array([mean_delta_e(
        bgr_u8_to_linear(shipped_look(p['neutral_confirm'])),
        p['target_confirm']) for p in pairs])

    folds = np.array_split(np.random.RandomState(0).permutation(n), N_FOLDS)
    loo_des = np.zeros(n)
    chosen = {}
    for fi, test_idx in enumerate(folds):
        train_mask = np.ones(n, dtype=bool)
        train_mask[test_idx] = False
        best_ci = int(np.argmin(de00[:, train_mask].mean(axis=1)))
        chosen[COMBOS[best_ci]] = chosen.get(COMBOS[best_ci], 0) + 1
        tl, ss, wp, cc = COMBOS[best_ci]
        for i in test_idx:
            out = apply_population_fit_look(pairs[i]['neutral_confirm'], tl, ss, wp, cc)
            loo_des[i] = mean_delta_e(bgr_u8_to_linear(out), pairs[i]['target_confirm'])
        print(f"  fold {fi+1}/{N_FOLDS} best={COMBOS[best_ci]}", flush=True)

    diff = baseline_des - loo_des
    wins = int((diff > 0).sum())
    losses = int((diff < 0).sum())
    mean_base, mean_loo = float(baseline_des.mean()), float(loo_des.mean())
    improvement = (mean_base - mean_loo) / mean_base * 100.0
    rng = np.random.RandomState(0)
    boot = np.array([diff[rng.randint(0, n, n)].mean() for _ in range(20000)])
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
    p_val = _sign_test_p(wins, losses)

    print(f"\n=== {brand} {model_filter or '(all)'} 결과 (n={n}) ===")
    print(f"기존(shipped apply_{brand}_look) ΔE00={mean_base:.3f}  LOO 최적화 ΔE00={mean_loo:.3f}  개선폭={improvement:+.2f}%")
    print(f"승/패={wins}/{losses}  부호검정 p={p_val:.4f}  부트스트랩 95% CI=[{ci_lo:+.3f},{ci_hi:+.3f}]")
    print("판정:", "보류(CI 0 포함)" if ci_lo <= 0 <= ci_hi else ("개선" if improvement > 0 else "악화"))
    top = sorted(chosen.items(), key=lambda kv: -kv[1])[:3]
    print("폴드별 선택 조합 상위:", ", ".join(f"{cnt}/{N_FOLDS} {combo}" for combo, cnt in top))


if __name__ == "__main__":
    main()
