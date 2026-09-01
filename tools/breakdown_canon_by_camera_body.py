"""
`brands/canon.py`의 `apply_canon_raw_look()`(3x3 매트릭스+톤커브+채도/
색조 LUT, ΔE00 직접 피팅)은 raw+jpeg 143쌍(R6 Mark III 99 + R1 44,
`datasets/canon/contributed/local-work-2026-08/`) 전체를 폴드 분리 없이
풀링해서 피팅됐다 - 이 143쌍이 이 브랜드의 raw+jpeg 데이터 전부라 두
바디로만 구성된다. Sony a1 II 사례
(`tools/breakdown_sony_by_camera_body.py`)와 같은 질문: 이 제네릭
함수가 두 바디 중 하나에서 유독 나쁜지 확인한다.

`tools.calibrate.load_neutral_render()`(8비트 BGR, libraw
use_camera_wb=True/gamma=(2.222,4.5)) 디코드 - `apply_canon_raw_look()`
docstring이 명시한 "반드시 8비트 BGR 입력"과 일치.

  python3 -m tools.breakdown_canon_by_camera_body
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from tools.calibrate import load_neutral_render
from tools.evaluate_expanded_clahe_shoulder_refit import (
    collect_contributed_pairs, load_target_linear, mean_delta_e, bgr_u8_to_linear,
)
from brands.canon import apply_canon_raw_look

MAX_DIM = 500


def main():
    all_pairs = collect_contributed_pairs("canon")
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "datasets", "canon", "contributed")
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
        by_camera.setdefault(cam, []).append(p)
    print("바디별 쌍 개수:", {k: len(v) for k, v in by_camera.items()})

    results = {}
    for cam, pairs in by_camera.items():
        des = []
        fail = 0
        for p in pairs:
            try:
                neutral_bgr = load_neutral_render(p["raw_path"], max_dim=MAX_DIM)
                looked_bgr = apply_canon_raw_look(neutral_bgr)
                looked_lin = bgr_u8_to_linear(looked_bgr)
                target = load_target_linear(p["jpeg_path"], looked_lin.shape[:2])
                des.append(mean_delta_e(looked_lin, target))
            except Exception:
                fail += 1
        des = np.array(des)
        results[cam] = des.tolist()
        print(f"\n{cam}: n={len(des)} (실패 {fail})")
        print(f"  평균 ΔE00={des.mean():.3f}  표준편차={des.std():.3f}  "
              f"중앙값={np.median(des):.3f}  최대={des.max():.3f}")

    out_path = os.path.join(base, "camera_body_de00_breakdown.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n저장: {out_path}")

    cams = list(results.keys())
    if len(cams) == 2:
        a, b = np.array(results[cams[0]]), np.array(results[cams[1]])
        rng = np.random.RandomState(0)
        diffs = np.array([
            a[rng.randint(0, len(a), len(a))].mean() - b[rng.randint(0, len(b), len(b))].mean()
            for _ in range(20000)
        ])
        ci_lo, ci_hi = np.percentile(diffs, [2.5, 97.5])
        print(f"\n{cams[0]} - {cams[1]} 평균차 부트스트랩 95% CI = [{ci_lo:+.3f}, {ci_hi:+.3f}]")
        print("0 포함 여부(0을 포함하면 판정 보류):", ci_lo <= 0 <= ci_hi)


if __name__ == "__main__":
    main()
