"""[research] recalibrate.py의 --cache-dir는 raw_calib_cache/ 스타일 평면
구조(<name>.jpg.3FR + <name>.jpg.target.jpg)만 받는데, 지금 하셀블라드
기여 데이터는 datasets/hasselblad/contributed/<세트>/manifest.csv 구조로
5개 세트(local-mixed-2026-07 대체분 포함 총 474쌍)에 흩어져 있다. 이
스크립트는 공식 13쌍(raw_calib_cache) + 기여 474쌍(collect_local_pairs())
전부를 합쳐서 recalibrate.py의 게이트 로직(decide_and_maybe_write)에
그대로 넘긴다 - 매트릭스/톤/색 재학습이나 통계 판정 로직은 전혀 새로
안 짜고 재사용.

기본은 dry-run(파일 안 건드림) - 실제 hasselblad.json 갱신은 --write를
명시해야 하고, 그것도 5% 교차검증 개선 게이트를 통과해야만 된다
(root CLAUDE.md: "Never touch hasselblad.json without explicit sign-off"
- dry-run 결과 보고 사용자가 별도로 승인해야 --write를 실행한다).

  python3 -m hybrid_engine.recalibrate_full_contributed          # dry-run
  python3 -m hybrid_engine.recalibrate_full_contributed --write  # 게이트 통과시만 반영
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hybrid_engine.calibrate_profile import _find_pairs as _official_find_pairs
from hybrid_engine.calibrate_profile import _resize_max_dim, CALIB_MAX_DIM
from hybrid_engine.core import color_matrix
from hybrid_engine.recalibrate import MIN_CV_IMPROVEMENT_PCT, decide_and_maybe_write
from hybrid_engine.utils.io import decode_raw, load_image_linear
from tools.calibrate import collect_local_pairs


def _load_all():
    pairs = [(r, j) for r, j in _official_find_pairs()]
    n_official = len(pairs)
    pairs += [(p["raw_path"], p["jpeg_path"]) for p in collect_local_pairs()
              if p["scene_type"] != "chart"]
    n_contributed = len(pairs) - n_official
    print(f"공식 {n_official}쌍 + 기여 {n_contributed}쌍 = 총 {len(pairs)}쌍")

    dataset = []
    for i, (raw_path, target_path) in enumerate(pairs):
        print(f"  [{i + 1}/{len(pairs)}] 로드 중: {os.path.basename(raw_path)}", flush=True)
        try:
            linear = decode_raw(raw_path)
        except Exception as e:
            print(f"    디코드 실패, 스킵: {e}")
            continue
        linear_small = _resize_max_dim(linear, CALIB_MAX_DIM)
        camera_wb = color_matrix.extract_camera_metadata(raw_path)["camera_whitebalance"]
        target_small = load_image_linear(target_path, resize_to=linear_small.shape[:2])
        dataset.append((linear_small, camera_wb, target_small))
    return dataset, len(pairs)


def main():
    parser = argparse.ArgumentParser(description="공식+기여 전체 하셀블라드 페어로 recalibrate 게이트 실행")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--n-folds", type=int, default=4)
    parser.add_argument("--min-improvement-pct", type=float, default=MIN_CV_IMPROVEMENT_PCT)
    args = parser.parse_args()

    dataset, total = _load_all()
    print(f"\n로드 완료: {len(dataset)}/{total}쌍\n")
    if not dataset:
        return

    decide_and_maybe_write(
        dataset, f"공식+기여 전체 {len(dataset)}쌍", n_folds=args.n_folds,
        min_improvement_pct=args.min_improvement_pct, write=args.write)


if __name__ == "__main__":
    main()
