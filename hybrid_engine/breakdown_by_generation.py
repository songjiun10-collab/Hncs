"""[research] recalibrate_full_contributed.py가 확인한 "487쌍 풀에서
ΔE 14.379로 나쁨" 현상이 특정 바디/세대에 몰린 건지 확인 - 새로 매트릭스를
학습하지 않고, 지금 배포된 hasselblad.json 그대로 페어별 ΔE00을 계산해서
tools.calibrate._generation_for()의 세대 라벨로 묶어 평균/표준편차를 낸다.

  python3 -m hybrid_engine.breakdown_by_generation
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import numpy as np

from hybrid_engine.calibrate_profile import _find_pairs as _official_find_pairs
from hybrid_engine.calibrate_profile import _resize_max_dim, CALIB_MAX_DIM, _mean_loss
from hybrid_engine.core import color_matrix
from hybrid_engine.utils.io import decode_raw, load_image_linear
from tools.calibrate import collect_local_pairs, _generation_for


def main():
    profile_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "assets", "profiles", "hasselblad.json")
    with open(profile_path, encoding="utf-8") as f:
        profile = json.load(f)
    profile.pop("_comment", None)

    items = []  # (raw_path, jpeg_path, generation)
    for r, j in _official_find_pairs():
        items.append((r, j, "공식(raw_calib_cache)"))
    for p in collect_local_pairs():
        if p["scene_type"] == "chart":
            continue
        items.append((p["raw_path"], p["jpeg_path"], p["generation"]))

    print(f"총 {len(items)}쌍")
    per_gen = defaultdict(list)
    for i, (raw_path, jpeg_path, gen) in enumerate(items):
        print(f"  [{i + 1}/{len(items)}] {gen}: {os.path.basename(raw_path)}", flush=True)
        try:
            linear = decode_raw(raw_path)
        except Exception as e:
            print(f"    디코드 실패, 스킵: {e}")
            continue
        linear_small = _resize_max_dim(linear, CALIB_MAX_DIM)
        camera_wb = color_matrix.extract_camera_metadata(raw_path)["camera_whitebalance"]
        target_small = load_image_linear(jpeg_path, resize_to=linear_small.shape[:2])
        loss = _mean_loss(profile, [(linear_small, camera_wb, target_small)])
        per_gen[gen].append(loss)

    print("\n=== 세대별 ΔE00 (기존 hasselblad.json 기준) ===")
    for gen in sorted(per_gen, key=lambda g: -np.mean(per_gen[g])):
        losses = per_gen[gen]
        print(f"{gen}: n={len(losses)}  평균={np.mean(losses):.3f}  "
              f"표준편차={np.std(losses):.3f}  최대={np.max(losses):.3f}")


if __name__ == "__main__":
    main()
