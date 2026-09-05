"""[research] 사용자가 별도 Codex 조사로 받아온 "잔차 L-채널 보정" 결과를
이 프로젝트 코드/데이터로 직접 재현·검증한다(hybrid_engine/EVALUATION.md
"공식 13쌍 잔차 L-채널 보정 시도" 절 참고 - 그 절은 재현 없이 그대로
옮겨적은 것이었음, 이 스크립트가 실제 검증).

공식 13쌍(raw_calib_cache)에 현재 배포된 hasselblad.json을 그대로 적용한
페어별 Lab을 얻은 뒤:
1. ΔE00을 L/C/H 성분(intermediate_attributes_CIE2000의 S_L/S_C/S_H로
   정규화한 (ΔL'/SL)^2 등)으로 분해 - R_T 교차항은 부호가 섞여 있어
   성분 비중 계산에서는 제외(L/C/H 세 항만으로 100% 정규화)
2. 페어별 L* 오프셋 최소자승 최적값(= mean(target_L) - mean(pred_L),
   오라클 - 그 페어의 정답을 알아야 계산됨)으로 L*를 이동시켜 ΔE00 재계산
3. 페어별 L* affine(1차 회귀 pred_L ~ target_L, 오라클) 정렬
4. 전역 median 매핑 - 13쌍 각각의 오라클 오프셋의 median 하나를 전체
   페어에 똑같이 적용(배포 가능 - 타깃 안 봄)
5. LOO 고정 오프셋 - 각 페어는 "나머지 12쌍"의 오라클 오프셋 median을
   적용받음(배포 가능, 과적합 방지 설계)

  ~/.hncs-hybrid-venv312/bin/python3 -m hybrid_engine.verify_l_channel_residual
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from hybrid_engine.calibrate_profile import _find_pairs, _resize_max_dim, CALIB_MAX_DIM
from hybrid_engine.core import color_matrix
from hybrid_engine.pipeline.engine import HybridCameraEngine
from hybrid_engine.utils.evaluate import (
    _cie2000_intermediate_terms,
    _linear_rgb_to_lab,
    delta_E_CIE2000_weighted,
)
from hybrid_engine.utils.io import decode_raw, load_image_linear


def _de00_from_lab(lab_a, lab_b):
    return np.mean(delta_E_CIE2000_weighted(lab_a.reshape(-1, 3), lab_b.reshape(-1, 3)))


def main():
    profile_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "assets", "profiles", "hasselblad.json")
    with open(profile_path, encoding="utf-8") as f:
        profile = json.load(f)
    profile.pop("_comment", None)
    engine = HybridCameraEngine(profile=profile)

    pairs = _find_pairs()
    print(f"공식 페어 {len(pairs)}쌍", flush=True)

    lab_preds, lab_targets = [], []
    for raw_path, target_path in pairs:
        print(f"  로드 중: {os.path.basename(raw_path)}", flush=True)
        linear = decode_raw(raw_path)
        linear_small = _resize_max_dim(linear, CALIB_MAX_DIM)
        camera_wb = color_matrix.extract_camera_metadata(raw_path)["camera_whitebalance"]
        target_small = load_image_linear(target_path, resize_to=linear_small.shape[:2])
        result = engine.process(linear_small, camera_whitebalance=camera_wb)
        lab_preds.append(_linear_rgb_to_lab(result).reshape(-1, 3))
        lab_targets.append(_linear_rgb_to_lab(target_small).reshape(-1, 3))

    n = len(pairs)
    baseline_de = np.array([_de00_from_lab(lab_preds[i], lab_targets[i]) for i in range(n)])
    print(f"\n기준 ΔE00(공식 13쌍, 현재 hasselblad.json) = {baseline_de.mean():.3f} "
          f"(EVALUATION.md에 기록된 8.558과 비교)")
    print("\n페어별 ΔE00 + Software EXIF(편집 흔적 확인):")
    import subprocess
    for i, (raw_path, target_path) in enumerate(pairs):
        sw = subprocess.run(["exiftool", "-Software", "-s", "-s", "-s", target_path],
                             capture_output=True, text=True, timeout=15).stdout.strip()
        edited = "EDITED" if sw else "clean"
        print(f"  [{edited:7s}] {os.path.basename(raw_path):30s} ΔE00={baseline_de[i]:.3f}  "
              f"Software={sw or '(없음)'}")

    # 1) L/C/H 성분 분해 (R_T 교차항 제외, 세 항만으로 정규화)
    l_frac, c_frac, h_frac = [], [], []
    for i in range(n):
        S_L, S_C, S_H, dLp, dCp, dHp, _R_T = _cie2000_intermediate_terms(
            lab_preds[i], lab_targets[i])
        l_sq = np.mean((dLp / S_L) ** 2)
        c_sq = np.mean((dCp / S_C) ** 2)
        h_sq = np.mean((dHp / S_H) ** 2)
        total = l_sq + c_sq + h_sq
        l_frac.append(l_sq / total)
        c_frac.append(c_sq / total)
        h_frac.append(h_sq / total)
    print(f"\nΔE00^2 성분 분해(R_T 제외, 페어 평균): "
          f"L {np.mean(l_frac)*100:.0f}% / C {np.mean(c_frac)*100:.0f}% / "
          f"H {np.mean(h_frac)*100:.0f}%")

    # 오라클 오프셋(페어별 최소자승 최적 L* 상수 이동)
    oracle_offsets = np.array([
        np.mean(lab_targets[i][:, 0] - lab_preds[i][:, 0]) for i in range(n)
    ])

    def shifted_de(offsets):
        des = []
        for i in range(n):
            shifted = lab_preds[i].copy()
            shifted[:, 0] += offsets[i]
            des.append(_de00_from_lab(shifted, lab_targets[i]))
        return np.array(des)

    oracle_de = shifted_de(oracle_offsets)
    print(f"\n2) 페어별 L 오프셋 정렬(오라클) ΔE00 = {oracle_de.mean():.3f} "
          f"({(oracle_de.mean()/baseline_de.mean()-1)*100:+.1f}%)")

    # 오라클 affine (1차 회귀 pred_L -> target_L)
    affine_de_list = []
    for i in range(n):
        p, t = lab_preds[i][:, 0], lab_targets[i][:, 0]
        gain, offset = np.polyfit(p, t, 1)
        shifted = lab_preds[i].copy()
        shifted[:, 0] = gain * p + offset
        affine_de_list.append(_de00_from_lab(shifted, lab_targets[i]))
    affine_de = np.array(affine_de_list)
    print(f"3) 페어별 affine(게인+오프셋) 정렬(오라클) ΔE00 = {affine_de.mean():.3f} "
          f"({(affine_de.mean()/baseline_de.mean()-1)*100:+.1f}%)")

    # 전역 median 매핑 (배포 가능 - 모든 페어에 같은 값 하나)
    global_median = np.median(oracle_offsets)
    global_de = shifted_de(np.full(n, global_median))
    print(f"\n4) 전역 median 오프셋({global_median:+.2f}) 매핑 ΔE00 = {global_de.mean():.3f} "
          f"({(global_de.mean()/baseline_de.mean()-1)*100:+.1f}%)")

    # LOO 고정 오프셋 (배포 가능 - 각 페어는 나머지 12쌍의 median만 봄)
    loo_offsets = np.array([
        np.median(np.delete(oracle_offsets, i)) for i in range(n)
    ])
    loo_de = shifted_de(loo_offsets)
    print(f"5) LOO 고정 오프셋(과적합 방지) ΔE00 = {loo_de.mean():.3f} "
          f"({(loo_de.mean()/baseline_de.mean()-1)*100:+.1f}%)")

    print(f"\n오라클 오프셋 값(페어별, L* 단위): {np.round(oracle_offsets, 2).tolist()}")


if __name__ == "__main__":
    main()
