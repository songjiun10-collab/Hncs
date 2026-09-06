"""X2D II 100C DCP v3 재발급 - **매트릭스 값은 v2 그대로, 슬롯 순서만
Adobe 관례(1=저온/StdA, 2=고온/D65)로 스왑**한다.

**왜**: v2(`tools/refit_x2dii_dual_illuminant_v2_illuminant_referenced.py`,
2026-09-04)는 `CalibrationIlluminant1=21(D65, 6504K)`,
`2=17(StdA, 2856K)`로 온도 내림차순이었다. RawTherapee
`rtengine/dcp.cc`의 매트릭스 보간 경로(`findXyztoCamera` 1690-1697행,
`makeXyzCam` 1820-1827행)는 `temperature_1 < temperature_2` 정렬을
검증 없이 전제해서 `if (wbtemp <= temperature_1) mix = 1.0`에 6504K
이하 **모든** 촬영(텅스텐 2856K 포함)이 걸려 무조건 ColorMatrix1(D65)로
스냅됐다 - RT에서 dual-illuminant가 사실상 죽어 D65 단일 매트릭스로
동작했다. 근본원인 확정과 실렌더 증거는 `hybrid_engine/EVALUATION.md`
"RawTherapee illuminant1 스냅 근본원인 확정 (2026-09-04)" 절과
`tools/analyze_x2dii_rt_illuminant_order_snap.py` /
`tools/analyze_x2dii_rt_render_swap_test.py` 참고.

**왜 재fit이 아니라 스왑인가**: 매트릭스 값 자체는 v2가 25장 held-out
end-to-end로 검증한 것 그대로 쓴다(CI=[+5.5509,+9.2794], 25/0). 이
프로젝트의 `core/dcp_interpolate.py` 보간은 슬롯 스왑에 **수학적으로
불변**이다 - 같은 중립색에 대해 g는 1-g로 뒤집히지만 최종 보간
매트릭스는 동일하다(이 스크립트가 `verify_swap_invariance()`로 매번
재확인, 2026-09-04 실행값 max|Δ|=8.9e-16). 따라서 v2의 통계적 근거가
그대로 승계되고, 재fit(=dpreview 25장 RAW 재디코드)은 필요 없다 -
애초에 dpreview raw는 Cloudflare 차단으로 현재 재확보 불가다.

**사용자 승인**: 2026-09-04, 근본원인 조사 보고 후 "새로 발급 ㄱㄱ"
(Never-list 파일 `hybrid_engine/assets/profiles/hasselblad_x2dii_chart.dcp`
변경에 대한 명시적, 그 자리에서의 승인). 승인된 범위는 "매트릭스 값은
그대로 두고 태그만 Adobe 관례로 스왑" - 재캘리브레이션이 아니다.

  ~/.hncs-hybrid-venv312/bin/python3 -m tools.reissue_x2dii_dcp_v3_adobe_illuminant_order
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from core.dcp_export import write_dcp, read_dcp, TAG_PROFILE_EMBED_POLICY
from core.dcp_interpolate import interpolate_dng_matrix

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DPREVIEW_DIR = os.path.join(BASE, "datasets", "hasselblad", "contributed",
                            "dpreview-x2dii100c-studio-chart-2026-09")
IN_REPORT_V2 = os.path.join(DPREVIEW_DIR,
                            "dual_illuminant_report_v2_illuminant_referenced.json")
OUT_REPORT_V3 = os.path.join(DPREVIEW_DIR,
                             "dual_illuminant_report_v3_adobe_illuminant_order.json")
OUT_DCP = os.path.join(BASE, "hybrid_engine", "assets", "profiles",
                       "hasselblad_x2dii_chart.dcp")

UNIQUE_CAMERA_MODEL = "Hasselblad 100-22-Coated6"
PROFILE_NAME = ("HNCS X2D II Chart Colorimetric "
                "(dual-illuminant v3, Adobe illuminant order)")
# Adobe 관례: 슬롯1이 저온, 슬롯2가 고온. v2의 슬롯 내용이 서로 바뀐다.
ILLUMINANT_1_ENUM = 17  # Standard Light A(2856K) <- v2의 illuminant2/group2
ILLUMINANT_2_ENUM = 21  # D65(6504K)              <- v2의 illuminant1/group1

TAG_UNIQUE_CAMERA_MODEL = 50708
TAG_CALIBRATION_ILLUMINANT_1 = 50778
TAG_CALIBRATION_ILLUMINANT_2 = 50779
TAG_COLOR_MATRIX_1 = 50721
TAG_COLOR_MATRIX_2 = 50722


def verify_swap_invariance(report_v2):
    """스왑이 `core/dcp_interpolate.py` 결과를 바꾸지 않는지 배포 전에
    확인한다 - v2의 25장 통계 검증을 v3가 승계한다는 주장의 근거."""
    cm1_v2 = np.array(report_v2["dcp_color_matrix_1"], dtype=np.float64)
    cm2_v2 = np.array(report_v2["dcp_color_matrix_2"], dtype=np.float64)
    out = {}
    worst = 0.0
    for key in ("group1_daylight_like", "group2_tungsten_like"):
        neutral = np.array(
            report_v2[key]["measured_native_neutral_g_normalized"],
            dtype=np.float64)
        m_v2, g_v2 = interpolate_dng_matrix(neutral, cm1_v2, 21, cm2_v2, 17)
        m_v3, g_v3 = interpolate_dng_matrix(neutral, cm2_v2, 17, cm1_v2, 21)
        delta = float(np.max(np.abs(m_v2 - m_v3)))
        worst = max(worst, delta)
        out[key] = {
            "g_v2_toward_slot1_d65": float(g_v2),
            "g_v3_toward_slot1_stda": float(g_v3),
            "g_sum_should_be_1": float(g_v2 + g_v3),
            "final_matrix_max_abs_diff": delta,
        }
        print(f"  {key}: g_v2={g_v2:.6f} -> g_v3={g_v3:.6f} "
              f"(합={g_v2 + g_v3:.6f}), 최종매트릭스 max|Δ|={delta:.3e}")
    if worst > 1e-9:
        raise SystemExit(f"스왑 불변성 깨짐(max|Δ|={worst:.3e}) - 발급 중단")
    return out


def main():
    with open(IN_REPORT_V2, encoding="utf-8") as f:
        v2 = json.load(f)

    print("스왑 불변성 확인(발급 전 게이트):")
    invariance = verify_swap_invariance(v2)

    # v2 슬롯 내용을 그대로 교차 배치한다 - 값은 한 자리도 안 바꾼다.
    dcp_cm1_v3 = v2["dcp_color_matrix_2"]  # StdA 매트릭스 -> 슬롯1
    dcp_cm2_v3 = v2["dcp_color_matrix_1"]  # D65 매트릭스  -> 슬롯2

    write_dcp(OUT_DCP, camera_model=UNIQUE_CAMERA_MODEL,
              profile_name=PROFILE_NAME,
              color_matrix_1=dcp_cm1_v3,
              calibration_illuminant_1=ILLUMINANT_1_ENUM,
              color_matrix_2=dcp_cm2_v3,
              calibration_illuminant_2=ILLUMINANT_2_ENUM)

    tags = read_dcp(OUT_DCP)
    print(f"\nDCP 재발급(v3, Adobe illuminant order): {OUT_DCP}")
    print(f"  UniqueCameraModel = {tags[TAG_UNIQUE_CAMERA_MODEL]!r}")
    print(f"  CalibrationIlluminant1 = {tags[TAG_CALIBRATION_ILLUMINANT_1]}"
          f" (17=Standard Light A, 2856K)")
    print(f"  CalibrationIlluminant2 = {tags[TAG_CALIBRATION_ILLUMINANT_2]}"
          f" (21=D65, 6504K)")
    print(f"  temperature_1 < temperature_2 (Adobe 관례 충족): "
          f"{2856.0 < 6504.0}")
    print(f"  ProfileEmbedPolicy present = {TAG_PROFILE_EMBED_POLICY in tags}")

    # 파일에 실제로 쓰인 값이 v2 매트릭스와 비트 단위로 같은지(교차) 확인
    file_cm1 = np.asarray(tags[TAG_COLOR_MATRIX_1]).reshape(3, 3)
    file_cm2 = np.asarray(tags[TAG_COLOR_MATRIX_2]).reshape(3, 3)
    d1 = float(np.max(np.abs(file_cm1 - np.array(v2["dcp_color_matrix_2"]))))
    d2 = float(np.max(np.abs(file_cm2 - np.array(v2["dcp_color_matrix_1"]))))
    print(f"  슬롯1 == v2 dcp_color_matrix_2: max|Δ|={d1:.3e}")
    print(f"  슬롯2 == v2 dcp_color_matrix_1: max|Δ|={d2:.3e}")
    # DCP는 매트릭스를 SRATIONAL로 저장하므로 리포트의 float64와 왕복하면
    # ~5e-7의 양자화 오차가 남는다 - v2 배포본을 되읽어도 같은 크기가
    # 나온다(2026-09-04 확인: 슬롯1 3.912e-07, 슬롯2 4.784e-07). 값이
    # 뒤바뀌었거나 다른 매트릭스가 들어간 경우는 자릿수가 완전히 다르다.
    if max(d1, d2) > 1e-5:
        raise SystemExit("파일 내용이 v2 매트릭스와 불일치 - 확인 필요")

    report = {
        "camera_model": "Hasselblad X2D II 100C",
        "supersedes": os.path.basename(IN_REPORT_V2),
        "change": "매트릭스 값 변경 없음. CalibrationIlluminant 슬롯 순서만 "
                  "Adobe 관례(1=저온 StdA/17, 2=고온 D65/21)로 스왑 - v2는 "
                  "1=D65/21, 2=StdA/17로 온도 내림차순이었다.",
        "why": "RawTherapee rtengine/dcp.cc의 매트릭스 보간 경로"
               "(findXyztoCamera 1690-1697행, makeXyzCam 1820-1827행)가 "
               "temperature_1 < temperature_2 정렬을 검증 없이 전제해, "
               "온도 내림차순 DCP에서는 wbtemp <= temperature_1 분기에 모든 "
               "정상 촬영이 걸려 무조건 ColorMatrix1로 스냅됐다. Adobe DNG "
               "SDK dng_color_spec.cpp(183-208행)는 역순이면 스스로 스왑하므로 "
               "ACR/Lightroom은 v2에서도 정상이었을 것으로 예상(레퍼런스 코드 "
               "기준). 근본원인 조사는 EVALUATION.md 2026-09-04 절 참고.",
        "matrices_unchanged_from_v2": True,
        "swap_invariance_check": {
            "note": "core/dcp_interpolate.py는 슬롯 스왑에 불변 - g는 1-g로 "
                    "뒤집히지만 최종 보간 매트릭스는 동일하다. 따라서 v2의 "
                    "25장 held-out end-to-end 검증(CI=[+5.5509,+9.2794], "
                    "25/0)이 v3에 그대로 승계된다.",
            "per_group": invariance,
        },
        "slot_1": {
            "calibration_illuminant": ILLUMINANT_1_ENUM,
            "illuminant_name": "Standard Light A",
            "cct_k": 2856.0,
            "source": "v2 dcp_color_matrix_2 (group2 tungsten-like fit)",
            "reference_illuminant_xy":
                v2["group2_tungsten_like"]["reference_illuminant_xy"],
            "measured_native_neutral_g_normalized":
                v2["group2_tungsten_like"]["measured_native_neutral_g_normalized"],
        },
        "slot_2": {
            "calibration_illuminant": ILLUMINANT_2_ENUM,
            "illuminant_name": "D65",
            "cct_k": 6504.0,
            "source": "v2 dcp_color_matrix_1 (group1 daylight-like fit)",
            "reference_illuminant_xy":
                v2["group1_daylight_like"]["reference_illuminant_xy"],
            "measured_native_neutral_g_normalized":
                v2["group1_daylight_like"]["measured_native_neutral_g_normalized"],
        },
        "color_matrix_1": v2["color_matrix_2"],
        "color_matrix_2": v2["color_matrix_1"],
        "dcp_color_matrix_1": dcp_cm1_v3,
        "dcp_color_matrix_2": dcp_cm2_v3,
        "inherited_validation_from_v2": v2["full25_held_out_end_to_end"],
        "note": "사용자 승인(2026-09-04, 근본원인 조사 보고 후 '새로 발급 ㄱㄱ')으로 "
                "배포. 승인 범위는 태그 순서 스왑 - 재캘리브레이션 아님. "
                "v2/v1 리포트는 기록으로 그대로 남아있다.",
    }
    with open(OUT_REPORT_V3, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n저장: {OUT_REPORT_V3}")


if __name__ == "__main__":
    main()
