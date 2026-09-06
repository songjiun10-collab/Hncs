"""[research] verify_chart_matrix_on_photos.py가 확인한 대로 챠트로
검증된 매트릭스를 실사진에 넣어도 개선이 거의 없었다(+0.1%) - Phase 0
(매트릭스) 문제가 아니라 Phase 1/2(톤/채도 커브)가 진짜 원인일 거라는
가설. 이 스크립트는 두 가지를 확인한다:

  1) 분포 - X2D II 100C 147쌍의 ΔE00이 고르게 나쁜지, 일부 이상치가
     평균을 끌어올리는지 (breakdown_by_generation.py는 평균/표준편차만
     냈음 - 표준편차 9.17이 평균 21.5 대비 커서 분포 확인 필요, "평균
     차이만으로 결론내지 않는다" 원칙).
  2) 매트릭스 고정 + 톤/채도만 재학습 - `coordinate_descent()`는
     `_SEARCH_SPACE`(contrast_n/highlight_rolloff_start/shadow_lift/
     sat_gain/max_chroma)만 탐색하고 `raw_baseline_matrix`는 base_params
     그대로 둔다 - 현재 배포 매트릭스를 고정한 채 톤/채도만 X2D II
     147쌍으로 재학습해서 Phase 1/2가 진짜 원인인지 직접 검증.

  python3 -m hybrid_engine.verify_x2dii_tone_only
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from hybrid_engine.calibrate_profile import (
    _resize_max_dim, CALIB_MAX_DIM, _mean_loss, coordinate_descent)
from hybrid_engine.core import color_matrix
from hybrid_engine.utils.io import decode_raw, load_image_linear
from tools.calibrate import collect_local_pairs

TARGET_GENERATION = "X2D II 100C"
PROFILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "assets", "profiles", "hasselblad.json")


def main():
    with open(PROFILE_PATH, encoding="utf-8") as f:
        shipped_profile = json.load(f)
    shipped_profile.pop("_comment", None)

    items = [p for p in collect_local_pairs()
              if p["generation"] == TARGET_GENERATION and p["scene_type"] != "chart"]
    print(f"{TARGET_GENERATION} {len(items)}쌍 로드 중...")

    dataset = []
    per_pair_loss = []
    for i, p in enumerate(items):
        print(f"  [{i + 1}/{len(items)}] {os.path.basename(p['raw_path'])}", flush=True)
        try:
            linear = decode_raw(p["raw_path"])
        except Exception as e:
            print(f"    디코드 실패, 스킵: {e}")
            continue
        linear_small = _resize_max_dim(linear, CALIB_MAX_DIM)
        camera_wb = color_matrix.extract_camera_metadata(p["raw_path"])["camera_whitebalance"]
        target_small = load_image_linear(p["jpeg_path"], resize_to=linear_small.shape[:2])
        item = (linear_small, camera_wb, target_small)
        dataset.append(item)
        per_pair_loss.append((os.path.basename(p["raw_path"]), _mean_loss(shipped_profile, [item])))

    losses = np.array([l for _, l in per_pair_loss])
    print(f"\n=== 1) 분포 (현재 배포 매트릭스, n={len(losses)}) ===")
    print(f"평균={losses.mean():.3f}  중앙값={np.median(losses):.3f}  표준편차={losses.std():.3f}")
    print(f"25%ile={np.percentile(losses, 25):.3f}  75%ile={np.percentile(losses, 75):.3f}  "
          f"90%ile={np.percentile(losses, 90):.3f}")
    for lo, hi in [(0, 10), (10, 20), (20, 30), (30, 40), (40, 100)]:
        n_in_bin = int(((losses >= lo) & (losses < hi)).sum())
        print(f"  ΔE00 [{lo:>2},{hi:>3}): {n_in_bin}장 ({n_in_bin / len(losses) * 100:.0f}%)")
    worst = sorted(per_pair_loss, key=lambda x: -x[1])[:5]
    print("최악 5장:", ", ".join(f"{n}({l:.1f})" for n, l in worst))

    print(f"\n=== 2) 매트릭스 고정 + 톤/채도만 재학습 (4-fold CV) ===")
    baseline_mean = losses.mean()
    print(f"현재 배포 파이프라인(매트릭스+톤/채도 전부 기존): {baseline_mean:.3f}")

    n_folds = 4
    rng = np.random.default_rng(0)
    order = rng.permutation(len(dataset))
    folds = np.array_split(order, n_folds)
    fold_losses = []
    for fi, fold_idx in enumerate(folds):
        fold_idx_set = set(fold_idx.tolist())
        train_set = [d for i, d in enumerate(dataset) if i not in fold_idx_set]
        held_out = [dataset[i] for i in fold_idx]
        tuned_params, _ = coordinate_descent(train_set, base_params=shipped_profile)
        fold_loss = _mean_loss(tuned_params, held_out)
        fold_losses.append(fold_loss)
        print(f"  fold {fi + 1}/{n_folds} ΔE={fold_loss:.3f}", flush=True)

    cv_mean = float(np.mean(fold_losses))
    improvement = (baseline_mean - cv_mean) / baseline_mean * 100
    print(f"\n매트릭스 고정, 톤/채도만 X2D II로 재학습(4-fold CV): {cv_mean:.3f} ({improvement:+.1f}%)")


if __name__ == "__main__":
    main()
