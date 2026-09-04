"""배포된 v3 DCP(Adobe illuminant order)가 RawTherapee에서 실제로
dual-illuminant 보간을 하는지 실렌더로 확인한다 -
`tools/reissue_x2dii_dcp_v3_adobe_illuminant_order.py` 발급 직후의 수용 검사.

**방법**: kmichels 3FR에 pp3로 WB를 텅스텐(2856K)/데이라이트(6504K)로
각각 강제하고, 각 WB에서 `DCPIlluminant=0`(자동보간) 렌더가 슬롯1(StdA)
강제/슬롯2(D65) 강제 중 어느 쪽에 가까운지 mean abs diff로 잰다. RT의
보간 입력 neutral은 파일 태그가 아니라 RT 자체 WB에서 오므로
(`rtengine/dcp.cc` 1753-1786행) WB 강제가 촬영 조명 재현으로 유효하다.

**기대(v3가 고쳐졌다면)**: WB 2856K에서 자동렌더는 슬롯1(StdA)에
가깝고, WB 6504K에서는 슬롯2(D65)에 가깝다 - 즉 WB에 따라 선택이
바뀐다. v2(태그 역순)에서는 두 WB 모두 D65로 스냅됐다
(`hybrid_engine/EVALUATION.md` 2026-09-04 근본원인 절,
`rt_render_swap_test_report.json`).

**사용자 승인**: v3 발급 자체가 사용자 승인("새로 발급 ㄱㄱ",
2026-09-04). 이 스크립트는 읽기 전용 검증 - `.dcp`를 쓰지 않는다.

  ~/.hncs-hybrid-venv312/bin/python3 -m tools.verify_x2dii_dcp_v3_rawtherapee
(rawtherapee-cli 5.13 필요, 렌더 6장 약 3분)
"""
import json
import os
import subprocess
import tempfile

import numpy as np
import imageio.v2 as imageio

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DCP = os.path.join(BASE, "hybrid_engine", "assets", "profiles",
                   "hasselblad_x2dii_chart.dcp")
RAW = os.path.join(BASE, "datasets", "hasselblad", "contributed",
                   "kmichels-x2dii-2026-07", "raw", "B_31325.3FR")
OUT_PATH = os.path.join(BASE, "datasets", "hasselblad", "contributed",
                        "dpreview-x2dii100c-studio-chart-2026-09",
                        "v3_rawtherapee_acceptance_report.json")

PP3_TEMPLATE = """[Version]
AppVersion=5.13
Version=350

[White Balance]
Enabled=true
Setting=Custom
Temperature={temp}
Green=1

[Color Management]
InputProfile=file:{dcp_path}
ToneCurve=false
ApplyLookTable=false
ApplyBaselineExposureOffset=false
ApplyHueSatMap=false
DCPIlluminant={illuminant}
"""


def render(pp3_path, out_tif):
    cmd = ["rawtherapee-cli", "-Y", "-o", out_tif, "-d", "-p", pp3_path,
           "-t", "-c", os.path.abspath(RAW)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if not os.path.exists(out_tif):
        raise RuntimeError(f"렌더 실패: {' '.join(cmd)}\n{r.stdout}\n{r.stderr}")


def mean_abs_diff(a_path, b_path):
    a = imageio.imread(a_path).astype(np.float64)
    b = imageio.imread(b_path).astype(np.float64)
    return float(np.mean(np.abs(a - b)))


def main():
    work = tempfile.mkdtemp(prefix="rt_v3_verify_")
    out = {"dcp": DCP, "raw": RAW, "cases": []}
    all_ok = True

    for label, temp, expect_slot in (("tungsten", 2856, 1),
                                     ("daylight", 6504, 2)):
        renders = {}
        for ill in (0, 1, 2):
            pp3 = os.path.join(work, f"{label}_ill{ill}.pp3")
            with open(pp3, "w") as f:
                f.write(PP3_TEMPLATE.format(temp=temp, dcp_path=DCP,
                                            illuminant=ill))
            tif = os.path.join(work, f"{label}_ill{ill}.tif")
            print(f"렌더 중: WB={temp}K DCPIlluminant={ill} ...", flush=True)
            render(pp3, tif)
            renders[ill] = tif

        d1 = mean_abs_diff(renders[0], renders[1])  # vs 슬롯1(StdA)
        d2 = mean_abs_diff(renders[0], renders[2])  # vs 슬롯2(D65)
        chosen = 1 if d1 < d2 else 2
        ok = chosen == expect_slot
        all_ok = all_ok and ok
        out["cases"].append({
            "wb_label": label, "wb_temp_k": temp,
            "auto_vs_slot1_stda": round(d1, 4),
            "auto_vs_slot2_d65": round(d2, 4),
            "closer_to_slot": chosen, "expected_slot": expect_slot,
            "pass": ok,
        })
        print(f"  WB={temp}K: 자동 vs 슬롯1(StdA)={d1:10.4f}, "
              f"vs 슬롯2(D65)={d2:10.4f} -> 슬롯{chosen} "
              f"(기대 슬롯{expect_slot}) {'OK' if ok else 'FAIL'}\n")

    out["all_pass"] = all_ok
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"판정: {'통과 - WB에 따라 매트릭스가 바뀐다(진짜 dual-illuminant)' if all_ok else 'FAIL'}")
    print(f"리포트 저장: {OUT_PATH}")


if __name__ == "__main__":
    main()
