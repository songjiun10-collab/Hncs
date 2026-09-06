"""
`apply_provia()`(brands/fuji.py)는 Provia/Standard 필름모드 raw+jpeg
119쌍(GFX100RF 89 + X-T30 III 20 + GFX50S II 10, EXIF
FilmMode="F0/Standard (Provia)" 필터)으로 검증됐지만, 그 검증은 거의
전부 GFX100RF(89/89 만장일치) 위주였고 X-T30 III/GFX50S II는 표본이
훨씬 작다 - Canon/Sony에서 찾은 것과 같은 질문: 제네릭 함수가 특정
바디에서 유독 나쁜지 확인한다.

`tools.evaluate_expanded_clahe_shoulder_refit.collect_contributed_pairs`
의 `film_mode_filter`를 그대로 재사용(EXIF FilmMode 직접 읽음).

  python3 -m tools.breakdown_fuji_provia_by_camera_body
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
from brands.fuji import apply_provia

MAX_DIM = 500
FILM_MODE = "F0/Standard (Provia)"


def main():
    pairs = collect_contributed_pairs("fuji", film_mode_filter=FILM_MODE)
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "datasets", "fuji", "contributed")
    name_to_camera = {}
    for set_name in sorted(os.listdir(base)):
        manifest = os.path.join(base, set_name, "manifest.csv")
        if not os.path.exists(manifest):
            continue
        for row in csv.DictReader(open(manifest, encoding="utf-8-sig")):
            name_to_camera.setdefault(row["filename_raw"], row.get("camera", "?"))

    by_camera = {}
    for p in pairs:
        cam = name_to_camera.get(p["name"], "?")
        by_camera.setdefault(cam, []).append(p)
    print("바디별 Provia 쌍 개수:", {k: len(v) for k, v in by_camera.items()})

    results = {}
    for cam, cam_pairs in by_camera.items():
        des = []
        fail = 0
        for p in cam_pairs:
            try:
                neutral_bgr = load_neutral_render(p["raw_path"], max_dim=MAX_DIM)
                looked_bgr = apply_provia(neutral_bgr)
                looked_lin = bgr_u8_to_linear(looked_bgr)
                target = load_target_linear(p["jpeg_path"], looked_lin.shape[:2])
                des.append(mean_delta_e(looked_lin, target))
            except Exception:
                fail += 1
        des = np.array(des)
        results[cam] = des.tolist()
        print(f"\n{cam}: n={len(des)} (실패 {fail})")
        if len(des):
            print(f"  평균 ΔE00={des.mean():.3f}  표준편차={des.std():.3f}  "
                  f"중앙값={np.median(des):.3f}  최대={des.max():.3f}")

    out_path = os.path.join(base, "provia_camera_body_de00_breakdown.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n저장: {out_path}")

    cams = [c for c in results if len(results[c]) >= 5]
    if len(cams) >= 2:
        base_cam = max(cams, key=lambda c: len(results[c]))
        for cam in cams:
            if cam == base_cam:
                continue
            a, b = np.array(results[cam]), np.array(results[base_cam])
            rng = np.random.RandomState(0)
            diffs = np.array([
                a[rng.randint(0, len(a), len(a))].mean() - b[rng.randint(0, len(b), len(b))].mean()
                for _ in range(20000)
            ])
            ci_lo, ci_hi = np.percentile(diffs, [2.5, 97.5])
            print(f"\n{cam}({len(a)}) - {base_cam}({len(b)}) 평균차 부트스트랩 95% CI = "
                  f"[{ci_lo:+.3f}, {ci_hi:+.3f}] (0 포함하면 판정 보류: {ci_lo <= 0 <= ci_hi})")


if __name__ == "__main__":
    main()
