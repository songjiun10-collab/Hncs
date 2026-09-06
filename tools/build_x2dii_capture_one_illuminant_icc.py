"""Capture One용 X2D II **조명별 ICC 2장**을 발급한다(주광용/텅스텐용).
배포된 범용 `hasselblad_x2dii_chart.icc`는 건드리지 않고 새 파일로만 낸다.

**왜 조명별인가 - 실패한 시도부터**: 먼저
`tools/regenerate_x2dii_icc_v2_combined.py`로 범용 ICC를 combined 25장
D50 매트릭스로 교체하려 했는데, 발급 전 게이트(무채색 6패치의 CIELAB
a*b* 크로마)에서 막혔다: 기존(kmichels n=9) 9.9393 vs 신규(combined
n=25) 9.9871. 양성 대조로 지표 타당성을 확인했다 - 매트릭스를 **자기
피팅 데이터**의 평균 무채색에 적용하면 kmichels는 1.3279(정상)인데
combined는 9.8444다. 즉 지표는 멀쩡하고, combined 단일 매트릭스가
실제로 무채색 축에서 깨진다. 원인은 명확하다: 25장이 이봉(bimodal)
조명 혼합이라(주광 R/G≈0.33 n=9, 텅스텐 R/G≈0.65 n=7, kmichels
R/G≈0.41 n=9) 그 평균 R/G=0.4485는 **실재하지 않는 촬영 조건**이고,
단일 매트릭스는 그 허구의 평균에 맞춰진다. `.dcp`가 dual-illuminant로
간 이유가 정확히 이것이다.

**이 스크립트의 접근**: ICC v4 matrix/TRC는 슬롯이 하나뿐이고 PCS
백색점이 D50 고정이라 dual-illuminant를 한 파일에 담을 수 없다. 대신
**조명마다 파일을 하나씩** 낸다 - Capture One 사용자는 촬영 조명에 맞는
Base Characteristic을 고르면 되고, 이게 단일 파일 포맷에서 진짜 두
조명을 표현하는 유일한 방법이다.

**매트릭스 변환**: v2 리포트의 `color_matrix_1`/`color_matrix_2`는
각자의 캘리브레이션 조명(D65 / Standard Light A) **색도 기준**으로
fit된 native->XYZ(그 조명) 행벡터 매트릭스다. ICC는 native->XYZ(**D50**)를
요구하므로 XYZ를 그 조명에서 D50으로 Bradford 색순응시킨다 - v2 refit
스크립트의 `_predict_d50()`가 보간 후 하는 것과 같은 단계다.

**게이트**: 각 ICC를 자기 조명 그룹의 실측 무채색에 적용해 CIELAB a*b*
크로마를 재고, 현재 배포된 범용 ICC(kmichels 매트릭스)를 같은 무채색에
적용한 값보다 낮아야 통과시킨다. 즉 "그 조명에서 쓰면 지금 것보다
낫다"를 발급 조건으로 건다.

**한계**: 24패치 전체 실측 샘플은 커밋돼 있지 않아(무채색 6패치와 그룹
평균 무채색만) 전체 ΔE00 재비교는 RAW 없이 불가능하다. dpreview RAW는
현재 Cloudflare 차단으로 재확보 불가. 매트릭스 자체의 통계적 근거는
v2 리포트의 25장 held-out end-to-end(CI=[+5.5509,+9.2794], 25/0)다.

**사용자 승인**: 2026-09-04, "캡처원용도 다 만들어"(`/goal`). 기존
배포 `.icc`/`.dcp`/`.json`은 건드리지 않는다 - 새 파일 2개만 추가한다.

  ~/.hncs-hybrid-venv312/bin/python3 -m tools.build_x2dii_capture_one_illuminant_icc
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import colour
import numpy as np

from core.icc_export import write_icc_matrix_trc_profile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DPREVIEW_DIR = os.path.join(BASE, "datasets", "hasselblad", "contributed",
                            "dpreview-x2dii100c-studio-chart-2026-09")
V2_JSON = os.path.join(DPREVIEW_DIR,
                       "dual_illuminant_report_v2_illuminant_referenced.json")
KMICHELS_JSON = os.path.join(BASE, "datasets", "hasselblad", "contributed",
                             "kmichels-x2dii-2026-07",
                             "camera_native_matrix_report.json")
PROFILES_DIR = os.path.join(BASE, "hybrid_engine", "assets", "profiles")
OUT_REPORT = os.path.join(DPREVIEW_DIR, "capture_one_illuminant_icc_report.json")

XYZ_D50 = np.array([0.9642956764295677, 1.0, 0.8251046025104605])
D50_XY = (0.34567, 0.35850)


def _xyz_to_lab(xyz, white=XYZ_D50):
    r = np.asarray(xyz, dtype=np.float64) / white

    def f(t):
        return np.where(t > (6.0 / 29.0) ** 3,
                        np.cbrt(t), t / (3 * (6.0 / 29.0) ** 2) + 4.0 / 29.0)

    fx, fy, fz = f(r[0]), f(r[1]), f(r[2])
    return np.array([116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)])


def _neutral_chroma(matrix_native_to_xyz_d50, native_rgb):
    xyz = np.asarray(native_rgb, dtype=np.float64) @ matrix_native_to_xyz_d50
    if xyz[1] <= 0:
        return float("nan")
    lab = _xyz_to_lab(xyz / xyz[1] * XYZ_D50[1])
    return float(np.hypot(lab[1], lab[2]))


def _adapt_matrix_to_d50(chart_matrix, illuminant_xy):
    """native->XYZ(자기 조명) 행벡터 매트릭스를 native->XYZ(D50)로 바꾼다.
    행벡터 규약이므로 각 행(=기저 응답의 XYZ)을 Bradford로 순응시킨다."""
    src = colour.xy_to_XYZ(np.asarray(illuminant_xy, dtype=np.float64))
    dst = colour.xy_to_XYZ(np.asarray(D50_XY, dtype=np.float64))
    adapted = colour.chromatic_adaptation(
        np.asarray(chart_matrix, dtype=np.float64), src, dst,
        method="Von Kries", transform="Bradford")
    return np.asarray(adapted, dtype=np.float64)


def main():
    with open(V2_JSON, encoding="utf-8") as f:
        v2 = json.load(f)
    with open(KMICHELS_JSON, encoding="utf-8") as f:
        km = json.load(f)

    shipped_generic = np.array(km["chart_matrix_in_sample_irls_cyan_init"],
                               dtype=np.float64)

    variants = [
        {
            "key": "daylight",
            "filename": "hasselblad_x2dii_chart_daylight.icc",
            "description": "HNCS X2D II Chart Colorimetric (daylight/D65)",
            "chart_matrix": v2["color_matrix_1"],
            "illuminant_xy": v2["group1_daylight_like"]["reference_illuminant_xy"],
            "neutral": v2["group1_daylight_like"]["measured_native_neutral_g_normalized"],
            "n": v2["group1_daylight_like"]["n"],
        },
        {
            "key": "tungsten",
            "filename": "hasselblad_x2dii_chart_tungsten.icc",
            "description": "HNCS X2D II Chart Colorimetric (tungsten/StdA)",
            "chart_matrix": v2["color_matrix_2"],
            "illuminant_xy": v2["group2_tungsten_like"]["reference_illuminant_xy"],
            "neutral": v2["group2_tungsten_like"]["measured_native_neutral_g_normalized"],
            "n": v2["group2_tungsten_like"]["n"],
        },
    ]

    results = []
    print("조명별 ICC 게이트(자기 조명 무채색의 CIELAB a*b* 크로마, 낮을수록 좋음):")
    print(f"  {'조명':<10} {'n':>3} {'현행 범용ICC':>14} {'조명별 신규':>13}  판정")
    for v in variants:
        m_d50 = _adapt_matrix_to_d50(v["chart_matrix"], v["illuminant_xy"])
        c_new = _neutral_chroma(m_d50, v["neutral"])
        c_generic = _neutral_chroma(shipped_generic, v["neutral"])
        ok = c_new < c_generic
        print(f"  {v['key']:<10} {v['n']:>3} {c_generic:14.4f} {c_new:13.4f}  "
              f"{'통과' if ok else '실패'}")
        v["matrix_d50"] = m_d50
        v["chroma_new"] = c_new
        v["chroma_generic"] = c_generic
        v["pass"] = ok
        results.append(v)

    failed = [v["key"] for v in results if not v["pass"]]
    if failed:
        raise SystemExit(f"게이트 실패({', '.join(failed)}) - 발급 중단")
    print("게이트 통과 - 두 조명 모두 현행 범용 ICC보다 자기 조명에서 중립적\n")

    report_variants = []
    for v in results:
        out_path = os.path.join(PROFILES_DIR, v["filename"])
        write_icc_matrix_trc_profile(out_path, v["matrix_d50"],
                                     description=v["description"])
        xyz = np.asarray(v["neutral"], dtype=np.float64) @ v["matrix_d50"]
        print(f"발급: {out_path}")
        print(f"  무채색 native -> XYZ(정규화): "
              f"{[round(x, 4) for x in (xyz / xyz[1]).tolist()]}")
        report_variants.append({
            "file": f"hybrid_engine/assets/profiles/{v['filename']}",
            "description": v["description"],
            "illuminant": v["key"],
            "illuminant_xy": list(v["illuminant_xy"]),
            "n_images_fit": v["n"],
            "matrix_source": f"dual_illuminant_report_v2_illuminant_referenced.json"
                             f" -> {'color_matrix_1' if v['key'] == 'daylight' else 'color_matrix_2'}",
            "adaptation": "Von Kries / Bradford, 자기 조명 -> D50 (ICC PCS)",
            "matrix_native_to_xyz_d50": v["matrix_d50"].tolist(),
            "neutral_chroma_this_profile": v["chroma_new"],
            "neutral_chroma_shipped_generic_icc": v["chroma_generic"],
            "neutral_native_to_xyz_normalized": (xyz / xyz[1]).tolist(),
        })

    report = {
        "purpose": "Capture One Base Characteristics - 조명별 ICC 2장",
        "why": "ICC v4 matrix/TRC는 슬롯 하나 + D50 PCS 고정이라 dual-illuminant를 "
               "한 파일에 못 담는다. 단일 매트릭스로 두 조명을 합치면(combined 25장) "
               "무채색이 깨진다 - 자기 데이터에서도 크로마 9.8444(kmichels 매트릭스는 "
               "자기 데이터에서 1.3279). 조명별 파일 분리가 단일 파일 포맷에서 "
               "두 조명을 표현하는 유일한 방법.",
        "shipped_generic_icc_untouched":
            "hybrid_engine/assets/profiles/hasselblad_x2dii_chart.icc (kmichels n=9 기준, 무변경)",
        "rejected_alternative": {
            "what": "범용 ICC를 combined 25장 D50 매트릭스로 교체",
            "script": "tools/regenerate_x2dii_icc_v2_combined.py",
            "why_rejected": "발급 전 게이트에서 막힘 - 무채색 6패치 크로마 평균 "
                            "기존 9.9393 vs 신규 9.9871. 양성 대조로 지표 타당성 확인 "
                            "(각 매트릭스를 자기 피팅 데이터에 적용: kmichels 1.3279, "
                            "combined 9.8444).",
        },
        "inherited_validation": v2["full25_held_out_end_to_end"],
        "limitation": "24패치 전체 실측 샘플이 커밋돼 있지 않아(무채색 6패치 + 그룹 "
                      "평균 무채색만) 전체 ΔE00 재비교는 RAW 없이 불가능하다. "
                      "dpreview RAW는 현재 Cloudflare 차단으로 재확보 불가. "
                      "이 게이트는 무채색 축에 한정된 검증이다.",
        "user_approval": "2026-09-04 '캡처원용도 다 만들어'",
        "variants": report_variants,
    }
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n리포트: {OUT_REPORT}")


if __name__ == "__main__":
    main()
