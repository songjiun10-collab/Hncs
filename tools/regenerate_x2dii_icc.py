"""
`tools/regenerate_x2dii_dcp.py`와 같은 방식으로, 커밋된
`camera_native_matrix_report.json`의 매트릭스로 Capture One용 ICC
프로필을 (재)발급한다. 배포된 `.dcp`는 그대로 두고 `.icc`만 새로
쓴다 - `core/icc_export.py` 모듈 docstring 참고(매트릭스 방향/'chad'
필요성/lcms2 2.19로 실측 검증한 내역).

  python3 -m tools.regenerate_x2dii_icc
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from core.icc_export import write_icc_matrix_trc_profile

SET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "datasets", "hasselblad", "contributed", "kmichels-x2dii-2026-07")
REPORT_JSON = os.path.join(SET_DIR, "camera_native_matrix_report.json")
OUT_ICC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "hybrid_engine", "assets", "profiles", "hasselblad_x2dii_chart.icc")

DESCRIPTION = "HNCS X2D II Chart Colorimetric"


def main():
    with open(REPORT_JSON, encoding="utf-8") as f:
        report = json.load(f)
    matrix = np.array(report["chart_matrix_in_sample_irls_cyan_init"])

    write_icc_matrix_trc_profile(OUT_ICC, matrix, description=DESCRIPTION)
    print(f"발급: {OUT_ICC}")

    # 실측 무채색 native RGB로 방향/수치 재확인(모듈 docstring의 검증과 동일 계산)
    neutral = np.array(report["measured_native_neutral_g_normalized"])
    xyz = neutral @ matrix
    xyz_norm = xyz / xyz[1]
    print(f"무채색 native -> XYZ(정규화): {xyz_norm.tolist()}")
    print("D50 기준:                     [0.9642, 1.0, 0.8249]")


if __name__ == "__main__":
    main()
