"""이미 커밋된 camera_native_matrix_report.json(analyze_camera_native_matrix.py
산출물)에서 매트릭스/조명값을 읽어 hybrid_engine/assets/profiles/
hasselblad_x2dii_chart.dcp를 write_dcp()의 현재(수정된) 버전으로 재발급한다.

**왜 필요한가**: core/dcp_export.py의 매직 넘버(0x4352)/UniqueCameraModel
원인 확정 수정(2026-08-31, 이 세션) 이후에도 이미 커밋된 .dcp 파일
자체는 구버전 write_dcp()로 만들어진 그대로였다 - 코드는 고쳤지만
산출물은 안 바뀐 상태. 이 스크립트가 그 갱신을 담당한다. UniqueCameraModel은
Chris Schmauch가 Adobe DNG Converter로 실제 X2D II 100C RAW를 변환해서
확인한 내부 코드네임("Hasselblad 100-22-Coated6")을 쓴다 - EXIF Model
문자열이 아니다(그걸 쓰면 Lightroom이 매칭 대상으로 안 보여준다).

  python3 -m tools.regenerate_x2dii_dcp
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from core.dcp_export import write_dcp, read_dcp, TAG_PROFILE_EMBED_POLICY

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_JSON = os.path.join(BASE, "datasets", "hasselblad", "contributed",
                           "kmichels-x2dii-2026-07", "camera_native_matrix_report.json")
OUT_DCP = os.path.join(BASE, "hybrid_engine", "assets", "profiles",
                       "hasselblad_x2dii_chart.dcp")

# Adobe DNG Converter로 실제 X2D II 100C RAW를 변환해야 나오는 내부
# 코드네임 - EXIF Make/Model이 아니다. core/dcp_export.py의 2026-08-31
# 정정 참조.
UNIQUE_CAMERA_MODEL = "Hasselblad 100-22-Coated6"
PROFILE_NAME = "HNCS X2D II Chart Colorimetric"


def main():
    with open(REPORT_JSON, encoding="utf-8") as f:
        report = json.load(f)

    color_matrix_1 = np.array(report["dcp_color_matrix_1"], dtype=np.float64)
    calibration_illuminant_1 = report["calibration_illuminant"]["chosen_enum"]

    write_dcp(OUT_DCP, camera_model=UNIQUE_CAMERA_MODEL, profile_name=PROFILE_NAME,
              color_matrix_1=color_matrix_1, calibration_illuminant_1=calibration_illuminant_1)

    tags = read_dcp(OUT_DCP)
    print(f"재발급: {OUT_DCP}")
    print(f"  UniqueCameraModel = {tags[50708]!r}")
    print(f"  ProfileName = {tags[50936]!r}")
    print(f"  CalibrationIlluminant1 = {tags[50778]}")
    print(f"  ProfileEmbedPolicy present = {TAG_PROFILE_EMBED_POLICY in tags}")
    with open(OUT_DCP, "rb") as f:
        magic = f.read(8)[2:4]
    print(f"  magic bytes = {magic.hex()}")


if __name__ == "__main__":
    main()
