"""
RAW -> Log 색공간 -> (선택) LUT 적용 CLI. core/log_pipeline.py 참고.

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
"""
import argparse
import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.log_pipeline import (
    LOG_SPACES, raw_to_prophoto_linear, apply_exposure, auto_exposure_average,
    auto_exposure_highlight_safe, auto_exposure_matrix, to_log_space, apply_cube_lut,
    to_16bit_bgr, write_exr,
)

_AUTO_EXPOSE_MODES = {
    "average": lambda linear, args: auto_exposure_average(linear),
    "highlight_safe": lambda linear, args: auto_exposure_highlight_safe(
        linear, percentile=args.highlight_percentile, target=args.highlight_target),
    "matrix": lambda linear, args: auto_exposure_matrix(linear),
}


def main():
    parser = argparse.ArgumentParser(description="RAW를 Log 색공간으로 변환 (+ 선택적 LUT 적용)")
    parser.add_argument("input", help="입력 RAW 파일 경로")
    parser.add_argument("output", help="출력 경로 (.tif/.tiff 또는 .exr)")
    parser.add_argument("--log-space", required=True, choices=sorted(LOG_SPACES),
                         help="타깃 Log 색공간")
    parser.add_argument("--lut", default=None, help="적용할 .cube LUT 파일 경로 (선택)")
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
    parser.add_argument("--exr-compression", default="zip",
                         help=".exr 출력 압축 방식 (기본 zip) - "
                              "none/rle/zips/zip/piz/pxr24/b44/b44a/dwaa/dwab")
    args = parser.parse_args()

    ext = os.path.splitext(args.output)[1].lower()
    if ext not in (".tif", ".tiff", ".exr"):
        print(f"지원하지 않는 출력 확장자: {ext!r} (.tif/.tiff 또는 .exr만 지원)")
        sys.exit(1)

    mode = args.auto_expose_mode or ("average" if args.auto_expose else None)

    print(f"RAW 디코드 중... ({args.input})")
    linear = raw_to_prophoto_linear(args.input)

    if mode:
        linear = _AUTO_EXPOSE_MODES[mode](linear, args)
    linear = apply_exposure(linear, args.exposure)

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
