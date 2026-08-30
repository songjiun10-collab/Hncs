"""[research] breakdown_by_generation.py가 확인한 대로 기존 hasselblad.json이
X2D II 100C(147쌍, ΔE00 평균 21.521 - 다른 세대는 전부 9~14대)에서만
유독 나쁘다 - 세대 뒤섞인 487쌍 풀 재보정이 게이트를 통과 못 한 것도
이 세대의 개선분이 다른 세대와 상쇄됐기 때문일 가능성이 높다. 이 세대만
따로 떼서 recalibrate.py의 게이트 로직으로 재보정.

  python3 -m hybrid_engine.recalibrate_x2dii100c          # dry-run
  python3 -m hybrid_engine.recalibrate_x2dii100c --write  # 게이트 통과시만 반영
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hybrid_engine.calibrate_profile import _resize_max_dim, CALIB_MAX_DIM
from hybrid_engine.core import color_matrix
from hybrid_engine.recalibrate import MIN_CV_IMPROVEMENT_PCT, decide_and_maybe_write
from hybrid_engine.utils.io import decode_raw, load_image_linear
from tools.calibrate import collect_local_pairs

TARGET_GENERATION = "X2D II 100C"


def _load_target():
    items = [p for p in collect_local_pairs()
              if p["generation"] == TARGET_GENERATION and p["scene_type"] != "chart"]
    print(f"{TARGET_GENERATION} {len(items)}쌍")

    dataset = []
    for i, p in enumerate(items):
        print(f"  [{i + 1}/{len(items)}] 로드 중: {os.path.basename(p['raw_path'])}", flush=True)
        try:
            linear = decode_raw(p["raw_path"])
        except Exception as e:
            print(f"    디코드 실패, 스킵: {e}")
            continue
        linear_small = _resize_max_dim(linear, CALIB_MAX_DIM)
        camera_wb = color_matrix.extract_camera_metadata(p["raw_path"])["camera_whitebalance"]
        target_small = load_image_linear(p["jpeg_path"], resize_to=linear_small.shape[:2])
        dataset.append((linear_small, camera_wb, target_small))
    return dataset


def main():
    parser = argparse.ArgumentParser(description=f"{TARGET_GENERATION} 전용 재보정")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--n-folds", type=int, default=4)
    parser.add_argument("--min-improvement-pct", type=float, default=MIN_CV_IMPROVEMENT_PCT)
    args = parser.parse_args()

    dataset = _load_target()
    print(f"\n로드 완료: {len(dataset)}쌍\n")
    if not dataset:
        return

    decide_and_maybe_write(
        dataset, f"{TARGET_GENERATION} 전용 {len(dataset)}쌍", n_folds=args.n_folds,
        min_improvement_pct=args.min_improvement_pct, write=args.write)


if __name__ == "__main__":
    main()
