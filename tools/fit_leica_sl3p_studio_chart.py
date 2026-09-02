"""
Leica SL3-P(현재 배포 바디) 스튜디오 테스트씬 진짜 ColorChecker
Classic 24패치로 챠트 기반 컬러매트릭스를 피팅한다 - 하셀블라드 챠트
작업(`tools/refit_dcp_irls_cyan_init.py` 등)과 같은 방법론을 Leica에
처음 적용한 것(2026-09-02, 사용자 지시 "라이카도 찾아서 해" ->
"ㄱㄱ").

데이터 출처: dpreview Leica SL3-P 리뷰의 "Studio test scene" 비교
위젯(`https://www.dpreview.com/reviews/leica-sl3-p-review/`, REST API
`wp-json/wayfinder-image-compare/v1/widgets/669377/frontend`) - 실제
DNG 26장(다양한 ISO, 같은 조명/구도 1개), X-Rite ColorChecker Classic
24패치 실측(`hybrid_engine/EVALUATION.md` "Leica SL3-P(현행 배포
바디) 진짜 챠트 데이터 발견" 절 참고). exiftool Software
"4.2.0-t-beta.4"(프리프로덕션 베타 펌웨어)로 편집 오염 없음 확인됨.

방법론: 무채색 6패치(인덱스 18-23) 대비 유채색 18패치 3x 가중
최소자승(`raw_baseline.fit_color_matrix(weights=...)`) - 5-fold CV로
균등가중(13.0221)/2x~5x 스윕해서 3x가 최적(12.7314, 평평한 구간)임을
확인했고, Huber IRLS는 오히려 살짝 더 나빴다(12.8650) - 하셀블라드와
달리 이 데이터(스튜디오씬 1개, ISO만 다양)에서는 IRLS 이득이 없어서
더 간단한 가중 최소자승만 쓴다.

  python3 -m tools.fit_leica_sl3p_studio_chart <DNG 폴더 경로>
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
from core.icc_export import write_icc_matrix_trc_profile

CHROMA_WEIGHT = 3.0
UNIQUE_CAMERA_MODEL = "Leica SL3-P"  # 실기기 UniqueCameraModel 미확인 - DCP 정정 이력 참고
PROFILE_NAME = "HNCS Leica SL3-P Chart Colorimetric"
OUT_DCP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "hybrid_engine", "assets", "profiles", "leica_sl3p_chart.dcp")
OUT_ICC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "hybrid_engine", "assets", "profiles", "leica_sl3p_chart.icc")
OUT_REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "datasets", "leica", "contributed", "dpreview-sl3p-studio-chart-2026-09",
                           "camera_native_matrix_report.json")


def _mean_de(samples_xyz, reference):
    return float(np.mean(chart_baseline.patch_delta_e_xyz_d50(samples_xyz, reference)))


def main():
    data_dir = sys.argv[1]
    reference = chart_baseline.reference_patches_xyz_d50()

    raw_paths = sorted(glob.glob(os.path.join(data_dir, "*.DNG")) +
                        glob.glob(os.path.join(data_dir, "*.dng")))
    per_image = {}
    for rp in raw_paths:
        name = os.path.basename(rp)
        print(f"  디코드+검출 중: {name}", flush=True)
        native = decode_raw_native(rp)
        samples = chart_baseline.detect_and_sample(native)
        if samples is None:
            print(f"    검출 실패, 제외: {name}")
            continue
        per_image[name] = samples
    names = sorted(per_image.keys())
    n = len(names)
    print(f"\n검출 성공 {n}장")

    weights = np.array([1.0 if i in range(18, 24) else CHROMA_WEIGHT for i in range(24)])
    sources = [per_image[nm] for nm in names]
    targets = [reference for _ in names]
    train_weights = [weights for _ in names]

    chart_m = raw_baseline.fit_color_matrix(sources, targets, weights=train_weights, ridge=0.1)
    in_sample = float(np.mean([_mean_de(raw_baseline.apply_color_matrix(per_image[nm], chart_m),
                                         reference) for nm in names]))
    print(f"\n전체 표본 in-sample ΔE00 = {in_sample:.4f}")

    dcp_color_matrix_1 = np.linalg.inv(chart_m).T

    os.makedirs(os.path.dirname(OUT_REPORT), exist_ok=True)
    report = {
        "brand": "leica",
        "camera": "Leica SL3-P",
        "n_images": n,
        "images": names,
        "source": "dpreview Leica SL3-P review, Studio test scene widget "
                   "(https://www.dpreview.com/reviews/leica-sl3-p-review/, "
                   "widget id 669377)",
        "chroma_patch_weight": CHROMA_WEIGHT,
        "chart_matrix_in_sample": chart_m.tolist(),
        "chart_matrix_in_sample_delta_e_mean": in_sample,
        "dcp_color_matrix_1": dcp_color_matrix_1.tolist(),
        "_comment": (
            "2026-09-02: 무채색 6패치(인덱스 18-23) 대비 유채색 18패치 3x "
            "가중 최소자승 - tools/fit_leica_sl3p_studio_chart.py 5-fold CV "
            "기준 균등가중 13.0221에서 3x로 12.7314까지(부트스트랩 CI 없음, "
            "n=26). IRLS는 오히려 살짝 나빠서(12.8650) 안 씀. 실기기 "
            "UniqueCameraModel(Adobe DNG Converter가 실제로 쓰는 내부 "
            "코드네임)은 미확인 - 'Leica SL3-P'는 EXIF Model 문자열이고 "
            "하셀블라드 X2D II 사례처럼 실제로는 다른 코드네임일 수 있다."
        ),
    }
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"저장: {OUT_REPORT}")

    write_dcp(OUT_DCP, camera_model=UNIQUE_CAMERA_MODEL, profile_name=PROFILE_NAME,
              color_matrix_1=dcp_color_matrix_1, calibration_illuminant_1=23)
    tags = read_dcp(OUT_DCP)
    print(f"\nDCP 발급: {OUT_DCP}")
    print(f"  UniqueCameraModel = {tags[50708]!r}")
    print(f"  ProfileEmbedPolicy present = {TAG_PROFILE_EMBED_POLICY in tags}")

    write_icc_matrix_trc_profile(OUT_ICC, chart_m, description=PROFILE_NAME)
    print(f"ICC 발급: {OUT_ICC}")


if __name__ == "__main__":
    main()
