"""Capture One용 X2D II ICC를 **combined 25장 D50 매트릭스**로 재발급한다
(v2). 기존 `tools/regenerate_x2dii_icc.py`(v1)는 kmichels 단독 9장
매트릭스를 썼다.

**왜 바꾸나**: 배포 `.dcp`는 2026-09-03에 combined 25장으로, 09-04에
dual-illuminant v2/v3로 두 번 재보정됐는데 `.icc`는 2026-09-02
(`3bff252`) 이후 그대로였다 - 즉 **Capture One 사용자만 구버전
매트릭스**를 쓰고 있었다. 그 구버전(kmichels 단독, n=9)은 이 프로젝트가
이미 단일조명 과적합으로 판정한 것이다: kmichels LOO CV는 2.7245로
좋아 보이지만 "10장을 94초 만에 찍은 같은 조명 번스트"라 사실상 같은
이미지끼리 검증한 것이고, 실제 다른 조명(dpreview)에 out-of-sample로
적용하면 19.155 ΔE00였다(`hybrid_engine/EVALUATION.md`
"dual-illuminant로 재교체" 절). combined 25장은 같은 종류의 다조명
데이터에 5-fold CV 12.6865, 부트스트랩 95% CI=[+16.6826,+20.8136],
승/패=25/0이다(`combined_chart_matrix_report.json`의
`combined_weighted_loo_cv`).

**왜 dual-illuminant(v2/v3) 매트릭스가 아니라 combined인가**: ICC v4
matrix/TRC에는 dual-illuminant 개념 자체가 없고(슬롯 하나뿐), PCS
백색점이 **D50 고정**이다(`core/icc_export.py` 모듈 독스트링). v2/v3의
두 매트릭스는 각자의 캘리브레이션 조명(D65 / Standard Light A) 색도
기준으로 fit된 illuminant-referenced 매트릭스라 D50 PCS에 그대로 넣으면
안 된다. combined 매트릭스는 `calibration_illuminant`가 D50(enum 23)인
D50 기준 fit이라 ICC PCS와 규약이 정확히 맞는다 - 단일 매트릭스
포맷에서 고를 수 있는 최선이다.

**발급 전 게이트**: 무채색 6패치 실측 네이티브값(리포트에 커밋돼 있음)을
구/신 매트릭스에 각각 통과시켜 D50 중립축에서 얼마나 벗어나는지(CIELAB
a*b* 크로마) 비교한다. 신규가 더 나쁘면 발급을 중단한다. 24패치 전체
실측은 커밋돼 있지 않아(무채색 6패치만) 전체 ΔE00 재비교는 RAW 없이
불가능하다 - 그 한계는 리포트에 명시한다. 매트릭스 자체의 통계적 근거는
위 combined CI로 이미 확립돼 있다.

**사용자 승인**: 2026-09-04, "캡처원용도 다 만들어"(`/goal`). 기존
배포 `.icc`를 덮어쓴다 - `.dcp`/`.json`은 건드리지 않는다.

  ~/.hncs-hybrid-venv312/bin/python3 -m tools.regenerate_x2dii_icc_v2_combined
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from core.icc_export import write_icc_matrix_trc_profile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMBINED_JSON = os.path.join(
    BASE, "datasets", "hasselblad", "contributed",
    "dpreview-x2dii100c-studio-chart-2026-09", "combined_chart_matrix_report.json")
KMICHELS_JSON = os.path.join(
    BASE, "datasets", "hasselblad", "contributed",
    "kmichels-x2dii-2026-07", "camera_native_matrix_report.json")
OUT_ICC = os.path.join(BASE, "hybrid_engine", "assets", "profiles",
                       "hasselblad_x2dii_chart.icc")
OUT_REPORT = os.path.join(
    BASE, "datasets", "hasselblad", "contributed",
    "dpreview-x2dii100c-studio-chart-2026-09", "icc_v2_combined_report.json")

DESCRIPTION = "HNCS X2D II Chart Colorimetric (combined 25)"
XYZ_D50 = np.array([0.9642956764295677, 1.0, 0.8251046025104605])


def _xyz_to_lab(xyz, white=XYZ_D50):
    r = np.asarray(xyz, dtype=np.float64) / white

    def f(t):
        return np.where(t > (6.0 / 29.0) ** 3,
                        np.cbrt(t), t / (3 * (6.0 / 29.0) ** 2) + 4.0 / 29.0)

    fx, fy, fz = f(r[0]), f(r[1]), f(r[2])
    return np.array([116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)])


def _neutral_chroma(matrix, native_rgb):
    """네이티브 무채색을 매트릭스로 XYZ(D50)에 보내고 CIELAB a*b* 크로마를
    잰다. 무채색이 진짜 무채색으로 가면 0에 가깝다(색캐스트 없음)."""
    xyz = np.asarray(native_rgb, dtype=np.float64) @ matrix
    if xyz[1] <= 0:
        return float("nan")
    lab = _xyz_to_lab(xyz / xyz[1] * XYZ_D50[1])
    return float(np.hypot(lab[1], lab[2]))


def main():
    with open(COMBINED_JSON, encoding="utf-8") as f:
        combined = json.load(f)
    with open(KMICHELS_JSON, encoding="utf-8") as f:
        kmichels = json.load(f)

    new_matrix = np.array(combined["chart_matrix_in_sample"], dtype=np.float64)
    old_matrix = np.array(kmichels["chart_matrix_in_sample_irls_cyan_init"],
                          dtype=np.float64)

    assert combined["calibration_illuminant"]["chosen_enum"] == 23, \
        "combined 매트릭스가 D50 기준이 아님 - ICC PCS와 안 맞으므로 중단"

    per_patch = combined["measured_native_neutral_per_patch"]
    print("무채색 6패치 중립성(CIELAB a*b* 크로마, 낮을수록 좋음):")
    print(f"  {'패치':<24} {'구(kmichels n=9)':>18} {'신(combined n=25)':>19}")
    rows = []
    for name, native in per_patch.items():
        c_old = _neutral_chroma(old_matrix, native)
        c_new = _neutral_chroma(new_matrix, native)
        rows.append({"patch": name, "chroma_old": c_old, "chroma_new": c_new})
        print(f"  {name:<24} {c_old:18.4f} {c_new:19.4f}")
    mean_old = float(np.mean([r["chroma_old"] for r in rows]))
    mean_new = float(np.mean([r["chroma_new"] for r in rows]))
    print(f"  {'평균':<24} {mean_old:18.4f} {mean_new:19.4f}")

    if not mean_new < mean_old:
        raise SystemExit(
            f"게이트 실패: 신규 매트릭스의 무채색 크로마 평균({mean_new:.4f})이 "
            f"기존({mean_old:.4f})보다 낫지 않다 - 발급 중단")
    print(f"게이트 통과: 무채색 크로마 평균 {mean_old:.4f} -> {mean_new:.4f}\n")

    write_icc_matrix_trc_profile(OUT_ICC, new_matrix, description=DESCRIPTION)
    print(f"발급: {OUT_ICC}")

    neutral = np.array(combined["measured_native_neutral_g_normalized"],
                       dtype=np.float64)
    xyz = neutral @ new_matrix
    xyz_norm = (xyz / xyz[1]).tolist()
    print(f"무채색 native -> XYZ(정규화): {[round(v, 4) for v in xyz_norm]}")
    print(f"D50 기준:                     {[round(v, 4) for v in XYZ_D50]}")

    report = {
        "artifact": "hybrid_engine/assets/profiles/hasselblad_x2dii_chart.icc",
        "purpose": "Capture One Base Characteristics (ICC v4 matrix/TRC)",
        "supersedes": {
            "source": "kmichels-x2dii-2026-07/camera_native_matrix_report.json"
                      " -> chart_matrix_in_sample_irls_cyan_init (n=9)",
            "why": "단일조명 번스트 과적합 - dpreview 다조명에 out-of-sample "
                   "19.155 ΔE00(EVALUATION.md 'dual-illuminant로 재교체' 절)",
            "issued_by": "tools/regenerate_x2dii_icc.py (v1, 2026-09-02)",
        },
        "matrix_source": "dpreview-x2dii100c-studio-chart-2026-09/"
                         "combined_chart_matrix_report.json -> chart_matrix_in_sample",
        "n_images": combined["n_images_combined"],
        "calibration_illuminant": combined["calibration_illuminant"],
        "inherited_validation": combined["combined_weighted_loo_cv"],
        "why_not_dual_illuminant": "ICC v4 matrix/TRC는 슬롯이 하나뿐이고 PCS "
                                   "백색점이 D50 고정이라, D65/StdA 기준으로 fit된 "
                                   "v2/v3 dual-illuminant 매트릭스를 그대로 넣을 수 "
                                   "없다. combined은 D50 기준 fit이라 규약이 맞는다.",
        "neutral_axis_gate": {
            "metric": "CIELAB a*b* chroma of the 6 measured neutral patches "
                      "(lower = less color cast)",
            "per_patch": rows,
            "mean_old": mean_old, "mean_new": mean_new,
        },
        "neutral_native_to_xyz_normalized": xyz_norm,
        "xyz_d50_reference": XYZ_D50.tolist(),
        "limitation": "24패치 전체 실측 샘플은 커밋돼 있지 않아(무채색 6패치만) "
                      "구/신 매트릭스의 전체 ΔE00 재비교는 RAW 없이 불가능하다. "
                      "dpreview RAW는 현재 Cloudflare 차단으로 재확보 불가. "
                      "매트릭스 자체의 통계적 근거는 combined 리포트의 25장 "
                      "5-fold CV + 부트스트랩 CI로 이미 확립돼 있다.",
        "user_approval": "2026-09-04 '캡처원용도 다 만들어'",
    }
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"리포트: {OUT_REPORT}")


if __name__ == "__main__":
    main()
