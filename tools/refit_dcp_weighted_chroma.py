"""
사용자 승인(2026-09-01, "ㅇㅇ")으로 DCP 챠트 매트릭스를 무채색 6패치
가중치 낮춘(유채색 4x) 최소자승으로 재피팅해서 실제 배포 반영한다 -
`tools/evaluate_dcp_weighted_patches.py`가 9장 전체 LOO로 확인한
-4.9%(2.8588->2.7179, 3.5x~5x 구간 평평한 진짜 신호) 근거.

kmichels-x2dii-2026-07 챠트 9장(B_31325~B_31333, B_31334는 manifest에
URL 자체가 없어서 복구 불가 - `tools/recover_kmichels_x2dii_chart.py`
참고) 전체로 홀드아웃 없이 최종 배포용 매트릭스를 피팅하고,
`camera_native_matrix_report.json`을 갱신한 뒤
`tools/regenerate_x2dii_dcp.py`와 같은 방식으로 .dcp를 재발급한다.

  python3 -m tools.refit_dcp_weighted_chroma
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from hybrid_engine.core import chart_baseline, raw_baseline
from hybrid_engine.utils.io import decode_raw_native
from core.dcp_export import write_dcp, read_dcp, TAG_PROFILE_EMBED_POLICY

SET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "datasets", "hasselblad", "contributed", "kmichels-x2dii-2026-07")
REPORT_JSON = os.path.join(SET_DIR, "camera_native_matrix_report.json")
OUT_DCP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "hybrid_engine", "assets", "profiles", "hasselblad_x2dii_chart.dcp")

CHROMA_WEIGHT = 4.0  # patch 18-23(무채색 6패치) 제외 전부 4x - 9장 LOO로 확정한 최적점
UNIQUE_CAMERA_MODEL = "Hasselblad 100-22-Coated6"
PROFILE_NAME = "HNCS X2D II Chart Colorimetric"


def _mean_de(samples_xyz, reference):
    return float(np.mean(chart_baseline.patch_delta_e_xyz_d50(samples_xyz, reference)))


def main():
    reference = chart_baseline.reference_patches_xyz_d50()
    raw_paths = sorted(glob.glob(os.path.join(SET_DIR, "raw", "*.3FR")))
    per_image = {}
    for raw_path in raw_paths:
        name = os.path.basename(raw_path)
        print(f"  디코드+검출 중: {name}", flush=True)
        native = decode_raw_native(raw_path)
        samples = chart_baseline.detect_and_sample(native)
        if samples is None:
            print(f"    검출 실패, 제외: {name}")
            continue
        per_image[name] = samples
    names = sorted(per_image.keys())
    n = len(names)
    print(f"\n검출 성공 {n}장: {names}")

    weights = np.array([1.0 if i in range(18, 24) else CHROMA_WEIGHT for i in range(24)])
    sources = [per_image[nm] for nm in names]
    targets = [reference for _ in names]
    train_weights = [weights for _ in names]

    chart_m = raw_baseline.fit_color_matrix(sources, targets, weights=train_weights)
    in_sample = float(np.mean([_mean_de(raw_baseline.apply_color_matrix(per_image[nm], chart_m),
                                         reference) for nm in names]))
    print(f"\n가중 최소자승(유채색 {CHROMA_WEIGHT}x) 전체 표본 in-sample ΔE00 = {in_sample:.4f}")

    dcp_color_matrix_1 = np.linalg.inv(chart_m).T

    with open(REPORT_JSON, encoding="utf-8") as f:
        report = json.load(f)
    report["n_images"] = n
    report["images"] = names
    report["chroma_patch_weight"] = CHROMA_WEIGHT
    report["chart_matrix_in_sample_delta_e_mean_weighted"] = in_sample
    report["chart_matrix_in_sample_weighted"] = chart_m.tolist()
    report["dcp_color_matrix_1_weighted"] = dcp_color_matrix_1.tolist()
    report["_comment_weighted"] = (
        "2026-09-01: chart_matrix_in_sample_weighted/dcp_color_matrix_1_weighted는 "
        "무채색 6패치(index 18-23) 제외 유채색 18패치 4x 가중 최소자승 - "
        "tools/evaluate_dcp_weighted_patches.py 9장 LOO 기준 -4.9%(2.8588->2.7179) "
        "확인 후 사용자 승인으로 채택. 원래 chart_matrix_in_sample/dcp_color_matrix_1 "
        "(균등가중, n=10 - B_31334 유실로 지금은 재현 불가)은 기록용으로 보존."
    )
    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"저장: {REPORT_JSON}")

    write_dcp(OUT_DCP, camera_model=UNIQUE_CAMERA_MODEL, profile_name=PROFILE_NAME,
              color_matrix_1=dcp_color_matrix_1, calibration_illuminant_1=23)
    tags = read_dcp(OUT_DCP)
    print(f"\n재발급: {OUT_DCP}")
    print(f"  UniqueCameraModel = {tags[50708]!r}")
    print(f"  ProfileEmbedPolicy present = {TAG_PROFILE_EMBED_POLICY in tags}")
    with open(OUT_DCP, "rb") as f:
        magic = f.read(8)[2:4]
    print(f"  magic bytes = {magic.hex()}")


if __name__ == "__main__":
    main()
