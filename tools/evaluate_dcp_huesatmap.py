"""
DCP HueSatMap(hue-only 축소판)이 배포된 chart 매트릭스
(`tools/refit_dcp_irls_cyan_init.py`) 위에서 LOO ΔE00을 더 낮추는지
확인 - `tools/dcp_export_huesatmap_experimental.py`(core/dcp_export.py
격리 사본, Never-list 안 건드림)의 태그 지원을 실제로 써먹는 실험.

patch 17(cyan)에서 a*(녹-적) 축으로 평균 +11.98 치우침(표준편차 0.496)이
남는다는 진단(`hybrid_engine/EVALUATION.md` 해당 절) - 3x3 선형 매트릭스로
못 잡는 방향이니, hue만 회전시키는(채도/명도는 그대로 두는) 비선형 보정을
얹으면 더 줄어드는지가 질문이다.

**중요한 단순화**: 실제 DNG HueSatMap은 렌더링 파이프라인의 HSV(카메라
작업 공간 RGB 기준)에서 적용된다. 이 스크립트는 그 정확한 색공간 대신
이미 이 프로젝트의 ΔE00 계산에 쓰는 CIELAB(a*, b*) 평면에서 원점 기준
회전으로 hue shift를 근사한다 - "얹으면 신호가 있는지"를 빨리 확인하려는
것이지, 실제 Lightroom에 넣을 수 있는 정확한 수치를 내는 게 아니다.
신호가 확인되면 그 다음 단계로 진짜 DNG 색공간 매핑을 구현할지 결정한다.

방법: 각 patch의 (기존 매트릭스로 예측한 Lab) vs (참조 Lab)에서 hue 오차
(도 단위, wrap)를 구하고, hue division마다 원형 가우시안 커널로 가중평균한
"hue shift 테이블"을 학습 8장에서 만들어 held-out 1장에 적용(a*,b* 벡터를
원점 기준 회전, L/채도는 불변) - 9장 leave-one-image-out.

  python3 -m tools.evaluate_dcp_huesatmap
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import colour
import numpy as np

from hybrid_engine.core import chart_baseline, raw_baseline
from hybrid_engine.utils.io import decode_raw_native
from tools.evaluate_dcp_irls_weighted import _irls_fit

SET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "datasets", "hasselblad", "contributed", "kmichels-x2dii-2026-07")
REPORT_JSON = os.path.join(SET_DIR, "camera_native_matrix_report.json")

D50 = colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]["D50"]
N_DIVISIONS = 8  # DNG HueSatMap 관례 - 45도씩
KERNEL_SIGMA_DEG = 30.0  # division 간격(45도)보다 좁은 원형 가우시안


def _wrap_deg(x):
    return (x + 180.0) % 360.0 - 180.0


def _hue_deg(a, b):
    return np.degrees(np.arctan2(b, a)) % 360.0


def _fit_hue_table(pred_lab_list, ref_lab):
    """학습 이미지들(각각 (24,3) Lab)에서 division별 hue shift(도) 테이블을
    원형 가우시안 커널 가중평균으로 학습. (N_DIVISIONS,) 반환."""
    all_pred_hue, all_shift = [], []
    for pred_lab in pred_lab_list:
        for i in range(24):
            a_p, b_p = pred_lab[i, 1], pred_lab[i, 2]
            a_r, b_r = ref_lab[i, 1], ref_lab[i, 2]
            chroma_r = np.hypot(a_r, b_r)
            if chroma_r < 5.0:  # 무채색 패치는 hue 정의가 불안정해서 제외
                continue
            pred_hue = _hue_deg(a_p, b_p)
            ref_hue = _hue_deg(a_r, b_r)
            all_pred_hue.append(pred_hue)
            all_shift.append(_wrap_deg(ref_hue - pred_hue))
    all_pred_hue = np.array(all_pred_hue)
    all_shift = np.array(all_shift)

    centers = np.arange(N_DIVISIONS) * (360.0 / N_DIVISIONS)
    table = np.zeros(N_DIVISIONS)
    for i, c in enumerate(centers):
        d = np.abs(_wrap_deg(all_pred_hue - c))
        w = np.exp(-0.5 * (d / KERNEL_SIGMA_DEG) ** 2)
        if w.sum() < 1e-6:
            table[i] = 0.0
        else:
            table[i] = np.average(all_shift, weights=w)
    return table


def _apply_hue_table(pred_lab, table):
    """(24,3) Lab에 hue 테이블을 적용(선형 보간, 원형) - L/채도는 불변,
    a*,b*만 원점 기준 회전."""
    centers = np.arange(N_DIVISIONS) * (360.0 / N_DIVISIONS)
    out = pred_lab.copy()
    for i in range(24):
        L, a, b = pred_lab[i]
        chroma = np.hypot(a, b)
        if chroma < 1e-6:
            continue
        hue = _hue_deg(a, b)
        # 인접 두 division 사이 선형 보간(원형)
        idx = hue / (360.0 / N_DIVISIONS)
        i0 = int(np.floor(idx)) % N_DIVISIONS
        i1 = (i0 + 1) % N_DIVISIONS
        frac = idx - np.floor(idx)
        shift0, shift1 = table[i0], table[i1]
        # 경계에서 wrap 방향 튀는 거 방지
        if shift1 - shift0 > 180:
            shift1 -= 360
        elif shift1 - shift0 < -180:
            shift1 += 360
        shift = shift0 + frac * (shift1 - shift0)
        new_hue = np.radians(hue + shift)
        out[i, 1] = chroma * np.cos(new_hue)
        out[i, 2] = chroma * np.sin(new_hue)
    return out


def _lab(xyz):
    return colour.XYZ_to_Lab(xyz, illuminant=D50)


def _delta_e00_lab(lab_a, lab_b):
    return np.asarray(colour.delta_E(lab_a, lab_b, method="CIE 2000"))


def main():
    reference = chart_baseline.reference_patches_xyz_d50()
    ref_lab = _lab(reference)

    raw_paths = sorted(glob.glob(os.path.join(SET_DIR, "raw", "*.3FR")))
    per_image = {}
    for raw_path in raw_paths:
        name = os.path.basename(raw_path)
        print(f"  디코드+검출 중: {name}", flush=True)
        native = decode_raw_native(raw_path)
        samples = chart_baseline.detect_and_sample(native)
        if samples is None:
            continue
        per_image[name] = samples
    names = sorted(per_image.keys())
    print(f"\n검출 성공 {len(names)}장: {names}")

    # cyan 초기가중치 2.0 - tools/refit_dcp_irls_cyan_init.py와 동일 시작점.
    init_weights = np.array([1.0 if i in range(18, 24) else 4.0 for i in range(24)])
    init_weights[17] = 2.0

    no_map_de = {}
    with_map_de = {}
    for held_out in names:
        train_names = [nm for nm in names if nm != held_out]
        # 매트릭스도 held_out 없이 새로 피팅 - 이전 버전은 전체 9장으로
        # 피팅한 매트릭스를 재사용해서 held_out이 학습에 새고 있었다.
        train_sources = [per_image[nm] for nm in train_names]
        train_targets = [reference for _ in train_names]
        _, fold_matrix = _irls_fit(train_sources, train_targets, init_weights)

        pred_lab_by_train_image = {
            nm: _lab(raw_baseline.apply_color_matrix(per_image[nm], fold_matrix))
            for nm in train_names
        }
        pred_lab_held = _lab(raw_baseline.apply_color_matrix(per_image[held_out], fold_matrix))

        no_map_de[held_out] = float(np.mean(_delta_e00_lab(pred_lab_held, ref_lab)))

        table = _fit_hue_table(list(pred_lab_by_train_image.values()), ref_lab)
        corrected_lab = _apply_hue_table(pred_lab_held, table)
        with_map_de[held_out] = float(np.mean(_delta_e00_lab(corrected_lab, ref_lab)))

    print(f"\nhue map 없음(챠트 매트릭스만, 진짜 LOO) LOO ΔE00 = {np.mean(list(no_map_de.values())):.4f}")
    print(f"hue map 적용(Lab 근사, {N_DIVISIONS}division, 진짜 LOO) LOO ΔE00 = {np.mean(list(with_map_de.values())):.4f}")
    print("\n장별 비교:")
    for nm in names:
        print(f"  {nm}: 없음={no_map_de[nm]:.4f}  적용={with_map_de[nm]:.4f}  "
              f"차이={with_map_de[nm] - no_map_de[nm]:+.4f}")

    # 전체 표본(홀드아웃 없이)으로 학습한 테이블 - 참고용, 배포하려면 이 값을 씀
    _, full_matrix = _irls_fit(list(per_image.values()), [reference] * len(names), init_weights)
    full_pred_lab = [_lab(raw_baseline.apply_color_matrix(per_image[nm], full_matrix)) for nm in names]
    full_table = _fit_hue_table(full_pred_lab, ref_lab)
    print(f"\n전체 표본 학습 hue shift 테이블(도, division 중심 0,45,...315):")
    print(f"  {np.round(full_table, 2).tolist()}")


if __name__ == "__main__":
    main()
