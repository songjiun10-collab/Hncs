"""[research] verify_historical_chart_matrix.py가 확인한 챠트 10장
leave-one-out 교차검증 매트릭스(ΔE00 2.779, 현재 배포 매트릭스 10.786보다
훨씬 좋음)가 실사진에서도 그런지 확인 - 챠트는 통제된 조명/피사체라
실제 다양한 장면에 일반화 안 될 수 있다(사용자 지적). X2D II 100C
실사진 147쌍(breakdown_by_generation.py가 쓴 것과 같은 데이터)에
챠트 매트릭스를 적용해서 카메라 자체 JPEG 대비 ΔE00을 재고, 현재 배포
매트릭스(21.521, breakdown_by_generation.py 기록)와 비교한다.

  python3 -m hybrid_engine.verify_chart_matrix_on_photos
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from hybrid_engine.calibrate_profile import _resize_max_dim, CALIB_MAX_DIM, _mean_loss, _DEFAULT_PARAMS
from hybrid_engine.core import color_matrix
from hybrid_engine.utils.io import decode_raw, load_image_linear
from tools.calibrate import collect_local_pairs

TARGET_GENERATION = "X2D II 100C"
REPORT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "datasets", "hasselblad", "contributed", "kmichels-x2dii-2026-07", "colorchecker_matrix_report.json")
PROFILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "assets", "profiles", "hasselblad.json")


def main():
    with open(REPORT_PATH, encoding="utf-8") as f:
        report = json.load(f)
    chart_matrix = report["chart_matrix_in_sample"]

    with open(PROFILE_PATH, encoding="utf-8") as f:
        shipped_profile = json.load(f)
    shipped_profile.pop("_comment", None)

    chart_profile = dict(_DEFAULT_PARAMS)
    chart_profile["raw_baseline_matrix"] = chart_matrix
    chart_profile["normalize_exposure"] = False  # 매트릭스 적용시 권장(EVALUATION.md 후속 실측 6)

    items = [p for p in collect_local_pairs()
              if p["generation"] == TARGET_GENERATION and p["scene_type"] != "chart"]
    print(f"{TARGET_GENERATION} {len(items)}쌍")

    shipped_losses, chart_losses = [], []
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
        dataset = [(linear_small, camera_wb, target_small)]
        shipped_losses.append(_mean_loss(shipped_profile, dataset))
        chart_losses.append(_mean_loss(chart_profile, dataset))

    print(f"\n=== {TARGET_GENERATION} 실사진 {len(shipped_losses)}쌍 ===")
    print(f"현재 배포 hasselblad.json: 평균 ΔE00={np.mean(shipped_losses):.3f}  "
          f"(참고 - breakdown_by_generation.py 기록값 21.521)")
    print(f"챠트 10장 교차검증된 매트릭스로 교체: 평균 ΔE00={np.mean(chart_losses):.3f}")
    improvement = (np.mean(shipped_losses) - np.mean(chart_losses)) / np.mean(shipped_losses) * 100
    print(f"개선폭: {improvement:+.1f}%")


if __name__ == "__main__":
    main()
