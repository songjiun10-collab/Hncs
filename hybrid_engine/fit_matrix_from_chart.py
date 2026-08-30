"""[research] verify_x2dii_chart.py가 확인한 대로 현재 배포된
hasselblad.json의 매트릭스가 X2D II 100C ColorChecker 챠트에서 rawpy
기본 디코드보다 -116.9% 더 나쁘다 - raw+jpeg 페어 기반 재보정
(recalibrate_x2dii100c.py, 게이트는 통과했지만 챠트로 검증 안 함) 대신
챠트 24패치에서 직접 3x3 매트릭스를 최소자승 피팅한다(hasselblad.json
v1.3의 X2D II 챠트 pooling과 같은 방법, `hybrid_engine/core/raw_baseline.py`의
fit_color_matrix 재사용). 챠트 1장(24패치)이면 9개 미지수(3x3 매트릭스)
피팅에 이미 과결정(overdetermined) - 10장 다 필요한 게 아니라 노이즈
평균용일 뿐이라는 판단으로 1장만 사용.

  python3 -m hybrid_engine.fit_matrix_from_chart
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from hybrid_engine.core import chart_baseline, raw_baseline
from hybrid_engine.utils.io import decode_raw

CHART_RAW = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "datasets", "hasselblad", "contributed", "kmichels-x2dii-2026-07", "raw", "B_31325.3FR")
PROFILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "assets", "profiles", "hasselblad.json")


def main():
    print(f"디코드: {CHART_RAW}")
    linear = decode_raw(CHART_RAW)

    samples = chart_baseline.detect_and_sample(linear)
    if samples is None:
        print("차트 검출 실패")
        return
    reference = chart_baseline.reference_patches_linear_srgb()

    print("챠트 24패치로 3x3 매트릭스 최소자승 피팅 중...")
    matrix = raw_baseline.fit_color_matrix([samples], [reference])

    fitted_samples = samples @ matrix
    de_fitted = chart_baseline.patch_delta_e(fitted_samples)
    print(f"\n챠트 직접 피팅 매트릭스 (in-sample, 같은 이미지): "
          f"패치별 ΔE00 평균={np.mean(de_fitted):.3f}  최대={np.max(de_fitted):.3f}")

    with open(PROFILE_PATH, encoding="utf-8") as f:
        profile = json.load(f)
    shipped_matrix = np.array(profile["raw_baseline_matrix"])
    shipped_samples = samples @ shipped_matrix
    de_shipped = chart_baseline.patch_delta_e(shipped_samples)
    print(f"현재 배포 hasselblad.json 매트릭스: "
          f"패치별 ΔE00 평균={np.mean(de_shipped):.3f}  최대={np.max(de_shipped):.3f}")

    de_no_matrix = chart_baseline.patch_delta_e(samples)
    print(f"매트릭스 없음(rawpy 기본): "
          f"패치별 ΔE00 평균={np.mean(de_no_matrix):.3f}  최대={np.max(de_no_matrix):.3f}")

    print(f"\n새 매트릭스 (참고용, hasselblad.json에 안 씀):")
    print(json.dumps(matrix.tolist(), indent=2))


if __name__ == "__main__":
    main()
