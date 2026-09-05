"""v2 후보의 격자 경계 두 축(`toe_lift` 하한 0.0, `white_point` 상한 1.0)이
**진짜 제약인지 그냥 최적점인지** 확인한다.

**왜 필요한가**: `tools/evaluate_fuji_classic_negative_v2_grid.py`가 사전에
못 박은 기준에 "최종 상수가 격자 경계에 붙으면 실패 신호"를 넣어뒀고, 결과가
`toe_lift=0.0`/`white_point=1.0`으로 경계에 붙었다. 다만 이 두 값은 각 축의
**항등 끝**이기도 하다 - `toe_lift=0`은 섀도 리프트 없음,
`white_point=1.0`은 하이라이트 압축 없음이고, 같은 세트를 적합한
`apply_provia`/`apply_classic_chrome_v2`/`apply_nostalgic_neg_v3`도 전부 이
값으로 수렴했다.

그러니 "의미상 끝이라 괜찮다"고 **주장하지 말고 재본다**. 나머지 두 축을
전체표본 최적값(`shoulder_start=0.78`, `sat_mult=0.40`)에 고정하고 경계
바깥으로 넘겨서 ΔE00이 더 떨어지는지 확인한다.

`core.curve.film_curve`는 결과를 `[0,1]`로 clip하므로 경계 바깥 값도 계산은
된다: `toe_lift<0`은 섀도를 뭉개고, `white_point>1.0`은 shoulder 구간을 위로
밀어 밝힌다. 후자가 바로 현행 계열 재보정을 망친 **노출 보정 탈출구**라,
여기서 최적이 그쪽으로 달아나면 "경계는 우리가 의도적으로 건 제약"이라는
뜻이고 그렇게 보고한다.

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

from hybrid_engine.utils.evaluate import mean_delta_e
from tools.calibrate import load_neutral_render
from tools.evaluate_fuji_classic_negative_v2_grid import apply_candidate

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SET_DIR = os.path.join(BASE, "datasets", "fuji", "contributed", "local-work-2026-08")
FILM_MODE = "Classic Negative"
MAX_DIM = 200

# tools/evaluate_fuji_classic_negative_v2_grid.py 전체표본 최적값
BEST = dict(toe_lift=0.0, shoulder_start=0.78, white_point=1.0, sat_mult=0.40)
# 경계 바깥까지 확장한 두 축 (0.0 / 1.0 이 각각 기존 경계)
TOE_LIFTS = (-0.08, -0.06, -0.04, -0.02, 0.0)
WHITE_POINTS = (1.0, 1.05, 1.10, 1.15, 1.20)


def _film_mode(jpg_path):
    return subprocess.run(["exiftool", "-s3", "-FilmMode", jpg_path],
                          capture_output=True, text=True, timeout=30).stdout.strip()


def main():
    rows = list(csv.DictReader(open(os.path.join(SET_DIR, "manifest.csv"),
                                    encoding="utf-8-sig")))
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
    print(f"[{FILM_MODE}] {n}쌍, 기준 상수 {BEST}\n")

    def de(tl, wp):
        return float(np.mean([mean_delta_e(
            apply_candidate(imgs[i], tl, BEST["shoulder_start"], wp,
                            BEST["sat_mult"]), targets[i]) for i in range(n)]))

    base = de(BEST["toe_lift"], BEST["white_point"])
    print(f"기준(경계 위) ΔE00={base:.4f}\n")

    print("toe_lift를 하한 밖으로 (white_point=1.0 고정):")
    toe_rows = {}
    for tl in TOE_LIFTS:
        v = de(tl, BEST["white_point"])
        toe_rows[tl] = v
        print(f"  toe_lift={tl:+.2f}  ΔE00={v:.4f}  {'← 기준' if tl == 0.0 else ('개선' if v < base else '악화')}")

    print("\nwhite_point를 상한 밖으로 (toe_lift=0.0 고정):")
    wp_rows = {}
    for wp in WHITE_POINTS:
        v = de(BEST["toe_lift"], wp)
        wp_rows[wp] = v
        print(f"  white_point={wp:.2f}  ΔE00={v:.4f}  {'← 기준' if wp == 1.0 else ('개선' if v < base else '악화')}")

    toe_binds = min(toe_rows.values()) < base - 1e-6
    wp_binds = min(wp_rows.values()) < base - 1e-6
    print(f"\ntoe_lift 경계가 최적을 가로막았나: {'예' if toe_binds else '아니오'}")
    print(f"white_point 경계가 최적을 가로막았나: {'예' if wp_binds else '아니오'}")
    if wp_binds:
        best_wp = min(wp_rows, key=wp_rows.get)
        print(f"  -> white_point가 {best_wp}까지 달아난다. film_curve에서 "
              f"white_point>1.0은 shoulder 구간을 위로 밀어 밝히는 것이라, "
              f"이는 tools/diagnose_neutral_render_offset_by_brand.py가 확인한 "
              f"전 브랜드 공통 밝기 격차를 다시 흡수하려는 것 - 의도적으로 건 "
              f"제약이므로 1.0을 유지한다")
    if not (toe_binds or wp_binds):
        print("  -> 두 경계 모두 진짜 최적점. 형제 룩 3개가 수렴한 값과 동일하다")

    out = os.path.join(SET_DIR, "classic_negative_v2_boundary_probe.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "purpose": "v2 후보의 격자 경계 두 축이 진짜 제약인지 최적점인지 확인",
            "film_mode": FILM_MODE, "n_pairs": n, "fixed": BEST,
            "baseline_de00": base,
            "toe_lift_sweep": {str(k): v for k, v in toe_rows.items()},
            "white_point_sweep": {str(k): v for k, v in wp_rows.items()},
            "toe_lift_boundary_binds": bool(toe_binds),
            "white_point_boundary_binds": bool(wp_binds),
            "modifies_shipped_code": False,
        }, f, indent=2, ensure_ascii=False)
    print(f"리포트: {out}")


if __name__ == "__main__":
    main()
