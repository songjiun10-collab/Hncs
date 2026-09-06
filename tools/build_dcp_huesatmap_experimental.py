"""
`tools/evaluate_dcp_huesatmap_srgb.py`가 확인한 sRGB HSV hue-only 보정을
실제 DCP 파일로 만든다 - `tools/dcp_export_huesatmap_experimental.py`
(core/dcp_export.py 격리 사본)로 쓴다. **배포된
`hybrid_engine/assets/profiles/hasselblad_x2dii_chart.dcp`(Never-list)는
건드리지 않는다** - 별도 실험 파일
`hasselblad_x2dii_chart_huesatmap_experimental.dcp`로 낸다.

N=8division/sigma=30(DNG 관례에 가까운 보수적 값 - `tools/evaluate_dcp_huesatmap_srgb.py`
스윕에서 N을 8~24로 늘려도 -4.98%~-5.04%로 수렴/포화하는 걸 확인해서
과적합 신호 없이 고른 값)로 전체 9장 홀드아웃 없이 학습한 hue 테이블을
`ProfileHueSatMapEncoding=1`(sRGB) 인코딩으로 쓴다. sat_scale/val_scale은
전부 1.0(안 건드림) - 이 실험은 hue만 검증했다.

**실기기 미검증**: `core/dcp_export.py`의 매직 넘버/UniqueCameraModel
버그가 실기기 테스트 전까진 안 잡혔던 것과 같은 리스크가 이 신규
태그에도 그대로 있다. Lightroom이 열어보기 전까진 "이론상 맞는 파일"
수준이다.

  python3 -m tools.build_dcp_huesatmap_experimental
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from hybrid_engine.core import chart_baseline, raw_baseline
from hybrid_engine.utils.io import decode_raw_native
from tools.evaluate_dcp_irls_weighted import _irls_fit
from tools.evaluate_dcp_huesatmap_srgb import (
    _xyz_d50_to_srgb_gamma, _rgb_to_hsv, _fit_hue_table,
)
from tools.dcp_export_huesatmap_experimental import write_dcp, read_dcp

SET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "datasets", "hasselblad", "contributed", "kmichels-x2dii-2026-07")
REPORT_JSON = os.path.join(SET_DIR, "camera_native_matrix_report.json")
OUT_DCP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "hybrid_engine", "assets", "profiles",
                        "hasselblad_x2dii_chart_huesatmap_experimental.dcp")

UNIQUE_CAMERA_MODEL = "Hasselblad 100-22-Coated6"
PROFILE_NAME = "HNCS X2D II Chart Colorimetric HueSatMap Experimental"
N_DIVISIONS = 8


def main():
    reference = chart_baseline.reference_patches_xyz_d50()
    ref_rgb_gamma = _xyz_d50_to_srgb_gamma(reference)
    ref_h, ref_s, ref_v = _rgb_to_hsv(ref_rgb_gamma)

    raw_paths = sorted(glob.glob(os.path.join(SET_DIR, "raw", "*.3FR")))
    per_image = {}
    for raw_path in raw_paths:
        name = os.path.basename(raw_path)
        print(f"  디코드+검출 중: {name}", flush=True)
        native = decode_raw_native(raw_path)
        samples = chart_baseline.detect_and_sample(native)
        if samples is None:
            continue
        per_image[name] = samples
    names = sorted(per_image.keys())
    print(f"\n검출 성공 {len(names)}장")

    init_weights = np.array([1.0 if i in range(18, 24) else 4.0 for i in range(24)])
    init_weights[17] = 2.0
    final_weights, chart_m = _irls_fit(list(per_image.values()), [reference] * len(names), init_weights)
    dcp_color_matrix_1 = np.linalg.inv(chart_m).T

    pred_hsv_list = []
    for nm in names:
        xyz_pred = raw_baseline.apply_color_matrix(per_image[nm], chart_m)
        rgb_gamma = _xyz_d50_to_srgb_gamma(xyz_pred)
        pred_hsv_list.append(_rgb_to_hsv(rgb_gamma))

    table = _fit_hue_table(pred_hsv_list, ref_h, ref_s)
    print(f"hue shift 테이블(도, {N_DIVISIONS}division): {np.round(table, 3).tolist()}")

    hue_sat_map_data = np.zeros((N_DIVISIONS, 1, 1, 3))
    hue_sat_map_data[:, 0, 0, 0] = table
    hue_sat_map_data[:, 0, 0, 1] = 1.0
    hue_sat_map_data[:, 0, 0, 2] = 1.0

    write_dcp(OUT_DCP, camera_model=UNIQUE_CAMERA_MODEL, profile_name=PROFILE_NAME,
              color_matrix_1=dcp_color_matrix_1, calibration_illuminant_1=23,
              hue_sat_map_dims=(N_DIVISIONS, 1, 1), hue_sat_map_data=hue_sat_map_data,
              hue_sat_map_encoding=1)
    tags = read_dcp(OUT_DCP)
    print(f"\n출력: {OUT_DCP}")
    print(f"  UniqueCameraModel = {tags[50708]!r}")
    print(f"  HueSatMapDims = {tags[50937]}")
    print(f"  HueSatMapEncoding = {tags[51107]}")
    recovered_table = tags[50938].reshape(N_DIVISIONS, 1, 1, 3)[:, 0, 0, 0]
    print(f"  라운드트립 hue 테이블 일치 = {np.allclose(recovered_table, table, atol=1e-3)}")

    with open(REPORT_JSON, encoding="utf-8") as f:
        report = json.load(f)
    report["huesatmap_experimental_dims"] = [N_DIVISIONS, 1, 1]
    report["huesatmap_experimental_hue_shift_table_deg"] = table.tolist()
    report["huesatmap_experimental_encoding"] = 1
    report["_comment_huesatmap_experimental"] = (
        "2026-09-01: 실험용 - 배포된 hasselblad_x2dii_chart.dcp/"
        "chart_matrix_in_sample_irls_cyan_init와 무관. "
        "tools/evaluate_dcp_huesatmap_srgb.py 9장 LOO(부트스트랩 CI 없음, "
        "N=8~24 스윕에서 -4.98%~-5.04%로 포화 확인, 단조성으로 신호 판정) "
        "기준 -4.98%(N=8,sigma=30). hasselblad_x2dii_chart_huesatmap_experimental.dcp"
        "로만 출력했고 배포된 .dcp는 그대로다 - 실기기(Lightroom) 미검증."
    )
    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"저장: {REPORT_JSON}")


if __name__ == "__main__":
    main()
