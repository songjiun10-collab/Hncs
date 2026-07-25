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
# 그 대표 색온도. AsShotNeutral 기반 CCT 진단에서 "그 CCT면 어느 enum이
# 가장 가까운가"를 보여주는 용도로만 쓴다 - 실제로 .dcp에 쓰는 값은
# _calibration_illuminant()가 고정한 23(D50)이다(아래 docstring 참고).
LIGHT_SOURCE_ENUMS = [
    (17, "Standard light A", 2856.0),
    (23, "D50", 5003.0),
    (20, "D55", 5503.0),
    (21, "D65", 6504.0),
    (22, "D75", 7504.0),
]

# 피팅 참조값이 XYZ(D50)이므로(chart_baseline.reference_patches_xyz_d50())
# 피팅된 매트릭스는 구성상 D50 기준이다. 따라서 CalibrationIlluminant1은
# 23(D50)으로 고정한다.
CALIBRATION_ILLUMINANT_ENUM = 23
CALIBRATION_ILLUMINANT_NAME = "D50"

# chart_baseline.PATCH_NAMES에서 무채색 6패치(white 9.5 ~ black 2).
NEUTRAL_PATCH_INDICES = [18, 19, 20, 21, 22, 23]


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


def _measured_native_neutral(per_image):
    """차트의 무채색 6패치에서 카메라 네이티브 공간의 "중립색 방향"을
    실측한다. 패치별로 G=1로 정규화한 뒤(각 패치의 밝기가 아니라 색도만
    비교하려고) 패치·이미지 전체를 평균하고, 다시 G=1로 정규화한
    (3,) 배열과 패치별 값을 함께 반환.

    이 값이 AsShotNeutral과 같은 의미(중립 물체의 카메라 네이티브 RGB)를
    갖는 실측치라서, 둘을 비교하면 AsShotNeutral의 스케일 규약이
    decode_raw_native() 출력과 채널별로 일치하는지 검증할 수 있다."""
    per_patch = {}
    for idx in NEUTRAL_PATCH_INDICES:
        vals = []
        for samples in per_image.values():
            rgb = np.asarray(samples[idx], dtype=np.float64)
            if rgb[1] <= 0:
                continue
            vals.append(rgb / rgb[1])
        if vals:
            per_patch[chart_baseline.PATCH_NAMES[idx]] = np.mean(vals, axis=0)
    if not per_patch:
        return None, {}
    mean = np.mean(list(per_patch.values()), axis=0)
    mean = mean / mean[1]
    return mean, {k: v.tolist() for k, v in per_patch.items()}


def _calibration_illuminant(as_shot_neutral, measured_native_neutral, cam_to_xyz):
    """`.dcp`에 쓸 CalibrationIlluminant1을 정한다 - **항상 23(D50)**.

    왜 D50인가: chart_baseline.reference_patches_xyz_d50()이 차트 참조값을
    XYZ(D50)으로 색순응시킨 뒤 피팅하므로, 피팅된 매트릭스는 **구성상**
    D50 기준이다. 즉 "촬영 당시 조명이 D50이었다고 측정/가정했다"가 아니라
    "이 매트릭스가 대응하는 참조 백색점이 D50이다"라는 뜻이고, 이게 이
    데이터로 정당화할 수 있는 유일한 illuminant 주장이다. 촬영 당시의 실제
    장면 조명은 이 데이터에서 **복원 불가능하다**(단순히 "측정되지 않았다"
    보다 강한 진술이다): 참조값이 이미 D50으로 색순응된 상태로 피팅에
    들어가므로, 원래 조명의 정보는 피팅 결과에 남지 않는다.

    AsShotNeutral로 CCT를 역산하는 접근은 폐기했다. 진단으로만 남긴다:
      (a) 차트 촬영 당시의 조명이 실측되지 않았다(manifest의 illuminant
          칼럼이 10장 전부 비어있음).
      (b) AsShotNeutral 자체가 카메라의 자동 WB 판단 결과라 측정된
          조명값이 아니다.
      (c) **실측으로 판명**: AsShotNeutral은 DNG 스펙의 raw 값 스케일
          기준인데 cam_to_xyz는 decode_raw_native()의 libraw 디모자이크
          출력(/65535) 기준이고, 두 스케일이 채널별로 **일치하지 않는다** -
          아래 measured_over_as_shot_channel_scale이 R/B에서 1에서 크게
          벗어난다. CCT는 색도(xy)에서 나오고 xy는 전역 스케일에만
          불변이므로, 채널별 스케일 차이가 있으면 AsShotNeutral을
          cam_to_xyz에 먹여 구한 xy는 의미가 없다. 이전 버전 docstring이
          "확인하지 않았다"고 달아둔 caveat (c)가 이렇게 해소됐고, 결론은
          그 추정이 유효하지 않다는 쪽이다."""
    import colour
    diagnostic = {
        "as_shot_neutral": None if as_shot_neutral is None else as_shot_neutral.tolist(),
        "measured_native_neutral_g_normalized":
            None if measured_native_neutral is None else measured_native_neutral.tolist(),
        "measured_over_as_shot_channel_scale": None,
        "cct_from_as_shot_neutral": None,
        "nearest_enum_from_that_cct": None,
        "nearest_enum_name_from_that_cct": None,
        "conclusive": False,
        "note": "진단 전용 - CalibrationIlluminant1으로 쓰지 않는다. "
                "AsShotNeutral의 채널별 스케일이 decode_raw_native() 출력과 "
                "일치하지 않는 것이 실측으로 확인돼(아래 channel_scale), "
                "여기서 역산한 CCT는 유효한 추정이 아니다.",
    }
    if as_shot_neutral is not None:
        asn = np.asarray(as_shot_neutral, dtype=np.float64)
        if asn[1] > 0:
            asn_g = asn / asn[1]
            if measured_native_neutral is not None:
                with np.errstate(divide="ignore", invalid="ignore"):
                    diagnostic["measured_over_as_shot_channel_scale"] = \
                        (measured_native_neutral / asn_g).tolist()
        xyz = asn @ cam_to_xyz
        total = xyz.sum()
        if total > 0:
            xy = np.array([xyz[0] / total, xyz[1] / total])
            cct = float(colour.xy_to_CCT(xy, method="McCamy 1992"))
            enum_value, enum_name, _cct = min(LIGHT_SOURCE_ENUMS,
                                              key=lambda e: abs(e[2] - cct))
            diagnostic["neutral_xy"] = xy.tolist()
            diagnostic["cct_from_as_shot_neutral"] = cct
            diagnostic["nearest_enum_from_that_cct"] = enum_value
            diagnostic["nearest_enum_name_from_that_cct"] = enum_name

    return {
        "chosen_enum": CALIBRATION_ILLUMINANT_ENUM,
        "chosen_enum_name": CALIBRATION_ILLUMINANT_NAME,
        "reason": "피팅 참조값이 XYZ(D50)이라 매트릭스가 구성상 D50 기준 - "
                  "촬영 당시 장면 조명을 측정/가정한 값이 아니고, 그 조명은 "
                  "D50으로 색순응된 참조값에서 복원 불가능하다.",
        "as_shot_neutral_diagnostic": diagnostic,
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
    #    XYZ->cam인지 cam->XYZ인지, 그리고 행벡터/열벡터 규약 중 어느
    #    쪽인지 문서만으론 단정할 수 없다. 그래서 네 후보를 전부 적용해
    #    보고 XYZ 참조값에 가장 가까워지는 쪽을 채택한다.
    #
    #    후보가 둘이 아니라 넷인 이유: apply_color_matrix()는 이 프로젝트
    #    규약대로 **행벡터**로 적용한다(native_row @ candidate). 반면
    #    libraw의 rgb_xyz_matrix는 DNG의 ColorMatrix1과 같은 **열벡터**
    #    규약 매트릭스다(cam_col = M @ xyz_col). 열벡터 규약 매트릭스를
    #    행벡터로 적용하려면 전치해야 하므로, M/inv(M)만 시험하면 정답
    #    후보(M.T, inv(M).T)를 아예 빠뜨린다.
    candidates = {
        "M": libraw_m,
        "inv(M)": np.linalg.inv(libraw_m),
        "M.T": libraw_m.T,
        "inv(M).T": np.linalg.inv(libraw_m).T,
    }
    direction_de = {}
    for label, cand in candidates.items():
        direction_de[label] = float(np.mean([
            _mean_de(raw_baseline.apply_color_matrix(per_image[nm], cand), reference)
            for nm in names]))
    chosen = min(direction_de, key=direction_de.get)
    libraw_cam_to_xyz = candidates[chosen]
    libraw_mean = direction_de[chosen]
    print("\n=== libraw rgb_xyz_matrix 방향 판정 (4후보) ===")
    for label in candidates:
        print(f"  native @ {label:<10s} ΔE00 {direction_de[label]:.2f}")
    print(f"  채택: {chosen}")

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

    print("\nDCP ColorMatrix1(XYZ D50 -> 네이티브, 열벡터 규약) = inv(chart_m).T:")
    print(np.linalg.inv(chart_m).T)

    native_neutral, native_neutral_per_patch = _measured_native_neutral(per_image)
    as_shot = read_as_shot_neutral(raw_paths[names[0]])
    illuminant = _calibration_illuminant(as_shot, native_neutral, chart_m)
    print("\n=== CalibrationIlluminant1 (D50 고정) + AsShotNeutral 진단 ===")
    print(json.dumps(illuminant, indent=2, ensure_ascii=False))

    report = {
        "n_images": n,
        "images": names,
        "camera_model": read_unique_camera_model(raw_paths[names[0]]),
        "libraw_direction_delta_e": direction_de,
        "libraw_direction_chosen": chosen,
        "no_correction_delta_e_mean": no_corr,
        "libraw_matrix_delta_e_mean": libraw_mean,
        "chart_matrix_in_sample_delta_e_mean": in_sample,
        "chart_matrix_cv_delta_e_mean": cv_mean,
        "chart_matrix_cv_delta_e_per_image": cv_per_image,
        "improvement_vs_libraw_pct": improvement,
        "chart_matrix_beats_libraw": bool(cv_mean < libraw_mean),
        "chart_matrix_in_sample": chart_m.tolist(),
        # DCP의 ColorMatrix1은 열벡터 규약(native_col = CM1 @ xyz_col)인데
        # chart_matrix_in_sample은 행벡터 피팅 결과(xyz_row = native_row @ M)라
        # 역행렬만으로는 안 되고 전치까지 필요하다. .dcp를 만들 때 쓰는
        # 값이 정확히 이것이다(tests/test_dcp_export.py가 잠금).
        "dcp_color_matrix_1": np.linalg.inv(chart_m).T.tolist(),
        "libraw_cam_to_xyz": libraw_cam_to_xyz.tolist(),
        # 무채색 6패치에서 실측한 네이티브 중립색(패치별 G=1 정규화 후 평균).
        # AsShotNeutral과 같은 의미의 실측치 - 아래 illuminant 진단이 둘을
        # 비교해서 AsShotNeutral의 스케일 규약이 맞지 않음을 보인다.
        "measured_native_neutral_g_normalized":
            None if native_neutral is None else native_neutral.tolist(),
        "measured_native_neutral_per_patch": native_neutral_per_patch,
        "calibration_illuminant": illuminant,
    }
    out_path = os.path.join(SET_DIR, "camera_native_matrix_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n저장: {out_path}")


if __name__ == "__main__":
    main()
