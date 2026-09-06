"""v2 후보의 격자 경계 네 축 전부가 **진짜 제약인지 그냥 최적점인지**
확인한다.

**왜 필요한가**: `tools/evaluate_fuji_classic_negative_v2_grid.py`가 사전에
못 박은 기준에 "최종 상수가 격자 경계에 붙으면 실패 신호"를 넣어뒀다.

색공간 버그 수정 전 1차 결과(`toe_lift=0.0, shoulder_start=0.78,
white_point=1.0, sat_mult=0.40`)는 두 축만 경계였다. `mean_delta_e()`에
BGR uint8을 linear RGB 변환 없이 넣던 버그(2026-09-06,
`hybrid_engine.utils.evaluate.bgr_u8_to_linear_rgb` 도입으로 수정)를 고치고
같은 격자를 재실행하니 개선폭이 +8.80%에서 **+19.36%**로 커졌고, 전체표본
최종 상수가 `(toe_lift=0.0, shoulder_start=0.82, white_point=1.0,
sat_mult=0.20)`로 **네 축 전부** 격자 경계에 붙었다(5/5 폴드 만장일치).

`toe_lift=0`/`white_point=1.0`은 같은 세트를 적합한
`apply_provia`/`apply_classic_chrome_v2`/`apply_nostalgic_neg_v3`도 전부
수렴한 항등값이라 그 자체로는 의심스럽지 않지만, "의미상 끝이라 괜찮다"고
주장하지 말고 네 축 전부 재본다. 나머지 세 축을 전체표본 최적값에 고정하고
경계 바깥으로 넘겨서 ΔE00이 더 떨어지는지 확인한다.

`core.curve.film_curve`는 결과를 `[0,1]`로 clip하므로 경계 바깥 값도 계산은
된다: `toe_lift<0`은 섀도를 뭉개고, `white_point>1.0`/`shoulder_start→1`은
하이라이트 압축을 줄여 전역적으로 밝힌다. 이게 바로 현행 계열 재보정을
망친 **노출 보정 탈출구**와 같은 메커니즘이라, 여기서 최적이 그쪽으로
계속 달아나면 "경계는 노출 격차를 흡수하는 탈출구"라는 뜻이고 그렇게
보고한다. `sat_mult`가 계속 내려가면 후지 특유의 과채도
(`tools/diagnose_neutral_render_offset_by_brand.py`, HSV S -19.490,
0/47쌍)를 반영하는 것인지도 함께 본다.

판정: 경계 바깥에서 ΔE00이 더 낮아지지 않으면 경계는 진짜 최적점이다.
낮아지면 그 축이 무엇을 보상하고 있는지 함께 적는다.

`brands/fuji.py`는 읽기만 한다.

  ~/.hncs-hybrid-venv312/bin/python3 -m tools.probe_fuji_classic_negative_v2_boundary
"""
import csv
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from hybrid_engine.utils.evaluate import bgr_u8_to_linear_rgb, mean_delta_e
from tools.calibrate import load_neutral_render
from tools.evaluate_fuji_classic_negative_v2_grid import apply_candidate

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SET_DIR = os.path.join(BASE, "datasets", "fuji", "contributed", "local-work-2026-08")
FILM_MODE = "Classic Negative"
MAX_DIM = 200

# tools/evaluate_fuji_classic_negative_v2_grid.py 전체표본 최적값
# (색공간 버그 수정 후 재실행, 2026-09-06 - 네 축 전부 격자 경계)
BEST = dict(toe_lift=0.0, shoulder_start=0.82, white_point=1.0, sat_mult=0.20)
# 네 축 전부 경계 바깥까지 확장해서 재확인
TOE_LIFTS = (-0.08, -0.06, -0.04, -0.02, 0.0)
SHOULDER_STARTS = (0.82, 0.86, 0.90, 0.94, 0.97, 0.99, 0.999)
WHITE_POINTS = (1.0, 1.05, 1.10, 1.15, 1.20)
SAT_MULTS = (0.20, 0.15, 0.10, 0.05, 0.02)


def _film_mode(jpg_path):
    return subprocess.run(["exiftool", "-s3", "-FilmMode", jpg_path],
                          capture_output=True, text=True, timeout=30).stdout.strip()


def main():
    with open(os.path.join(SET_DIR, "manifest.csv"), encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    imgs, targets = [], []
    for r in rows:
        jpg = os.path.join(SET_DIR, "jpeg", r["filename_jpeg"])
        raw = os.path.join(SET_DIR, "raw", r["filename_raw"])
        if not (os.path.exists(jpg) and os.path.exists(raw)):
            continue
        if _film_mode(jpg) != FILM_MODE:
            continue
        g = load_neutral_render(raw, max_dim=MAX_DIM)
        imgs.append(g)
        targets.append(cv2.resize(cv2.imread(jpg), (g.shape[1], g.shape[0]),
                                  interpolation=cv2.INTER_AREA))
    n = len(imgs)
    if n == 0:
        raise ValueError(f"No usable pairs found for {FILM_MODE}; check manifest.csv "
                         "and local JPEG/RAW files.")
    print(f"[{FILM_MODE}] {n}쌍, 기준 상수 {BEST}\n")

    targets_linear = [bgr_u8_to_linear_rgb(t) for t in targets]

    def de(tl, ss, wp, sm):
        return float(np.mean([mean_delta_e(
            bgr_u8_to_linear_rgb(apply_candidate(imgs[i], tl, ss, wp, sm)),
            targets_linear[i]) for i in range(n)]))

    base = de(BEST["toe_lift"], BEST["shoulder_start"], BEST["white_point"],
             BEST["sat_mult"])
    print(f"기준(전체표본 최적값) ΔE00={base:.4f}\n")

    def sweep(name, values, base_key):
        print(f"\n{name} 스윕 (나머지 세 축은 최적값 고정):")
        rows = {}
        for v in values:
            params = dict(BEST)
            params[base_key] = v
            de_v = de(params["toe_lift"], params["shoulder_start"],
                      params["white_point"], params["sat_mult"])
            rows[v] = de_v
            tag = ("← 기준" if v == BEST[base_key]
                   else ("개선" if de_v < base else "악화"))
            print(f"  {name}={v:+.3f}  ΔE00={de_v:.4f}  {tag}")
        return rows

    toe_rows = sweep("toe_lift", TOE_LIFTS, "toe_lift")
    shoulder_rows = sweep("shoulder_start", SHOULDER_STARTS, "shoulder_start")
    wp_rows = sweep("white_point", WHITE_POINTS, "white_point")
    sat_rows = sweep("sat_mult", SAT_MULTS, "sat_mult")

    binds = {
        "toe_lift": min(toe_rows.values()) < base - 1e-6,
        "shoulder_start": min(shoulder_rows.values()) < base - 1e-6,
        "white_point": min(wp_rows.values()) < base - 1e-6,
        "sat_mult": min(sat_rows.values()) < base - 1e-6,
    }
    print()
    for axis, does_bind in binds.items():
        print(f"{axis} 경계가 최적을 가로막았나: {'예' if does_bind else '아니오'}")

    if binds["shoulder_start"]:
        best_ss = min(shoulder_rows, key=shoulder_rows.get)
        print(f"  -> shoulder_start가 {best_ss}까지 달아난다 - shoulder_start->1은 "
              f"하이라이트 압축을 줄여 전역적으로 밝히는 것과 같은 효과라, "
              f"white_point 탈출구와 동일한 노출 보정 메커니즘일 수 있다")
    if binds["white_point"]:
        best_wp = min(wp_rows, key=wp_rows.get)
        print(f"  -> white_point가 {best_wp}까지 달아난다 - film_curve에서 "
              f"white_point>1.0은 shoulder 구간을 위로 밀어 밝히는 것이라, "
              f"전 브랜드 공통 밝기 격차를 다시 흡수하려는 탈출구일 수 있다")
    if binds["sat_mult"]:
        best_sm = min(sat_rows, key=sat_rows.get)
        print(f"  -> sat_mult가 {best_sm}까지 달아난다 - 후지 neutral 렌더가 "
              f"카메라 JPEG보다 과채도(HSV S -19.490, 0/47쌍)인 것과 방향이 "
              f"일치해 진짜 특성일 수도, 과도한 desaturation 탈출구일 수도 있다")
    if not any(binds.values()):
        print("  -> 네 경계 모두 진짜 최적점")

    out = os.path.join(SET_DIR, "classic_negative_v2_boundary_probe.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "purpose": "v2 후보의 격자 경계 네 축 전부가 진짜 제약인지 최적점인지 확인 "
                       "(색공간 버그 수정 후 재실행)",
            "film_mode": FILM_MODE, "n_pairs": n, "fixed": BEST,
            "baseline_de00": base,
            "toe_lift_sweep": {str(k): v for k, v in toe_rows.items()},
            "shoulder_start_sweep": {str(k): v for k, v in shoulder_rows.items()},
            "white_point_sweep": {str(k): v for k, v in wp_rows.items()},
            "sat_mult_sweep": {str(k): v for k, v in sat_rows.items()},
            "boundary_binds": binds,
            "modifies_shipped_code": False,
        }, f, indent=2, ensure_ascii=False)
    print(f"리포트: {out}")


if __name__ == "__main__":
    main()
