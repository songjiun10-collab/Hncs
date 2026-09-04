"""X2D II 100C v2 DCP가 RawTherapee에서 group2(텅스텐성)인데도
illuminant1(D65)로 스냅되는 근본원인 재도출 - RT `rtengine/dcp.cc`(5.13,
dev와 동일 확인)의 매트릭스 보간 알고리즘을 그대로 포팅해서 우리
`core/dcp_interpolate.py`(DNG 스펙 재현)와 나란히 돌려본다.

**배경**: 2026-09-04 v2 재배포 직후 `rawtherapee-cli` 재검증에서
dpreview group2 실제 이미지(챠트 실측 R/G=0.646, 확실한 텅스텐성)의
`DCPIlluminant=0`(자동보간) 렌더가 `=1`(D65 강제)과 픽셀 단위로 동일했다
(`hybrid_engine/EVALUATION.md` "v2 재배포 + RawTherapee 재검증" 절).
우리 수학(`core/dcp_interpolate.py`)은 같은 중립색에 g=0.0176
(illuminant2/StdA 쪽)을 내는데 RT는 정반대로 스냅한 미해결 불일치.

**가설(이 스크립트가 검증)**: RT `dcp.cc`의 매트릭스 보간 경로
(`findXyztoCamera` 1690-1697행, `makeXyzCam` 1820-1827행)는

    if (wbtemp <= temperature_1)      mix = 1.0;   // -> ColorMatrix1
    else if (wbtemp >= temperature_2) mix = 0.0;   // -> ColorMatrix2
    else                              mix = mired 선형보간;

로 **temperature_1 < temperature_2 정렬을 전제**한다(Adobe 관례:
CalibrationIlluminant1=StdA(2856K), 2=D65(6504K)). 같은 파일의
`makeHueSatMap`(1967행)에는 `reverse = temperature_1 > temperature_2`
스왑 처리가 있지만 매트릭스 경로에는 없다. 우리 v2 DCP는
CalibrationIlluminant1=21(D65, 6504K), 2=17(StdA, 2856K)로 **역순**이라
wbtemp가 6504K 이하인 모든 정상 촬영(텅스텐 ~2856K 포함)이
`wbtemp <= temperature_1`에 걸려 무조건 mix=1.0(ColorMatrix1)이 된다 -
관찰된 "항상 illuminant1로 스냅"과 정확히 일치.

**방법**: RT의 `xyCoordToTemperature`(DNG SDK Robertson uv 테이블
방식)와 `neutralToXy` 고정점 반복, 비스왑 mix 공식을 그대로 포팅.
배포된 `.dcp`를 `core.dcp_export.read_dcp`로 **읽기만** 하고(Never-list,
수정 없음), v2 리포트의 group1/group2 실측 중립색을 넣어

  (a) 현재 태그 순서(T1=6504, T2=2856)에서 RT 로직의 mix
  (b) 스왑 순서(T1=2856, T2=6504, 매트릭스도 스왑)에서 RT 로직의 mix
  (c) 우리 `core.dcp_interpolate.interpolate_dng_matrix`의 g

를 비교하고, Robertson vs McCamy CCT 차이도 같은 xy에서 정량화해
"CCT 근사식 차이가 원인이 아님"을 못박는다.

**사용자 승인**: 이 조사 자체가 사용자 지시("페이블 ㄱㄱ", task-brief
`.superpowers/sdd/x2dii-rt-asshotneutral-investigation/task-brief.md`).
읽기 전용 분석 - 배포 파일 수정 없음.

실행: ~/.hncs-hybrid-venv312/bin/python3 -m tools.analyze_x2dii_rt_illuminant_order_snap
"""
import json
import numpy as np

from core.dcp_export import read_dcp
from core.dcp_interpolate import (interpolate_dng_matrix, _xyz_to_xy,
                                  _cct_from_xy, STANDARD_ILLUMINANT_CCT_K)

DCP_PATH = "hybrid_engine/assets/profiles/hasselblad_x2dii_chart.dcp"
REPORT_PATH = ("datasets/hasselblad/contributed/"
               "dpreview-x2dii100c-studio-chart-2026-09/"
               "dual_illuminant_report_v2_illuminant_referenced.json")
OUT_PATH = ("datasets/hasselblad/contributed/"
            "dpreview-x2dii100c-studio-chart-2026-09/"
            "rt_illuminant_order_root_cause_report.json")

TAG_COLOR_MATRIX_1 = 0xC621
TAG_COLOR_MATRIX_2 = 0xC622
TAG_CALIBRATION_ILLUMINANT_1 = 0xC65A
TAG_CALIBRATION_ILLUMINANT_2 = 0xC65B

# RT dcp.cc 294-326행의 DNG SDK Robertson isotemperature 테이블 그대로.
_RT_TEMP_TABLE = [
    (0, 0.18006, 0.26352, -0.24341), (10, 0.18066, 0.26589, -0.25479),
    (20, 0.18133, 0.26846, -0.26876), (30, 0.18208, 0.27119, -0.28539),
    (40, 0.18293, 0.27407, -0.30470), (50, 0.18388, 0.27709, -0.32675),
    (60, 0.18494, 0.28021, -0.35156), (70, 0.18611, 0.28342, -0.37915),
    (80, 0.18740, 0.28668, -0.40955), (90, 0.18880, 0.28997, -0.44278),
    (100, 0.19032, 0.29326, -0.47888), (125, 0.19462, 0.30141, -0.58204),
    (150, 0.19962, 0.30921, -0.70471), (175, 0.20525, 0.31647, -0.84901),
    (200, 0.21142, 0.32312, -1.0182), (225, 0.21807, 0.32909, -1.2168),
    (250, 0.22511, 0.33439, -1.4512), (275, 0.23247, 0.33904, -1.7298),
    (300, 0.24010, 0.34308, -2.0637), (325, 0.24702, 0.34655, -2.4681),
    (350, 0.25591, 0.34951, -2.9641), (375, 0.26400, 0.35200, -3.5814),
    (400, 0.27218, 0.35407, -4.3633), (425, 0.28039, 0.35577, -5.3762),
    (450, 0.28863, 0.35714, -6.7262), (475, 0.29685, 0.35823, -8.5955),
    (500, 0.30505, 0.35907, -11.324), (525, 0.31320, 0.35968, -15.628),
    (550, 0.32129, 0.36011, -23.325), (575, 0.32931, 0.36038, -40.770),
    (600, 0.33724, 0.36051, -116.45),
]


def rt_xy_coord_to_temperature(xy):
    """RT dcp.cc `xyCoordToTemperature`(285-379행) 축자 포팅 - DNG SDK
    `dng_temperature`의 Robertson uv 최근접 등온선 방식."""
    x, y = xy
    u = 2.0 * x / (1.5 - x + 6.0 * y)
    v = 3.0 * y / (1.5 - x + 6.0 * y)
    last_dt = 0.0
    res = 0.0
    for index in range(1, 31):
        du, dv = 1.0, _RT_TEMP_TABLE[index][3]
        length = np.sqrt(1.0 + dv * dv)
        du, dv = du / length, dv / length
        uu = u - _RT_TEMP_TABLE[index][1]
        vv = v - _RT_TEMP_TABLE[index][2]
        dt = -uu * dv + vv * du
        if dt <= 0.0 or index == 30:
            dt = max(-dt, 0.0)
            f = 0.0 if index == 1 else dt / (last_dt + dt)
            res = 1.0e6 / (_RT_TEMP_TABLE[index - 1][0] * f
                           + _RT_TEMP_TABLE[index][0] * (1.0 - f))
            break
        last_dt = dt
    return res


def rt_mix(wbtemp, temperature_1, temperature_2):
    """RT dcp.cc `findXyztoCamera`/`makeXyzCam`의 mix 공식(1690-1697,
    1820-1827행) 축자 포팅 - **스왑 처리 없음**이 요점."""
    if wbtemp <= temperature_1:
        return 1.0
    if wbtemp >= temperature_2:
        return 0.0
    inv_t = 1.0 / wbtemp
    return ((inv_t - 1.0 / temperature_2)
            / (1.0 / temperature_1 - 1.0 / temperature_2))


def rt_neutral_to_xy_and_mix(neutral, cm1, cm2, temperature_1, temperature_2):
    """RT dcp.cc `neutralToXy`(1714-1745행) 고정점 반복 축자 포팅.
    preferred_illuminant=0(자동) 경로만. 반환: (xy, wbtemp, mix)."""
    last_xy = (0.3457, 0.3585)  # D50 시작점(RT 1720행)
    neutral = np.asarray(neutral, dtype=np.float64)
    for _ in range(30):
        mix = rt_mix(rt_xy_coord_to_temperature(last_xy),
                     temperature_1, temperature_2)
        cm = cm1 if mix >= 1.0 else (cm2 if mix <= 0.0
                                     else mix * cm1 + (1.0 - mix) * cm2)
        xyz = np.linalg.inv(cm) @ neutral
        next_xy = _xyz_to_xy(xyz)
        if abs(next_xy[0] - last_xy[0]) + abs(next_xy[1] - last_xy[1]) < 1e-7:
            last_xy = next_xy
            break
        last_xy = next_xy
    wbtemp = rt_xy_coord_to_temperature(last_xy)
    return last_xy, wbtemp, rt_mix(wbtemp, temperature_1, temperature_2)


def main():
    tags = read_dcp(DCP_PATH)
    cm1 = np.asarray(tags[TAG_COLOR_MATRIX_1]).reshape(3, 3)
    cm2 = np.asarray(tags[TAG_COLOR_MATRIX_2]).reshape(3, 3)
    ill1 = int(tags[TAG_CALIBRATION_ILLUMINANT_1])
    ill2 = int(tags[TAG_CALIBRATION_ILLUMINANT_2])
    t1 = STANDARD_ILLUMINANT_CCT_K[ill1]
    t2 = STANDARD_ILLUMINANT_CCT_K[ill2]

    report_json = json.load(open(REPORT_PATH))
    neutrals = {
        "group1_daylight_like": report_json["group1_daylight_like"][
            "measured_native_neutral_g_normalized"],
        "group2_tungsten_like": report_json["group2_tungsten_like"][
            "measured_native_neutral_g_normalized"],
    }

    out = {
        "dcp_path": DCP_PATH,
        "calibration_illuminant_1": ill1, "temperature_1_k": t1,
        "calibration_illuminant_2": ill2, "temperature_2_k": t2,
        "rt_source": ("rtengine/dcp.cc @ tag 5.13 (dev와 diff 없음 확인); "
                      "mix 공식 1690-1697/1820-1827행, 스왑은 "
                      "makeHueSatMap 1967행에만 존재"),
        "cases": {},
    }

    print(f"DCP: illuminant1={ill1}({t1}K), illuminant2={ill2}({t2}K)"
          f" -> temperature_1 > temperature_2 (역순): {t1 > t2}")

    for name, neutral in neutrals.items():
        # (a) RT 로직, 현재 태그 순서 그대로
        xy_a, wbtemp_a, mix_a = rt_neutral_to_xy_and_mix(
            neutral, cm1, cm2, t1, t2)
        # (b) RT 로직, 스왑 순서(매트릭스/온도 함께 스왑 - Adobe 관례 순서)
        xy_b, wbtemp_b, mix_b = rt_neutral_to_xy_and_mix(
            neutral, cm2, cm1, t2, t1)
        # (c) 우리 DNG 스펙 재현
        _, g_ours = interpolate_dng_matrix(neutral, cm1, ill1, cm2, ill2)
        # CCT 근사식 차이(같은 수렴 xy에서)
        mccamy = _cct_from_xy(*xy_a)
        robertson = rt_xy_coord_to_temperature(xy_a)

        case = {
            "neutral_g_normalized": list(map(float, neutral)),
            "rt_as_shipped": {
                "converged_xy": [round(v, 6) for v in xy_a],
                "wbtemp_k": round(wbtemp_a, 1),
                "mix": round(mix_a, 6),
                "selected": ("ColorMatrix1" if mix_a >= 1.0 else
                             "ColorMatrix2" if mix_a <= 0.0 else "interpolated"),
            },
            "rt_swapped_order": {
                "converged_xy": [round(v, 6) for v in xy_b],
                "wbtemp_k": round(wbtemp_b, 1),
                "mix_toward_slot1_stda": round(mix_b, 6),
                "weight_on_original_cm1_d65": round(1.0 - mix_b, 6),
                "selected": ("StdA matrix(원래 CM2)" if mix_b >= 1.0 else
                             "D65 matrix(원래 CM1)" if mix_b <= 0.0
                             else "interpolated"),
            },
            "ours_dng_spec_g_toward_cm1": round(float(g_ours), 6),
            "cct_method_delta_at_same_xy": {
                "mccamy_k": round(mccamy, 1),
                "robertson_rt_k": round(robertson, 1),
                "abs_diff_k": round(abs(mccamy - robertson), 1),
            },
        }
        out["cases"][name] = case
        print(f"\n[{name}] neutral={neutral}")
        print(f"  (a) RT 현재 순서 : wbtemp={wbtemp_a:7.1f}K mix={mix_a:.4f}"
              f" -> {case['rt_as_shipped']['selected']}")
        print(f"  (b) RT 스왑 순서 : wbtemp={wbtemp_b:7.1f}K"
              f" 원래CM1(D65) 가중치={1.0 - mix_b:.4f}"
              f" -> {case['rt_swapped_order']['selected']}")
        print(f"  (c) 우리 DNG 재현: g(CM1 가중치)={g_ours:.4f}")
        print(f"  CCT 근사식 차이: McCamy={mccamy:.1f}K"
              f" vs Robertson(RT)={robertson:.1f}K"
              f" (|Δ|={abs(mccamy - robertson):.1f}K)")

    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(f"\n리포트 저장: {OUT_PATH}")


if __name__ == "__main__":
    main()
