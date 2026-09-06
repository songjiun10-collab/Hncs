"""
RAW -> Log 또는 HDR(PQ/HLG) 색공간 -> (선택) LUT 적용 CLI. core/log_pipeline.py 참고.

출력 확장자로 형식을 정한다 - .tif/.tiff는 16비트 정수(범용, 뷰어 호환성
좋음), .exr는 32비트 float OpenEXR(씬 참조 워크플로우 실제 업계 표준,
DaVinci Resolve/Nuke 등이 직접 읽음 - 클리핑 없이 Log/HDR 값을 그대로
보존).

  python3 -m tools.raw_pipeline input.CR3 output.tiff --log-space F-Log2
  python3 -m tools.raw_pipeline input.CR3 output.exr --log-space S-Log3
  python3 -m tools.raw_pipeline input.ARW output.tiff --log-space S-Log3 --lut looks/my_look.cube
  python3 -m tools.raw_pipeline input.CR3 output.tiff --log-space S-Log3 --exposure 1.5
  python3 -m tools.raw_pipeline input.CR3 output.tiff --log-space V-Log --auto-expose-mode highlight_safe
  python3 -m tools.raw_pipeline input.CR3 output.tiff --log-space V-Log --auto-expose-mode matrix
  python3 -m tools.raw_pipeline input.CR3 output.tiff --log-space S-Log3 --auto-wb-mode white_patch
  python3 -m tools.raw_pipeline input.CR3 output.tiff --log-space S-Log3 --auto-wb-mode shades_of_gray
  python3 -m tools.raw_pipeline input.CR3 output.tiff --hdr-space HLG
  python3 -m tools.raw_pipeline input.CR3 output.exr --hdr-space PQ --hdr-peak-nits 4000
  python3 -m tools.raw_pipeline input.RAF output.tiff --log-space F-Log2 --lens-correct

--log-space와 --hdr-space는 상호배타(그레이딩용 Log 커브 vs BT.2020
PQ/HLG HDR 인코딩 - core/log_pipeline.py의 to_hdr_space() docstring 참고,
미검증 항목)이고 --lut는 --log-space 전용이다.
"""
import argparse
import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.log_pipeline import (
    LOG_SPACES, HDR_SPACES, raw_to_prophoto_linear, apply_exposure, auto_exposure_average,
    auto_exposure_highlight_safe, auto_exposure_matrix, estimate_wb_shades_of_gray,
    estimate_wb_white_patch, to_log_space, to_hdr_space, apply_cube_lut, to_16bit_bgr, write_exr,
)
from core.lens_correction import correct_from_exif
from tools.lens_correction import resolve_lens_params

_AUTO_EXPOSE_MODES = {
    "average": lambda linear, args: auto_exposure_average(linear),
    "highlight_safe": lambda linear, args: auto_exposure_highlight_safe(
        linear, percentile=args.highlight_percentile, target=args.highlight_target),
    "matrix": lambda linear, args: auto_exposure_matrix(linear),
}

_AUTO_WB_MODES = {
    "white_patch": lambda linear, args: estimate_wb_white_patch(
        linear, percentile=args.wb_percentile),
    "shades_of_gray": lambda linear, args: estimate_wb_shades_of_gray(
        linear, p=args.wb_minkowski_p),
}


def lens_correct_linear_image(input_path, linear_rgb, *, make=None, model=None,
                              lens=None, focal_length=None, aperture=None,
                              distance=1000.0):
    """RAW EXIF/lensfun 프로파일로 선형 RGB 이미지의 왜곡을 보정한다.

    색공간·노출·LUT 처리보다 앞 단계에서 실행한다. 왜곡 보정은 픽셀의
    위치만 재배치하므로 선형 ProPhoto RGB에 적용해도 색값 자체는 바꾸지
    않으며, 이후 모든 Log/HDR/LUT 경로가 동일한 기하 보정 결과를 사용한다.

    EXIF 또는 명시적 override에 필요한 정보가 없거나 lensfun DB에 프로필이
    없으면 ``RuntimeError``를 낸다. 요청한 보정을 조용히 생략하지 않도록
    의도적으로 fail-closed 동작을 한다.
    """
    params = resolve_lens_params(
        input_path, make=make, model=model, lens=lens,
        focal_length=focal_length, aperture=aperture,
    )
    corrected, info = correct_from_exif(linear_rgb, distance=distance, **params)
    if not info["ok"]:
        raise RuntimeError(f"{info['reason']} ({info})")
    return corrected, info


def main():
    parser = argparse.ArgumentParser(description="RAW를 Log 색공간으로 변환 (+ 선택적 LUT 적용)")
    parser.add_argument("input", help="입력 RAW 파일 경로")
    parser.add_argument("output", help="출력 경로 (.tif/.tiff 또는 .exr)")
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--log-space", choices=sorted(LOG_SPACES),
                               help="타깃 Log 색공간 (--hdr-space와 동시 사용 불가)")
    target_group.add_argument("--hdr-space", choices=sorted(HDR_SPACES),
                               help="타깃 HDR 색공간(PQ/HLG, BT.2020 색역) - "
                                    "--log-space와 동시 사용 불가. 그레이딩용 중간산물이 "
                                    "목적으로, 실제 HDR10/HLG 디스플레이나 DaVinci 등에서 "
                                    "확인된 적은 없음(미검증)")
    parser.add_argument("--hdr-peak-nits", type=float, default=1000.0,
                         help="--hdr-space에서 linear 1.0(기준 화이트)이 대응하는 절대 "
                              "밝기(cd/m^2, 기본 1000 - 그레이딩 업계 관례). PQ는 ST 2084 "
                              "스펙상 10000nit 시스템피크가 고정이라 이 값은 '1.0이 몇 "
                              "nit인가'만 정하고, HLG는 이 값을 nominal peak luminance로도 "
                              "그대로 씀")
    parser.add_argument("--lut", default=None,
                         help="적용할 .cube LUT 파일 경로 (--log-space 전용, --hdr-space와 "
                              "동시 사용 불가 - PQ/HLG 인코딩된 값에 Log용 LUT을 얹는 건 "
                              "의미가 불분명해서 범위 밖)")
    parser.add_argument("--exposure", type=float, default=0.0,
                         help="수동 노출 보정 (EV 스탑, 기본 0)")
    parser.add_argument("--auto-expose-mode", choices=sorted(_AUTO_EXPOSE_MODES), default=None,
                         help="자동노출 모드 - average(전체평균을 미드그레이로) / "
                              "highlight_safe(하이라이트가 안 타도록 상위 백분위수 기준) / "
                              "matrix(카메라 평가측광 흉내, 중앙 가중). "
                              "--exposure와 동시 사용 시 자동노출 먼저 적용 후 추가 보정")
    parser.add_argument("--auto-expose", action="store_true",
                         help="[구버전 호환] --auto-expose-mode average 와 동일")
    parser.add_argument("--highlight-percentile", type=float, default=99.5,
                         help="highlight_safe 모드에서 지킬 백분위수 (기본 99.5)")
    parser.add_argument("--highlight-target", type=float, default=0.9,
                         help="highlight_safe 모드에서 그 백분위수가 위치할 linear 값 (기본 0.9)")
    parser.add_argument("--auto-wb-mode", choices=sorted(_AUTO_WB_MODES), default=None,
                         help="자동 화이트밸런스 모드 - white_patch(채널별 최고밝기를 흰색으로) / "
                              "shades_of_gray(Gray World~White Patch를 잇는 민코프스키 p-노름 "
                              "일반화, Finlayson&Trezzi 2004). 지정하면 카메라 WB 없이 디코드한 "
                              "뒤 이 알고리즘으로 화이트밸런스를 대신 추정한다(카메라 WB와 이중 "
                              "적용 방지) - 자동노출/수동노출보다 먼저 적용. 실측(2026-08, "
                              "docs/measurements.md): raw_calib_cache 13장 기준 카메라 실제 "
                              "화이트밸런스 대비 평균 ΔE00 14~16(명백히 다른 색감) - 실사용 "
                              "권장 안 함, 조명정보 없는 창작 실험용")
    parser.add_argument("--wb-percentile", type=float, default=99.9,
                         help="white_patch 모드에서 '흰 패치'로 볼 채널별 백분위수 (기본 99.9)")
    parser.add_argument("--wb-minkowski-p", type=float, default=6.0,
                         help="shades_of_gray 모드의 민코프스키 노름 차수 (기본 6, "
                              "Finlayson&Trezzi 논문 권장값)")
    parser.add_argument("--exr-compression", default="zip",
                         help=".exr 출력 압축 방식 (기본 zip) - "
                              "none/rle/zips/zip/piz/pxr24/b44/b44a/dwaa/dwab")
    parser.add_argument("--lens-correct", action="store_true",
                        help="EXIF/lensfun DB로 왜곡을 보정. 기본은 끔 - "
                             "기존 출력 기하를 바꾸지 않으며, 요청 시 매치 실패를 오류로 처리")
    parser.add_argument("--make", default=None,
                        help="렌즈 보정용 카메라 제조사 override (기본 EXIF)")
    parser.add_argument("--model", default=None,
                        help="렌즈 보정용 카메라 모델 override (기본 EXIF)")
    parser.add_argument("--lens", default=None,
                        help="렌즈 보정용 렌즈 모델 override (기본 EXIF LensModel/LensID/LensInfo)")
    parser.add_argument("--focal-length", type=float, default=None,
                        help="렌즈 보정용 초점거리 mm override (기본 EXIF)")
    parser.add_argument("--aperture", type=float, default=None,
                        help="렌즈 보정용 조리개값 override (기본 EXIF)")
    parser.add_argument("--lens-distance", type=float, default=1000.0,
                        help="렌즈 보정용 촬영 거리 근사치(m), 기본 1000(무한대에 가깝게)")
    args = parser.parse_args()

    ext = os.path.splitext(args.output)[1].lower()
    if ext not in (".tif", ".tiff", ".exr"):
        print(f"지원하지 않는 출력 확장자: {ext!r} (.tif/.tiff 또는 .exr만 지원)")
        sys.exit(1)

    if args.hdr_space and args.lut:
        print("--hdr-space는 --lut와 동시 사용 불가 (Log용 LUT을 PQ/HLG 값에 적용하는 건 "
              "의미가 불분명해서 범위 밖)")
        sys.exit(1)

    mode = args.auto_expose_mode or ("average" if args.auto_expose else None)

    print(f"RAW 디코드 중... ({args.input})")
    linear = raw_to_prophoto_linear(args.input, use_camera_wb=not args.auto_wb_mode)

    if args.lens_correct:
        print("렌즈 왜곡 보정 중... (EXIF/lensfun)")
        try:
            linear, lens_info = lens_correct_linear_image(
                args.input, linear, make=args.make, model=args.model,
                lens=args.lens, focal_length=args.focal_length,
                aperture=args.aperture, distance=args.lens_distance,
            )
        except (RuntimeError, ValueError) as exc:
            print(f"렌즈 보정 실패: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"매치된 DB 프로파일: 카메라={lens_info['camera']}  "
              f"렌즈={lens_info['lens']}")

    if args.auto_wb_mode:
        print(f"자동 화이트밸런스 추정 중... (auto_wb_mode={args.auto_wb_mode})")
        linear = _AUTO_WB_MODES[args.auto_wb_mode](linear, args)

    if mode:
        linear = _AUTO_EXPOSE_MODES[mode](linear, args)
    linear = apply_exposure(linear, args.exposure)

    if args.hdr_space:
        print(f"HDR 변환 중... (hdr_space={args.hdr_space}, peak_nits={args.hdr_peak_nits})")
        log_img = to_hdr_space(linear, args.hdr_space, peak_nits=args.hdr_peak_nits)
    else:
        print(f"Log 변환 중... (log_space={args.log_space})")
        log_img = to_log_space(linear, args.log_space)

    if args.lut:
        print(f"LUT 적용 중... ({args.lut})")
        log_img = apply_cube_lut(log_img, args.lut)

    if ext == ".exr":
        write_exr(log_img, args.output, compression=args.exr_compression)
    else:
        bgr16 = to_16bit_bgr(log_img)
        cv2.imwrite(args.output, bgr16)
    print(f"저장: {args.output}")


if __name__ == "__main__":
    main()
