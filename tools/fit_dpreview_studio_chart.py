"""dpreview 스튜디오씬 공용 챠트 위젯에서 받은 진짜 ColorChecker Classic
24패치 RAW로 챠트 기반 컬러매트릭스를 피팅해 DCP+ICC를 발급한다 -
`tools/dpreview/fit_leica_sl3p_studio_chart.py`(2026-09-02, Leica SL3-P 최초 적용)를
여러 브랜드에 재사용하도록 일반화한 버전(2026-09-06). 방법론은 동일:
무채색 6패치(인덱스 18-23) 대비 유채색 18패치 3x 가중 최소자승
(`raw_baseline.fit_color_matrix(weights=...)`), 전체 표본으로 최종 매트릭스
피팅 + in-sample ΔE00 보고(발급용 - CV/부트스트랩 CI는 `validate_dpreview_
chart_brand.py`가 이미 그 브랜드의 `chart_validation_report.json`으로
검증 완료한 별개 단계, 이 스크립트는 그 검증을 통과한 브랜드에 대해서만
돌린다).

**사용자 승인(2026-09-06)**: canon/nikon/panasonic/sigma/ricoh_gr/olympus/
pentax 7개 브랜드 전부 `chart_validation_report.json`의 부트스트랩 95% CI가
0을 넘지 않는 뚜렷한 개선(+21.7%~+61.2%)을 보여 발급 승인("ㅇㅇ ㄱ").
이후 재다운로드한 동일 발급 표본으로 리포트를 갱신했고 최신 수치는
`hybrid_engine/EVALUATION.md`의 2026-09-06 정정 블록에 기록했다.

  python3 -m tools.fit_dpreview_studio_chart <RAW 폴더> <brand> \
      <camera 표시명> <ext> --unique-camera-model <Adobe 내부 코드명> [--illuminant N]
  예: python3 -m tools.fit_dpreview_studio_chart \
      datasets/canon/contributed/dpreview-r6iii-studio-chart-2026-09/raw \
      canon "Canon EOS R6 Mark III" cr3
"""
import argparse
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

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_WEIGHT = 3.0


def _mean_de(samples_xyz, reference):
    return float(np.mean(chart_baseline.patch_delta_e_xyz_d50(samples_xyz, reference)))


def _validate_issuance_inputs(raw_dir, brand, camera_display_name, names):
    """Fail closed unless the exact detected sample set was cross-validated."""
    report_path = os.path.join(os.path.dirname(raw_dir.rstrip(os.sep)),
                               "chart_validation_report.json")
    if not os.path.exists(report_path):
        raise FileNotFoundError(
            f"검증 리포트 없음: {report_path} - 발급 전에 validate_dpreview_chart_brand를 실행해야 함"
        )
    with open(report_path, encoding="utf-8") as handle:
        validation = json.load(handle)
    if validation.get("brand") != brand or validation.get("camera") != camera_display_name:
        raise ValueError("검증 리포트의 brand/camera가 발급 입력과 다름")
    expected = set(validation.get("images", []))
    actual = set(names)
    if expected != actual:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(
            f"표본 불일치: 검증 {len(expected)}장/발급 {len(actual)}장, "
            f"검증에만 있음={missing[:3]}, 발급에만 있음={extra[:3]}"
        )


def fit_and_issue(raw_dir, brand, camera_display_name, ext, illuminant=23,
                  camera_model=None):
    if not camera_model or camera_model == camera_display_name:
        raise ValueError(
            "Adobe DNG Converter로 확인한 UniqueCameraModel을 camera_model로 명시해야 함; "
            "EXIF 표시명을 재사용하면 안 됨"
        )
    reference = chart_baseline.reference_patches_xyz_d50()
    raw_paths = sorted(glob.glob(os.path.join(raw_dir, f"*.{ext}")) +
                        glob.glob(os.path.join(raw_dir, f"*.{ext.upper()}")))

    per_image = {}
    fail = 0
    for rp in raw_paths:
        name = os.path.basename(rp)
        try:
            native = decode_raw_native(rp)
            samples = chart_baseline.detect_and_sample(native)
        except Exception as e:
            fail += 1
            print(f"  검출 실패(예외 {type(e).__name__}), 제외: {name}")
            continue
        if samples is None:
            fail += 1
            print(f"  검출 실패, 제외: {name}")
            continue
        per_image[name] = samples
    names = sorted(per_image.keys())
    n = len(names)
    print(f"검출 성공 {n}/{len(raw_paths)}장 (실패 {fail})")
    if n < 3:
        print("표본 부족, 종료")
        return None
    _validate_issuance_inputs(raw_dir, brand, camera_display_name, names)

    weights = np.array([1.0 if i in range(18, 24) else CHROMA_WEIGHT for i in range(24)])
    sources = [per_image[nm] for nm in names]
    targets = [reference for _ in names]
    train_weights = [weights for _ in names]

    chart_m = raw_baseline.fit_color_matrix(sources, targets, weights=train_weights, ridge=0.1)
    in_sample = float(np.mean([_mean_de(raw_baseline.apply_color_matrix(per_image[nm], chart_m),
                                         reference) for nm in names]))
    print(f"전체 표본({n}장) in-sample ΔE00 = {in_sample:.4f}")

    dcp_color_matrix_1 = np.linalg.inv(chart_m).T

    out_dcp = os.path.join(BASE, "hybrid_engine", "assets", "profiles", f"{brand}_chart.dcp")
    out_icc = os.path.join(BASE, "hybrid_engine", "assets", "profiles", f"{brand}_chart.icc")
    out_report = os.path.join(raw_dir, os.pardir, "camera_native_matrix_report.json")

    report = {
        "brand": brand,
        "camera": camera_display_name,
        "unique_camera_model": camera_model,
        "n_images": n,
        "n_failed_detect": fail,
        "images": names,
        "chroma_patch_weight": CHROMA_WEIGHT,
        "chart_matrix_in_sample": chart_m.tolist(),
        "chart_matrix_in_sample_delta_e_mean": in_sample,
        "dcp_color_matrix_1": dcp_color_matrix_1.tolist(),
        "_comment": (
            "tools/fit_dpreview_studio_chart.py - tools/fit_leica_sl3p_studio_"
            "chart.py(2026-09-02)의 일반화판. 무채색 6패치(인덱스 18-23) 대비 "
            "유채색 18패치 3x 가중 최소자승, ridge=0.1, 전체 표본으로 최종 "
            "매트릭스 피팅. 이 브랜드의 챠트 보정 유의성(부트스트랩 95% CI)은 "
            "같은 폴더의 chart_validation_report.json(validate_dpreview_chart_"
            "brand.py, k-fold CV)에서 별도로 검증됨 - 이 리포트는 CV가 아니라 "
            "발급용 in-sample 피팅. camera는 표시명이고, DCP에는 Adobe DNG "
            "Converter로 확인한 UniqueCameraModel을 별도로 기록한다."
        ),
    }
    with open(out_report, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"저장: {out_report}")

    write_dcp(out_dcp, camera_model=camera_model, profile_name=f"HNCS {camera_display_name} Chart Colorimetric",
              color_matrix_1=dcp_color_matrix_1, calibration_illuminant_1=illuminant)
    tags = read_dcp(out_dcp)
    print(f"DCP 발급: {out_dcp}")
    print(f"  UniqueCameraModel = {tags[50708]!r}")
    print(f"  ProfileEmbedPolicy present = {TAG_PROFILE_EMBED_POLICY in tags}")

    write_icc_matrix_trc_profile(out_icc, chart_m, description=f"HNCS {camera_display_name} Chart Colorimetric")
    print(f"ICC 발급: {out_icc}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_dir")
    parser.add_argument("brand")
    parser.add_argument("camera_display_name")
    parser.add_argument("ext")
    parser.add_argument("--unique-camera-model", required=True,
                        help="Adobe DNG Converter로 확인한 DCP UniqueCameraModel")
    parser.add_argument("--illuminant", type=int, default=23,
                         help="EXIF LightSource enum (기본 23=D50, chart_baseline 기준과 일치)")
    args = parser.parse_args()
    fit_and_issue(args.raw_dir, args.brand, args.camera_display_name, args.ext,
                  args.illuminant, args.unique_camera_model)


if __name__ == "__main__":
    main()
