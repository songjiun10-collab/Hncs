"""[research] fit_matrix_from_chart.py가 낸 2.318은 B_31325 한 장으로
피팅하고 같은 장에서 측정한 in-sample 값이라 과적합 의심을 벗어날 수
없다(사용자 지적). datasets/hasselblad/contributed/kmichels-x2dii-2026-07/
colorchecker_matrix_report.json에 이미 10장 전체로 피팅 + leave-one-out
교차검증까지 끝난 매트릭스(chart_matrix_in_sample, cv 평균 2.779 - in-sample
2.689와 거의 차이 없어 과적합 아님 확인됨)가 있다 - 이걸 오늘 복구한
B_31325 한 장에 다시 적용해서 리포트에 기록된 값(3.68)과 내 코드가
같은 결과를 내는지 교차검증한다(파이프라인 자체의 정확성 검증).

  python3 -m hybrid_engine.verify_historical_chart_matrix
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
REPORT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "datasets", "hasselblad", "contributed", "kmichels-x2dii-2026-07", "colorchecker_matrix_report.json")
PROFILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "assets", "profiles", "hasselblad.json")


def main():
    with open(REPORT_PATH, encoding="utf-8") as f:
        report = json.load(f)
    historical_matrix = np.array(report["chart_matrix_in_sample"])
    reported_b31325 = report["chart_matrix_in_sample_delta_e_per_image"]["B_31325.3FR"]
    reported_cv_mean = report["chart_matrix_cv_delta_e_mean"]
    reported_in_sample_mean = report["chart_matrix_in_sample_delta_e_mean"]

    print(f"디코드: {CHART_RAW}")
    linear = decode_raw(CHART_RAW)
    samples = chart_baseline.detect_and_sample(linear)
    if samples is None:
        print("차트 검출 실패")
        return

    de_no_matrix = chart_baseline.patch_delta_e(samples)
    de_historical = chart_baseline.patch_delta_e(samples @ historical_matrix)

    with open(PROFILE_PATH, encoding="utf-8") as f:
        profile = json.load(f)
    shipped_matrix = np.array(profile["raw_baseline_matrix"])
    de_shipped = chart_baseline.patch_delta_e(samples @ shipped_matrix)

    print(f"\n매트릭스 없음: {np.mean(de_no_matrix):.3f} "
          f"(리포트 기록: {report['baseline_delta_e_per_image']['B_31325.3FR']:.3f})")
    print(f"현재 배포 hasselblad.json 매트릭스: {np.mean(de_shipped):.3f}")
    print(f"과거 챠트 10장 교차검증된 매트릭스 (B_31325 재적용): {np.mean(de_historical):.3f} "
          f"(리포트 기록값: {reported_b31325:.3f})")
    print(f"\n참고 - 리포트 전체 10장 평균: in-sample={reported_in_sample_mean:.3f}  "
          f"leave-one-out CV={reported_cv_mean:.3f} (차이 {(reported_cv_mean-reported_in_sample_mean)/reported_in_sample_mean*100:+.1f}% - 과적합 아님)")


if __name__ == "__main__":
    main()
