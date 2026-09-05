"""Classic Negative를 **검증된 파라미터 계열**로 재적합해 v2 후보를 만든다.

**왜 계열을 바꾸나**: `tools/recalibrate_fuji_classic_negative.py`(현행 계열
그대로 재보정)는 ΔE00 15.2250 -> 8.6978(+42.87%, 46승1패,
CI [+5.7623,+7.2889])로 성공 기준을 통과했지만, 네 파라미터가 **전부 격자
경계**에 붙었다(`sat_mult` 0.45 하한, `contrast_n` 1.0 하한, `black_lift`
0.12 상한, `white_point` 1.18 상한). 진단 결과 원인이 룩이 아니었다:

- `tools/diagnose_fuji_neutral_render_offset.py`: `load_neutral_render()`
  출력이 카메라 JPEG보다 Lab L 중앙값 기준 크게 어둡다(47/47쌍, 부트스트랩
  95% CI가 0 배제). `tools/calibrate.py:130`의 `no_auto_bright=True` 때문인
  의도된 "무가공 베이스라인"이다.
- `tools/diagnose_fuji_autobright_vs_look.py`: 그렇다고 auto-bright를 켜도
  현행 상수 ΔE00은 일부만 줄어든다(부트스트랩 95% CI가 0 배제하나 폭이
  작음) - 하이라이트 정규화라 미드톤 격차는 남는다.

즉 현행 계열(하드 S커브 + `black_lift`/`white_point` 리맵)은 네 노브를 전부
전역 레벨 맞추기에 소모한다. 반면 같은 GFX50S II 세트를 같은
`load_neutral_render` 경로로 적합한 `apply_provia`,
`apply_classic_chrome_v2`, `apply_nostalgic_neg_v3`는 전부
`toe_lift=0.0/white_point=1.0`으로 수렴했다 - 밝기 리프트를 아예 안 쓴다.
`core.curve.film_curve`는 `white_point <= 1.0`이라 **구조적으로 밝기를 올릴
수 없어서** 경계 탈출이 불가능하다.

**따라서**: CLAHE + `film_curve(toe_lift, shoulder_start, white_point)`
계열에 Classic Negative의 핵심인 채도(`sat_mult`)를 4번째 축으로 붙여
재적합한다. `apply_classic_chrome`->`_v2` 전례와 같은 형태다.

**성공 기준(결과 보기 전에 확정)**: 5-fold 교차검증 홀드아웃에서 이미지별
ΔE00을 현행 `apply_classic_negative`와 페어드로 비교해 **부트스트랩 95%
CI(20000회, 고정 시드)가 0을 배제하고 v2 후보가 우세할 때만** v2 추가를
권고한다. CI가 0을 포함하면 판정 보류. 추가로 **최종 상수가 격자 경계에
붙으면** 그 자체를 실패 신호로 보고한다 - 경계 탈출은 모델 형태가 데이터에
안 맞는다는 뜻이기 때문이다.

**주의**: 이 스크립트는 `brands/fuji.py`를 수정하지 않는다. v2 함수를 실제로
추가할지는 사용자의 별도 결정이다.

  ~/.hncs-hybrid-venv312/bin/python3 -m tools.evaluate_fuji_classic_negative_v2_grid
"""
import csv
import json
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from brands.fuji import apply_classic_negative
from core.curve import film_curve
from hybrid_engine.utils.evaluate import bgr_u8_to_linear_rgb, mean_delta_e
from tools.calibrate import load_neutral_render

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SET_DIR = os.path.join(BASE, "datasets", "fuji", "contributed", "local-work-2026-08")
FILM_MODE = "Classic Negative"

GRID_MAX_DIM = 200
CONFIRM_MAX_DIM = 400
CLAHE_CLIP = 1.25
N_FOLDS = 5
SEED = 0

# 검증된 계열의 범위를 그대로 쓴다(tools/evaluate_new_body_de00_grid.py) +
# Classic Negative의 핵심인 채도 축.
TOE_LIFTS = (0.0, 0.02, 0.036, 0.06, 0.09)
SHOULDER_STARTS = (0.50, 0.58, 0.66, 0.70, 0.74, 0.78, 0.82)
WHITE_POINTS = (0.85, 0.90, 0.95, 1.0)
# 1차 실행(하한 0.45)에서 fold 1이 sat_mult=0.45 하한에 붙어서 사용자
# 지시로 0.20까지 넓혔다. neutral 렌더가 카메라 JPEG보다 HSV S 평균 19.490
# 과채도인 것(`tools/diagnose_fuji_neutral_render_offset.py`, 0/47쌍,
# 부트스트랩 95% CI [-22.964,-16.162])과 방향이 일치한다.
SAT_MULTS = (0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.55, 0.65, 0.75, 0.85, 1.0)
COMBOS = [(tl, ss, wp, sm) for tl in TOE_LIFTS for ss in SHOULDER_STARTS
          for wp in WHITE_POINTS for sm in SAT_MULTS]

# 경계 판정용 - 각 축의 최소/최대
_EDGES = {
    "toe_lift": (min(TOE_LIFTS), max(TOE_LIFTS)),
    "shoulder_start": (min(SHOULDER_STARTS), max(SHOULDER_STARTS)),
    "white_point": (min(WHITE_POINTS), max(WHITE_POINTS)),
    "sat_mult": (min(SAT_MULTS), max(SAT_MULTS)),
}


def apply_candidate(img_bgr, toe_lift, shoulder_start, white_point, sat_mult,
                    clahe_clip=CLAHE_CLIP):
    """v2 후보 - 형제 룩들과 같은 톤 계열 + 채도 축."""
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)
    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)
    out = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * sat_mult, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def _film_mode(jpg_path):
    return subprocess.run(["exiftool", "-s3", "-FilmMode", jpg_path],
                          capture_output=True, text=True, timeout=30).stdout.strip()


def _sign_test_p(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    return min(1.0, 2.0 * sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n))


def summarize(base, new, label_base, label_new, n_bootstrap=20000, seed=SEED):
    d = np.asarray(base, float) - np.asarray(new, float)
    n = len(d)
    rng = np.random.default_rng(seed)
    boot = np.array([d[rng.integers(0, n, n)].mean() for _ in range(n_bootstrap)])
    lo, hi = (float(v) for v in np.percentile(boot, [2.5, 97.5]))
    wins, losses = int((d > 0).sum()), int((d < 0).sum())
    p = _sign_test_p(wins, losses)
    incon = lo <= 0.0 <= hi
    print(f"\n평균 {label_base} ΔE00={np.mean(base):.4f}  "
          f"평균 {label_new} ΔE00={np.mean(new):.4f}  "
          f"개선폭={100.0 * d.mean() / np.mean(base):+.2f}%")
    print(f"승/패={wins}/{losses}  부호검정 p={p:.4f}  "
          f"부트스트랩 95% CI=[{lo:+.4f}, {hi:+.4f}]")
    verdict = ("판정 보류 (CI가 0 포함)" if incon
               else (f"{label_new} 우세" if d.mean() > 0 else f"{label_base} 우세"))
    print(f"판정: {verdict}")
    return dict(mean_base=float(np.mean(base)), mean_new=float(np.mean(new)),
                n=n, wins=wins, losses=losses, p_value=p, ci_lo=lo, ci_hi=hi,
                inconclusive=bool(incon), verdict=verdict)


def _best_combo(idxs, grids, targets_grid):
    targets_linear = [bgr_u8_to_linear_rgb(target) for target in targets_grid]
    best, best_de = None, float("inf")
    for combo in COMBOS:
        de = float(np.mean([
            mean_delta_e(bgr_u8_to_linear_rgb(apply_candidate(grids[i], *combo)),
                         targets_linear[i])
            for i in idxs
        ]))
        if de < best_de:
            best, best_de = combo, de
    return best, best_de


def _on_edge(combo):
    names = ("toe_lift", "shoulder_start", "white_point", "sat_mult")
    return [n for n, v in zip(names, combo) if v in _EDGES[n]]


def main():
    with open(os.path.join(SET_DIR, "manifest.csv"), encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    grids, targets_grid, confirms, targets_confirm, names = [], [], [], [], []
    for r in rows:
        jpg = os.path.join(SET_DIR, "jpeg", r["filename_jpeg"])
        raw = os.path.join(SET_DIR, "raw", r["filename_raw"])
        if not (os.path.exists(jpg) and os.path.exists(raw)):
            continue
        if _film_mode(jpg) != FILM_MODE:
            continue
        jimg = cv2.imread(jpg)
        g = load_neutral_render(raw, max_dim=GRID_MAX_DIM)
        c = load_neutral_render(raw, max_dim=CONFIRM_MAX_DIM)
        grids.append(g)
        targets_grid.append(cv2.resize(jimg, (g.shape[1], g.shape[0]),
                                       interpolation=cv2.INTER_AREA))
        confirms.append(c)
        targets_confirm.append(cv2.resize(jimg, (c.shape[1], c.shape[0]),
                                          interpolation=cv2.INTER_AREA))
        names.append(r["filename_raw"])
        if len(names) % 10 == 0:
            print(f"  {len(names)}개 로드", flush=True)

    n = len(names)
    if n == 0:
        raise ValueError(f"No usable pairs found for {FILM_MODE}; check manifest.csv "
                         "and local JPEG/RAW files.")
    print(f"\n[{FILM_MODE}] {n}쌍, 콤보 {len(COMBOS)}개, {N_FOLDS}-fold\n", flush=True)

    rng = np.random.default_rng(SEED)
    order = rng.permutation(n)
    folds = np.array_split(order, N_FOLDS)

    de_cur, de_new, fold_combos = [None] * n, [None] * n, []
    for fi, test_idx in enumerate(folds, 1):
        train_idx = [i for i in range(n) if i not in set(test_idx.tolist())]
        print(f"[fold {fi}/{N_FOLDS}] 학습 {len(train_idx)}개", flush=True)
        combo, tr_de = _best_combo(train_idx, grids, targets_grid)
        print(f"  선택 combo={combo}  학습 ΔE00={tr_de:.4f}", flush=True)
        fold_combos.append(list(combo))
        for i in test_idx.tolist():
            target_linear = bgr_u8_to_linear_rgb(targets_confirm[i])
            de_cur[i] = mean_delta_e(
                bgr_u8_to_linear_rgb(apply_classic_negative(confirms[i])),
                target_linear)
            de_new[i] = mean_delta_e(
                bgr_u8_to_linear_rgb(apply_candidate(confirms[i], *combo)),
                target_linear)
        print(f"  홀드아웃 현행 {np.mean([de_cur[i] for i in test_idx]):.4f} -> "
              f"v2 {np.mean([de_new[i] for i in test_idx]):.4f}", flush=True)

    print(f"\n=== {N_FOLDS}-fold 홀드아웃 (데이터 누수 없음) ===")
    stats = summarize(de_cur, de_new, "현행 apply_classic_negative", "v2 후보")

    print("\n=== 전체 표본 최종 상수 ===", flush=True)
    full_combo, full_de = _best_combo(list(range(n)), grids, targets_grid)
    edges = _on_edge(full_combo)
    print(f"combo=(toe_lift={full_combo[0]}, shoulder_start={full_combo[1]}, "
          f"white_point={full_combo[2]}, sat_mult={full_combo[3]})  "
          f"in-sample ΔE00={full_de:.4f}")
    print(f"격자 경계에 붙은 축: {edges or '없음'}")

    unanimous = all(fc == fold_combos[0] for fc in fold_combos)
    print(f"폴드 만장일치: {'예' if unanimous else '아니오'}  폴드별 선택={fold_combos}")

    passed = (not stats["inconclusive"]) and stats["mean_new"] < stats["mean_base"]
    print(f"\n성공 기준(CI가 0 배제 + v2 우세) 충족: {'예' if passed else '아니오'}")
    if passed and edges:
        print(f"다만 {edges} 축이 격자 경계 - 모델 형태가 여전히 데이터에 "
              f"안 맞을 수 있음, 범위를 넓혀 재확인 필요")
    print(f"권고: {'v2 추가 제안 (배포는 사용자 결정)' if passed and not edges else ('v2 추가 제안하되 경계 축 재확인 선행' if passed else '현행 유지')}")

    out = os.path.join(SET_DIR, "classic_negative_v2_grid_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "purpose": "Classic Negative를 형제 룩들과 같은 검증된 파라미터 "
                       "계열(CLAHE + film_curve + 채도)로 재적합",
            "why_family_change": "현행 계열 재보정이 4개 파라미터 전부 격자 "
                                 "경계로 달아났고, 진단 결과 원인이 룩이 아니라 "
                                 "load_neutral_render()의 no_auto_bright=True "
                                 "노출 격차였음",
            "criterion": "5-fold 홀드아웃 페어드 부트스트랩 95% CI 20000회 고정 "
                         "시드가 0을 배제하고 v2가 우세할 때만 추가 권고; 최종 "
                         "상수가 격자 경계에 붙으면 실패 신호",
            "film_mode": FILM_MODE,
            "set": "datasets/fuji/contributed/local-work-2026-08",
            "n_pairs": n,
            "images": names,
            "n_combos": len(COMBOS),
            "grid": {"toe_lift": list(TOE_LIFTS), "shoulder_start": list(SHOULDER_STARTS),
                     "white_point": list(WHITE_POINTS), "sat_mult": list(SAT_MULTS)},
            "fold_combos": fold_combos,
            "fold_unanimous": unanimous,
            "full_sample_combo": list(full_combo),
            "full_sample_in_sample_de00": full_de,
            "params_on_grid_edge": edges,
            "delta_e_current": de_cur,
            "delta_e_v2": de_new,
            "stats": stats,
            "criterion_passed": bool(passed),
            "modifies_shipped_code": False,
        }, f, indent=2, ensure_ascii=False)
    print(f"리포트: {out}")


if __name__ == "__main__":
    main()
