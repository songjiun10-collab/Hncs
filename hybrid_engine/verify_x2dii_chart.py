"""[research] X2D II 100C 재보정(recalibrate_x2dii100c.py, 게이트 통과 +5.8%)이
진짜 색채측정학적으로 맞는지, 실사진 JPEG 대신 진짜 ColorChecker 정답값으로
확인한다 - chart_baseline.py(GitHub 이슈 #4용)의 cv2.mcc 자동검출 + 공식
분광측정 참조값을 그대로 재사용.

datasets/hasselblad/contributed/kmichels-x2dii-2026-07/의 챠트 1쌍
(B_31325, 구글드라이브에서 복구 - 원래 10연사 중 대표 1장)으로:
  1) rawpy 기본 디코드(매트릭스 없음) ΔE00
  2) 현재 배포된 hasselblad.json의 raw_baseline_matrix 적용 ΔE00
비교. X2D II 전용으로 재학습한 새 매트릭스는 이번 실행에서 저장 안 해뒀어서
(recalibrate_x2dii100c.py를 --write 없이 돌려서 new_params가 파일에 안
남음) 이번엔 "현재 배포본이 챠트 기준으로 이미 나쁜가"부터 확인한다.

  python3 -m hybrid_engine.verify_x2dii_chart
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from hybrid_engine.core import chart_baseline
from hybrid_engine.utils.io import decode_raw

CHART_RAW = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "datasets", "hasselblad", "contributed", "kmichels-x2dii-2026-07", "raw", "B_31325.3FR")
PROFILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "assets", "profiles", "hasselblad.json")


def main():
    print(f"디코드: {CHART_RAW}")
    linear = decode_raw(CHART_RAW)

    print("차트 24패치 검출 중...")
    samples_no_matrix = chart_baseline.detect_and_sample(linear)
    if samples_no_matrix is None:
        print("차트 검출 실패 - 이미지/각도 확인 필요")
        return

    de_no_matrix = chart_baseline.patch_delta_e(samples_no_matrix)
    print(f"\n매트릭스 없음(rawpy 기본): 패치별 ΔE00 평균={np.mean(de_no_matrix):.3f}  "
          f"표준편차={np.std(de_no_matrix):.3f}  최대={np.max(de_no_matrix):.3f}")

    with open(PROFILE_PATH, encoding="utf-8") as f:
        profile = json.load(f)
    matrix = np.array(profile["raw_baseline_matrix"])
    linear_matrixed = np.clip(linear @ matrix, 0, None)
    samples_matrixed = chart_baseline.detect_and_sample(linear_matrixed)
    de_matrixed = chart_baseline.patch_delta_e(samples_matrixed)
    print(f"현재 배포 hasselblad.json 매트릭스 적용: 패치별 ΔE00 평균={np.mean(de_matrixed):.3f}  "
          f"표준편차={np.std(de_matrixed):.3f}  최대={np.max(de_matrixed):.3f}")

    improvement = (np.mean(de_no_matrix) - np.mean(de_matrixed)) / np.mean(de_no_matrix) * 100
    print(f"\n매트릭스 유무 차이: {improvement:+.1f}%")


if __name__ == "__main__":
    main()
