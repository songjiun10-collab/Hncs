"""
사용자 승인(2026-09-01, "ㅇ")으로 DCP 챠트 매트릭스를 Huber IRLS(무채색
-4x 가중치에서 시작)로 재피팅해서 실제 배포 반영한다 -
`tools/evaluate_dcp_irls_weighted.py`가 9장 전체 LOO로 확인한 결과 기준
(부트스트랩 CI 없음, 단조성으로 신호 판정 - `hybrid_engine/EVALUATION.md`
참고): 균등가중 LOO ΔE00 2.8588 대비 무채색-4x에서 시작한 IRLS가 LOO
ΔE00 2.6078까지 낮췄다(개선폭 -8.8%, 앞서 배포한 무채색-4x 단독 -4.9%보다
더 낮음).

kmichels-x2dii-2026-07 챠트 9장 전체로 홀드아웃 없이 IRLS를 수렴시켜
최종 배포용 매트릭스를 얻고, `camera_native_matrix_report.json`을
갱신한 뒤 .dcp를 재발급한다.

  python3 -m tools.refit_dcp_irls_final
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
from tools.evaluate_dcp_irls_weighted import _irls_fit

SET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "datasets", "hasselblad", "contributed", "kmichels-x2dii-2026-07")
REPORT_JSON = os.path.join(SET_DIR, "camera_native_matrix_report.json")
OUT_DCP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "hybrid_engine", "assets", "profiles", "hasselblad_x2dii_chart.dcp")

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

    chroma_init = np.array([1.0 if i in range(18, 24) else 4.0 for i in range(24)])
    sources = [per_image[nm] for nm in names]
    targets = [reference for _ in names]

    final_weights, chart_m = _irls_fit(sources, targets, chroma_init)
    in_sample = float(np.mean([_mean_de(raw_baseline.apply_color_matrix(per_image[nm], chart_m),
                                         reference) for nm in names]))
    print(f"\nIRLS 수렴 가중치: {np.round(final_weights, 3).tolist()}")
    print(f"전체 표본 in-sample ΔE00 = {in_sample:.4f}")

    dcp_color_matrix_1 = np.linalg.inv(chart_m).T

    with open(REPORT_JSON, encoding="utf-8") as f:
        report = json.load(f)
    report["chart_matrix_in_sample_irls"] = chart_m.tolist()
    report["dcp_color_matrix_1_irls"] = dcp_color_matrix_1.tolist()
    report["chart_matrix_in_sample_delta_e_mean_irls"] = in_sample
    report["irls_final_weights"] = final_weights.tolist()
    report["_comment_irls"] = (
        "2026-09-01: chart_matrix_in_sample_irls/dcp_color_matrix_1_irls는 "
        "무채색-4x 초기값에서 시작한 Huber IRLS(iteratively reweighted "
        "least squares) - tools/evaluate_dcp_irls_weighted.py 9장 LOO 기준 "
        "(부트스트랩 CI 없음, 단조성으로 신호 판정) -8.8%(2.8588->2.6078) "
        "확인 후 사용자 승인으로 채택. _weighted(무채색-4x 단독, -4.9%)와 "
        "원래 균등가중 필드 둘 다 기록용으로 보존."
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
