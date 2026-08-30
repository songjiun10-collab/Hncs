"""[research] breakdown_by_generation.py로 세대별 ΔE00 격차를 확인한 뒤,
특정 세대 하나만 떼서 recalibrate.py의 게이트 로직으로 재보정한다 -
세대 뒤섞은 풀 재보정은 한 세대의 개선분이 다른 세대와 상쇄될 수 있어서
(2026-08 X2D II 100C 사례), 안 좋은 세대만 격리해서 재보정하는 게
더 정확한 신호를 준다.

  python3 -m hybrid_engine.recalibrate_by_generation --generation "X2D II 100C"
  python3 -m hybrid_engine.recalibrate_by_generation --generation "X2D II 100C" --write
  python3 -m hybrid_engine.recalibrate_by_generation --list   # 사용 가능한 세대 라벨 목록
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


def _load_target(generation):
    items = [p for p in collect_local_pairs()
              if p["generation"] == generation and p["scene_type"] != "chart"]
    print(f"{generation} {len(items)}쌍")

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
    parser = argparse.ArgumentParser(description="세대(바디) 하나만 떼서 재보정")
    parser.add_argument("--generation", help='예: "X2D II 100C", "X1D", "CFV 100C/907X"')
    parser.add_argument("--list", action="store_true", help="사용 가능한 세대 라벨과 표본수 출력 후 종료")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--n-folds", type=int, default=4)
    parser.add_argument("--min-improvement-pct", type=float, default=MIN_CV_IMPROVEMENT_PCT)
    args = parser.parse_args()

    if args.list:
        from collections import Counter
        counts = Counter(p["generation"] for p in collect_local_pairs())
        for gen, n in counts.most_common():
            print(f"{gen}: {n}쌍")
        return

    if not args.generation:
        parser.error("--generation 필요 (또는 --list로 사용 가능한 값 확인)")

    dataset = _load_target(args.generation)
    print(f"\n로드 완료: {len(dataset)}쌍\n")
    if not dataset:
        print(f"'{args.generation}' 세대에 해당하는 페어가 없음 - --list로 정확한 라벨 확인")
        return

    decide_and_maybe_write(
        dataset, f"{args.generation} 전용 {len(dataset)}쌍", n_folds=args.n_folds,
        min_improvement_pct=args.min_improvement_pct, write=args.write)


if __name__ == "__main__":
    main()
