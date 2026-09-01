"""
`brands/sony.py`의 `apply_sony_raw_look()`은 Sony 328쌍(288쌍 디코드
성공, a7V/a7R VI 포함) 풀링 데이터로 튜닝됐다 - `brands/sony_raw.py`
docstring 참고. a7V(ILCE-7M5)/a7R VI(ILCE-7RM6)는 이미 전용 함수
(`brands/sony_a7v.py`/`sony_a7rvi.py`)가 있으니, 나머지 전용 함수 없는
바디(ILCE-7CR/ILCE-1M2/ILCE-9M3)에서 제네릭 함수가 하셀블라드 X1D
사례(제네릭 `apply_hncs()`가 세대 중 가장 나빴던 것)처럼 유독 나쁜지
확인한다.

`tools/evaluate_population_raw_look_native_confirm.py`와 같은 로더
(`collect_contributed_pairs`)/디코드(`load_neutral_render`) 재사용,
선택 단계 관례(max_dim=500)로 빠르게 스크리닝만 한다 - 신호가 보이면
그 다음에 원본 픽셀로 재확인.

  python3 -m tools.breakdown_sony_by_camera_body
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json

import numpy as np

from tools.calibrate import load_neutral_render
from tools.evaluate_expanded_clahe_shoulder_refit import (
    collect_contributed_pairs, load_target_linear, mean_delta_e, bgr_u8_to_linear,
)
from brands.sony_raw import apply_sony_raw_look

MAX_DIM = 500
NO_DEDICATED_BODIES = ["ILCE-7CR", "ILCE-1M2", "ILCE-9M3"]


def main():
    all_pairs = collect_contributed_pairs("sony")
    # camera 필드가 dict에 없어서, manifest를 다시 읽어 name->camera 매핑
    import csv
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "datasets", "sony", "contributed")
    name_to_camera = {}
    for set_name in sorted(os.listdir(base)):
        manifest = os.path.join(base, set_name, "manifest.csv")
        if not os.path.exists(manifest):
            continue
        for row in csv.DictReader(open(manifest, encoding="utf-8-sig")):
            name_to_camera.setdefault(row["filename_raw"], row.get("camera", "?"))

    by_camera = {}
    for p in all_pairs:
        cam = name_to_camera.get(p["name"], "?")
        if cam not in NO_DEDICATED_BODIES:
            continue
        by_camera.setdefault(cam, []).append(p)

    print("바디별 쌍 개수:", {k: len(v) for k, v in by_camera.items()})

    for cam, pairs in by_camera.items():
        des = []
        fail = 0
        for p in pairs:
            try:
                neutral_bgr = load_neutral_render(p["raw_path"], max_dim=MAX_DIM)
                looked_bgr = apply_sony_raw_look(neutral_bgr)
                looked_lin = bgr_u8_to_linear(looked_bgr)
                target = load_target_linear(p["jpeg_path"], looked_lin.shape[:2])
                de = mean_delta_e(looked_lin, target)
                des.append(de)
            except Exception as e:
                fail += 1
        des = np.array(des)
        print(f"\n{cam}: n={len(des)} (실패 {fail})")
        print(f"  평균 ΔE00={des.mean():.3f}  표준편차={des.std():.3f}  "
              f"중앙값={np.median(des):.3f}  최대={des.max():.3f}")
        by_camera[cam] = des.tolist()  # 재사용/기록용

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "datasets", "sony", "contributed",
                             "no_dedicated_body_de00_breakdown.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(by_camera, f, indent=2)
    print(f"\n저장: {out_path}")

    # 부트스트랩 - a1 II(ILCE-1M2) vs 나머지 두 바디 평균차
    rng = np.random.RandomState(0)
    a1ii = np.array(by_camera["ILCE-1M2"])
    others = np.concatenate([np.array(by_camera["ILCE-7CR"]), np.array(by_camera["ILCE-9M3"])])
    diffs = []
    for _ in range(20000):
        a = a1ii[rng.randint(0, len(a1ii), len(a1ii))]
        b = others[rng.randint(0, len(others), len(others))]
        diffs.append(a.mean() - b.mean())
    diffs = np.array(diffs)
    ci_lo, ci_hi = np.percentile(diffs, [2.5, 97.5])
    print(f"\nILCE-1M2 평균 - (7CR+9M3 풀링) 평균 부트스트랩 95% CI = [{ci_lo:+.3f}, {ci_hi:+.3f}]")
    print("0 포함 안 함(유의미) =" if not (ci_lo <= 0 <= ci_hi) else "0 포함(판정 보류) =",
          ci_lo <= 0 <= ci_hi)


if __name__ == "__main__":
    main()
