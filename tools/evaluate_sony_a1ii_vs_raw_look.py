"""
`tools/fit_population_body_de00_grid.py sony ILCE-1M2`가 고른 후보
(toe=0.02, ss=0.66, wp=0.85, clip=3.0 - 3/5 폴드, 차점 toe=0.02/ss=0.78/
wp=0.85/clip=2.0 - 2/5 폴드)를 **올바른 현재 baseline인
`apply_sony_raw_look()`**(brands/sony_raw.py) 대비로 재확인한다 -
그 그리드 스크립트는 `apply_sony_look()`(구버전, brands/sony.py)과
비교했었는데, 실제 무전용함수 Sony 바디에 쓰이는 최신 제네릭은
`apply_sony_raw_look()`이라 그거랑 맞대결해야 진짜 개선폭이 나온다.
`tools/evaluate_population_raw_look_native_confirm.py`와 같은 로더/
디코드 재사용, ILCE-1M2만 필터링.

  python3 -m tools.evaluate_sony_a1ii_vs_raw_look
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from tools.calibrate import load_neutral_render
from tools.evaluate_expanded_clahe_shoulder_refit import (
    collect_contributed_pairs, load_target_linear, mean_delta_e, bgr_u8_to_linear,
)
from brands.sony_raw import apply_sony_raw_look

MAX_DIM = 400
CANDIDATES = [
    ("3/5폴드 1위", 0.02, 0.66, 0.85, 3.0),
    ("2/5폴드 2위", 0.02, 0.78, 0.85, 2.0),
]


def _sign_test_p(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def main():
    pairs = collect_contributed_pairs("sony", model_filter="ILCE-1M2")
    print(f"ILCE-1M2: {len(pairs)}쌍", flush=True)

    baseline_des = []
    decoded = []
    for p in pairs:
        neutral_bgr = load_neutral_render(p["raw_path"], max_dim=MAX_DIM)
        looked_bgr = apply_sony_raw_look(neutral_bgr)
        looked_lin = bgr_u8_to_linear(looked_bgr)
        target = load_target_linear(p["jpeg_path"], looked_lin.shape[:2])
        baseline_des.append(mean_delta_e(looked_lin, target))
        decoded.append((neutral_bgr, target))
    baseline_des = np.array(baseline_des)
    print(f"apply_sony_raw_look() 기준 ΔE00 = {baseline_des.mean():.4f} (n={len(baseline_des)})")

    for label, tl, ss, wp, cc in CANDIDATES:
        cand_des = []
        for (neutral_bgr, target), p in zip(decoded, pairs):
            out = apply_sony_raw_look(neutral_bgr, toe_lift=tl, shoulder_start=ss,
                                       white_point=wp, clahe_clip=cc)
            out_lin = bgr_u8_to_linear(out)
            cand_des.append(mean_delta_e(out_lin, target))
        cand_des = np.array(cand_des)
        diff = baseline_des - cand_des
        wins, losses = int((diff > 0).sum()), int((diff < 0).sum())
        improvement = (baseline_des.mean() - cand_des.mean()) / baseline_des.mean() * 100.0
        rng = np.random.RandomState(0)
        n = len(diff)
        boot = np.array([diff[rng.randint(0, n, n)].mean() for _ in range(20000)])
        ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
        p_val = _sign_test_p(wins, losses)
        print(f"\n{label} (toe={tl},ss={ss},wp={wp},clip={cc}): ΔE00={cand_des.mean():.4f}  "
              f"개선폭={improvement:+.2f}%")
        print(f"  승/패={wins}/{losses}  부호검정 p={p_val:.4f}  부트스트랩 95% CI=[{ci_lo:+.3f},{ci_hi:+.3f}]")
        print("  판정:", "보류(CI 0 포함)" if ci_lo <= 0 <= ci_hi else ("후보 우세" if improvement > 0 else "기존 우세"))


if __name__ == "__main__":
    main()
