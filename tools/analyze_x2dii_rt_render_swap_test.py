"""X2D II 100C v2 DCP의 RawTherapee illuminant1 스냅 근본원인(태그 역순 +
RT 매트릭스 경로의 비스왑 mix 공식)을 **실제 rawtherapee-cli 렌더로 실증**
하는 합성 테스트 - `tools/analyze_x2dii_rt_illuminant_order_snap.py`의
수식 재도출과 짝을 이루는 실기 검증.

**설계**: dpreview group2 raw는 Cloudflare에 막혀 재다운로드가 안 되므로
(task-brief 참고), 로컬에 있는 kmichels 3FR에 **pp3로 WB를 2856K(StdA)
강제**해서 텅스텐 촬영 상황을 재현한다 - RT dcp.cc 1753행 주석대로 RT의
보간 판단에 들어가는 neutral은 파일의 AsShotNeutral이 아니라 **RT 자체
WB 설정**에서 오므로, WB 강제는 실제 텅스텐 촬영과 같은 보간 입력을
만든다. 그 위에서 2x3 매트릭스 실험:

  DCP 2종: (S) 배포본 그대로(illuminant1=D65, 2=StdA - 역순),
           (W) illuminant/매트릭스를 함께 스왑한 실험 사본
           (Adobe 관례 순서: 1=StdA, 2=D65. 새 파일로만 생성 -
           배포본은 읽기만, Never-list 준수)
  DCPIlluminant 3종: 0(자동보간)/1(슬롯1 강제)/2(슬롯2 강제)

**예측(태그 역순이 원인일 때)**: WB=2856K인데도
  - S: render(0) == render(1) (D65 매트릭스 - 잘못된 스냅, 기존 관찰 재현)
  - W: render(0) ≈ render(1) (슬롯1=StdA 매트릭스 - 올바른 방향,
       mix≈0.985라 완전 동일이 아니라 근사)
  - render(S,0) vs render(W,0): 큰 차이(같은 이미지/설정에서 태그 순서만
    바꿨는데 선택 매트릭스가 D65<->StdA로 뒤집힘)

**사용자 승인**: 조사 지시 자체가 사용자 위임(task-brief
`.superpowers/sdd/x2dii-rt-asshotneutral-investigation/task-brief.md`).
배포 `.dcp`/`core/*` 수정 없음 - 스왑 DCP는 scratch 하위 새 파일.

실행: ~/.hncs-hybrid-venv312/bin/python3 -m tools.analyze_x2dii_rt_render_swap_test
(rawtherapee-cli 5.13 필요, 렌더 6장이라 몇 분 소요)
"""
import json
import os
import subprocess
import tempfile

import numpy as np
import imageio.v2 as imageio

from core.dcp_export import read_dcp, write_dcp

DCP_SHIPPED = "hybrid_engine/assets/profiles/hasselblad_x2dii_chart.dcp"
RAW = "datasets/hasselblad/contributed/kmichels-x2dii-2026-07/raw/B_31325.3FR"
OUT_PATH = ("datasets/hasselblad/contributed/"
            "dpreview-x2dii100c-studio-chart-2026-09/"
            "rt_render_swap_test_report.json")

TAG_CM1, TAG_CM2 = 0xC621, 0xC622
TAG_ILL1, TAG_ILL2 = 0xC65A, 0xC65B

PP3_TEMPLATE = """[Version]
AppVersion=5.13
Version=350

[White Balance]
Enabled=true
Setting=Custom
Temperature=2856
Green=1

[Color Management]
InputProfile=file:{dcp_path}
ToneCurve=false
ApplyLookTable=false
ApplyBaselineExposureOffset=false
ApplyHueSatMap=false
DCPIlluminant={illuminant}
"""


def render(raw, pp3_path, out_tif):
    # rawtherapee-cli가 상대경로 입력을 "doesn't exist"로 거부해서 절대경로 필수.
    cmd = ["rawtherapee-cli", "-Y", "-o", out_tif, "-d", "-p", pp3_path,
           "-t", "-c", os.path.abspath(raw)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if not os.path.exists(out_tif):
        raise RuntimeError(f"렌더 실패: {' '.join(cmd)}\n{r.stdout}\n{r.stderr}")


def mean_abs_diff(a_path, b_path):
    a = imageio.imread(a_path).astype(np.float64)
    b = imageio.imread(b_path).astype(np.float64)
    return float(np.mean(np.abs(a - b)))


def main():
    tags = read_dcp(DCP_SHIPPED)
    assert int(tags[TAG_ILL1]) == 21 and int(tags[TAG_ILL2]) == 17, \
        "배포본 태그 순서가 전제(1=D65,2=StdA)와 다름 - 스크립트 재검토 필요"

    work = tempfile.mkdtemp(prefix="rt_swap_test_")
    dcp_swapped = os.path.join(work, "x2dii_swapped_illuminant_order.dcp")
    write_dcp(dcp_swapped,
              camera_model="Hasselblad X2D II 100C",
              profile_name="X2DII chart swapped-order EXPERIMENTAL",
              color_matrix_1=np.asarray(tags[TAG_CM2]).reshape(3, 3),
              calibration_illuminant_1=17,
              color_matrix_2=np.asarray(tags[TAG_CM1]).reshape(3, 3),
              calibration_illuminant_2=21)
    print(f"스왑 DCP(실험용 새 파일): {dcp_swapped}")

    renders = {}
    for dcp_key, dcp_path in (("shipped", os.path.abspath(DCP_SHIPPED)),
                              ("swapped", dcp_swapped)):
        for ill in (0, 1, 2):
            pp3 = os.path.join(work, f"{dcp_key}_ill{ill}.pp3")
            with open(pp3, "w") as f:
                f.write(PP3_TEMPLATE.format(dcp_path=dcp_path,
                                            illuminant=ill))
            out_tif = os.path.join(work, f"{dcp_key}_ill{ill}.tif")
            print(f"렌더 중: {dcp_key} DCPIlluminant={ill} ...", flush=True)
            render(RAW, pp3, out_tif)
            renders[(dcp_key, ill)] = out_tif

    pairs = [
        ("shipped", 0, "shipped", 1, "S: 자동 vs 슬롯1(D65) - 0이면 기존 관찰 재현"),
        ("shipped", 0, "shipped", 2, "S: 자동 vs 슬롯2(StdA) - 크면 스냅 방향이 D65라는 뜻"),
        ("swapped", 0, "swapped", 1, "W: 자동 vs 슬롯1(StdA) - 작으면 올바른 방향으로 감"),
        ("swapped", 0, "swapped", 2, "W: 자동 vs 슬롯2(D65) - 커야 정상"),
        ("shipped", 0, "swapped", 0, "같은 설정, 태그 순서만 스왑 - 커야 근본원인 확정"),
        ("shipped", 1, "swapped", 2, "동일 매트릭스(D65) 강제 - 0이어야 함(무결성 체크)"),
        ("shipped", 2, "swapped", 1, "동일 매트릭스(StdA) 강제 - 0이어야 함(무결성 체크)"),
    ]
    out = {"raw": RAW, "wb_forced": "Custom 2856K (StdA성 촬영 재현)",
           "diffs": []}
    print()
    for ka, ia, kb, ib, label in pairs:
        d = mean_abs_diff(renders[(ka, ia)], renders[(kb, ib)])
        out["diffs"].append({"a": f"{ka}:ill{ia}", "b": f"{kb}:ill{ib}",
                             "mean_abs_diff_16bit": round(d, 4),
                             "label": label})
        print(f"  {ka}:ill{ia} vs {kb}:ill{ib}  mean|Δ|={d:10.4f}  ({label})")

    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(f"\n리포트 저장: {OUT_PATH}\n작업 파일: {work} (임시, 커밋 안 함)")


if __name__ == "__main__":
    main()
