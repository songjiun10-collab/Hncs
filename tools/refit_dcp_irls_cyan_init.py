"""
사용자 승인(2026-09-01, "ㄱㄱ 해")으로 DCP 챠트 매트릭스를 재피팅해서
실제 배포 반영한다 - 기존 IRLS(무채색-4x 초기값)의 챠트 매치 잔차를
패치별로 뜯어보니 patch 17(cyan)만 9장 전부에서 평균 ΔE00=7.166
(표준편차 0.977 - 노이즈 아니라 구조적)로 다른 패치(다음 최악
3.695)보다 압도적으로 나빴다. cyan의 IRLS 초기가중치를 4.0에서
2.0으로 낮춰 재수렴시키면 9장 LOO ΔE00이 2.6078에서 2.5942로
추가 개선된다(-0.52%, 1.0/0.5/0.2는 도로 나빠지는 U자형 최적점 -
`tools/evaluate_dcp_irls_weighted.py`가 쓰는 것과 같은
`_irls_fit()`으로 확인, 부트스트랩 CI는 n=9라 불가능해서 단조성으로
신호 판정). 24개 패치를 전부 이런 식으로 손대면 표본 9장에 대한
과적합이라 여기서 멈춘다 - cyan 하나만, 패치별 잔차가 압도적으로
컸다는 물리적 근거가 있는 조정.

kmichels-x2dii-2026-07 챠트 9장 전체로 홀드아웃 없이 IRLS를 수렴시켜
최종 배포용 매트릭스를 얻고, `camera_native_matrix_report.json`을
갱신한 뒤 .dcp를 재발급한다.

  python3 -m tools.refit_dcp_irls_cyan_init
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
CYAN_PATCH_INDEX = 17
CYAN_INIT_WEIGHT = 2.0


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

    init_weights = np.array([1.0 if i in range(18, 24) else 4.0 for i in range(24)])
    init_weights[CYAN_PATCH_INDEX] = CYAN_INIT_WEIGHT
    sources = [per_image[nm] for nm in names]
    targets = [reference for _ in names]

    final_weights, chart_m = _irls_fit(sources, targets, init_weights)
    in_sample = float(np.mean([_mean_de(raw_baseline.apply_color_matrix(per_image[nm], chart_m),
                                         reference) for nm in names]))
    print(f"\nIRLS 수렴 가중치: {np.round(final_weights, 3).tolist()}")
    print(f"전체 표본 in-sample ΔE00 = {in_sample:.4f}")

    dcp_color_matrix_1 = np.linalg.inv(chart_m).T

    with open(REPORT_JSON, encoding="utf-8") as f:
        report = json.load(f)
    report["chart_matrix_in_sample_irls_cyan_init"] = chart_m.tolist()
    report["dcp_color_matrix_1_irls_cyan_init"] = dcp_color_matrix_1.tolist()
    report["chart_matrix_in_sample_delta_e_mean_irls_cyan_init"] = in_sample
    report["irls_cyan_init_final_weights"] = final_weights.tolist()
    report["_comment_irls_cyan_init"] = (
        "2026-09-01: chart_matrix_in_sample_irls_cyan_init/"
        "dcp_color_matrix_1_irls_cyan_init는 patch 17(cyan) 잔차가 9장 "
        "전부에서 평균 ΔE00=7.166(표준편차 0.977)로 다른 패치보다 "
        "압도적으로 나빴던 걸 발견하고, cyan의 IRLS 초기가중치만 4.0에서 "
        "2.0으로 낮춰 재수렴시킨 결과 - tools/evaluate_dcp_irls_weighted.py "
        "와 같은 _irls_fit()으로 9장 LOO 확인(부트스트랩 CI 없음, 단조성으로 "
        "신호 판정) -0.52%(2.6078->2.5942, U자형 최적점 확인됨) 후 사용자 "
        "승인으로 채택. 24개 패치 전부 이런 식으로 튜닝하면 n=9 표본 "
        "과적합이라 cyan 하나(물리적 근거 있는 이상값)에서 멈춤. "
        "_irls(무채색-4x 단독, -8.8%)와 원래 필드들은 기록용으로 보존."
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
