"""카메라 네이티브 공간에서 색매트릭스를 피팅해 libraw 내장 매트릭스와
비교한다 - DCP 프로필의 ColorMatrix1이 요구하는 공간이 기존
tools/analyze_colorchecker_matrix.py가 다루는 공간(libraw가 이미 자기
매트릭스를 적용한 sRGB)과 다르기 때문. 설계 근거:
docs/superpowers/specs/2026-07-25-camera-native-matrix-dcp-design.md

  python3 -m tools.analyze_camera_native_matrix
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import rawpy

from hybrid_engine.core import chart_baseline, raw_baseline
from hybrid_engine.utils.exif import read_as_shot_neutral, read_unique_camera_model
from hybrid_engine.utils.io import decode_raw_native

SET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "datasets", "hasselblad", "contributed", "kmichels-x2dii-2026-07")

# EXIF LightSource enum 중 DCP의 CalibrationIlluminant로 흔히 쓰는 값과
# 그 대표 색온도. 추정 CCT에서 가장 가까운 것을 고른다.
LIGHT_SOURCE_ENUMS = [
    (17, "Standard light A", 2856.0),
    (23, "D50", 5003.0),
    (20, "D55", 5503.0),
    (21, "D65", 6504.0),
    (22, "D75", 7504.0),
]


def _load_native_chart_samples():
    """각 차트 RAW를 카메라 네이티브로 디코드해서 24패치를 샘플링.
    반환: {파일명: (24, 3) 네이티브 RGB}"""
    raw_paths = sorted(glob.glob(os.path.join(SET_DIR, "raw", "*.3FR")))
    per_image = {}
    for raw_path in raw_paths:
        name = os.path.basename(raw_path)
        print(f"  디코드+검출 중(네이티브): {name}", flush=True)
        native = decode_raw_native(raw_path)
        samples = chart_baseline.detect_and_sample(native)
        if samples is None:
            print(f"    차트 검출 실패, 제외: {name}")
            continue
        per_image[name] = samples
    return per_image


def _libraw_matrix(raw_path):
    """libraw 내장 rgb_xyz_matrix의 앞 3행. RGB 카메라는 4번째 행이
    전부 0이라 잘라낸다(4색 센서용 자리)."""
    with rawpy.imread(raw_path) as raw:
        return np.asarray(raw.rgb_xyz_matrix, dtype=np.float64)[:3, :3]


def _mean_de(samples_xyz, reference):
    return float(np.mean(chart_baseline.patch_delta_e_xyz_d50(samples_xyz, reference)))


def _estimate_illuminant(as_shot_neutral, cam_to_xyz):
    """AsShotNeutral(촬영 당시 중립색의 카메라 네이티브 RGB)을 피팅된
    매트릭스로 XYZ에 보내 그 색도의 CCT를 추정하고, 가장 가까운 EXIF
    LightSource enum을 고른다.

    주의: 이건 **추정**이다. 세 겹으로 그렇다.
      (a) 차트 촬영 당시의 조명이 실측되지 않았다(manifest의 illuminant
          칼럼이 10장 전부 비어있음).
      (b) AsShotNeutral 자체가 카메라의 자동 WB 판단 결과라 측정된
          조명값이 아니다.
      (c) AsShotNeutral은 DNG 스펙의 raw 값 스케일 기준인데 cam_to_xyz는
          decode_raw_native()가 낸 libraw 디모자이크 출력(/65535 정규화)
          기준으로 피팅된 것이라, 두 스케일이 채널별로 정확히 일치한다는
          보장이 없다. 다만 CCT는 색도(xy)에서만 나오고 xy는 전역 스케일에
          불변이므로, 채널별 스케일 차이가 없다면 이 추정은 유효하다 -
          libraw가 채널별로 다른 정규화를 적용하는 경우에만 틀어진다.
          이 부분은 확인하지 않았다."""
    import colour
    if as_shot_neutral is None:
        return None
    xyz = np.asarray(as_shot_neutral, dtype=np.float64) @ cam_to_xyz
    total = xyz.sum()
    if total <= 0:
        return None
    xy = np.array([xyz[0] / total, xyz[1] / total])
    cct = float(colour.xy_to_CCT(xy, method="McCamy 1992"))
    enum_value, enum_name, enum_cct = min(LIGHT_SOURCE_ENUMS,
                                          key=lambda e: abs(e[2] - cct))
    return {
        "as_shot_neutral": as_shot_neutral.tolist(),
        "neutral_xy": xy.tolist(),
        "estimated_cct": cct,
        "chosen_enum": enum_value,
        "chosen_enum_name": enum_name,
        "chosen_enum_cct": enum_cct,
        "note": "추정값 - 촬영 당시 조명이 실측되지 않았음(manifest illuminant 칼럼 공백)",
    }


def main():
    reference = chart_baseline.reference_patches_xyz_d50()
    per_image = _load_native_chart_samples()
    names = sorted(per_image.keys())
    n = len(names)
    print(f"\n검출 성공 {n}장: {names}")
    if n < 2:
        print("이미지가 2장 미만이라 교차검증 불가")
        sys.exit(1)

    raw_paths = {os.path.basename(p): p
                 for p in glob.glob(os.path.join(SET_DIR, "raw", "*.3FR"))}
    libraw_m = _libraw_matrix(raw_paths[names[0]])

    # 1) libraw 매트릭스의 방향을 실측으로 확정한다 - rgb_xyz_matrix가
    #    XYZ->cam인지 cam->XYZ인지 문서만으론 단정할 수 없어서, 두 방향
    #    다 적용해보고 XYZ 참조값에 가까워지는 쪽을 채택한다.
    as_is = float(np.mean([
        _mean_de(raw_baseline.apply_color_matrix(per_image[nm], libraw_m), reference)
        for nm in names]))
    inverted_m = np.linalg.inv(libraw_m)
    inverted = float(np.mean([
        _mean_de(raw_baseline.apply_color_matrix(per_image[nm], inverted_m), reference)
        for nm in names]))
    if as_is <= inverted:
        libraw_cam_to_xyz, chosen = libraw_m, "as_is"
    else:
        libraw_cam_to_xyz, chosen = inverted_m, "inverted"
    print("\n=== libraw rgb_xyz_matrix 방향 판정 ===")
    print(f"  그대로 적용(native @ M):        ΔE00 {as_is:.2f}")
    print(f"  역행렬 적용(native @ inv(M)):   ΔE00 {inverted:.2f}")
    print(f"  채택: {chosen}")
    libraw_mean = min(as_is, inverted)

    # 2) 보정 없음 - 네이티브 값을 XYZ로 그대로 간주(스케일 감각용,
    #    정상적으로 매우 나쁠 것)
    no_corr = float(np.mean([_mean_de(per_image[nm], reference) for nm in names]))

    # 3) 차트 피팅: in-sample + leave-one-image-out CV
    all_sources = [per_image[nm] for nm in names]
    all_targets = [reference for _ in names]
    chart_m = raw_baseline.fit_color_matrix(all_sources, all_targets)
    in_sample = float(np.mean([
        _mean_de(raw_baseline.apply_color_matrix(per_image[nm], chart_m), reference)
        for nm in names]))

    cv_per_image = {}
    for i, held_out in enumerate(names):
        train_sources = [per_image[nm] for j, nm in enumerate(names) if j != i]
        train_targets = [reference for _ in train_sources]
        m = raw_baseline.fit_color_matrix(train_sources, train_targets)
        corrected = raw_baseline.apply_color_matrix(per_image[held_out], m)
        cv_per_image[held_out] = _mean_de(corrected, reference)
    cv_mean = float(np.mean(list(cv_per_image.values())))

    improvement = (1 - cv_mean / libraw_mean) * 100 if libraw_mean > 0 else 0.0

    print("\n=== 패치 평균 ΔE00 (XYZ D50 기준, 이미지별 평균의 평균) ===")
    print(f"보정 없음(네이티브를 XYZ로 간주):        {no_corr:.2f}")
    print(f"libraw 내장 매트릭스({chosen}):          {libraw_mean:.2f}")
    print(f"차트 매트릭스 in-sample({n}장 pooled):     {in_sample:.2f}")
    print(f"차트 매트릭스 leave-one-image-out CV:   {cv_mean:.2f}")
    print(f"\nlibraw 대비 개선(CV 기준): {improvement:+.1f}%")
    if cv_mean < libraw_mean:
        print("=> 차트 매트릭스가 libraw를 이겼다. DCP 프로필 생성 조건 충족.")
    else:
        print("=> 차트 매트릭스가 libraw를 못 이겼다. DCP 프로필은 생성하지 않는다.")

    print("\n차트 매트릭스(네이티브 -> XYZ D50, in-sample):")
    print(chart_m)

    as_shot = read_as_shot_neutral(raw_paths[names[0]])
    illuminant = _estimate_illuminant(as_shot, chart_m)
    print("\n=== CalibrationIlluminant 추정 ===")
    print(illuminant)

    report = {
        "n_images": n,
        "images": names,
        "camera_model": read_unique_camera_model(raw_paths[names[0]]),
        "libraw_direction_delta_e": {"as_is": as_is, "inverted": inverted},
        "libraw_direction_chosen": chosen,
        "no_correction_delta_e_mean": no_corr,
        "libraw_matrix_delta_e_mean": libraw_mean,
        "chart_matrix_in_sample_delta_e_mean": in_sample,
        "chart_matrix_cv_delta_e_mean": cv_mean,
        "chart_matrix_cv_delta_e_per_image": cv_per_image,
        "improvement_vs_libraw_pct": improvement,
        "chart_matrix_beats_libraw": bool(cv_mean < libraw_mean),
        "chart_matrix_in_sample": chart_m.tolist(),
        "libraw_cam_to_xyz": libraw_cam_to_xyz.tolist(),
        "estimated_illuminant": illuminant,
    }
    out_path = os.path.join(SET_DIR, "camera_native_matrix_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n저장: {out_path}")


if __name__ == "__main__":
    main()
