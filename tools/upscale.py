"""Real-ESRGAN AI 업스케일 CLI. core/upscale.py 참고.

  python3 -m tools.upscale input.jpg output.jpg --scale 4 --engine onnx
  python3 -m tools.upscale input.jpg output.jpg --scale 2 --engine pytorch
  python3 -m tools.upscale input.jpg output.jpg --scale 4 --tile-size 256 --tile-pad 16
"""
import argparse
import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.upscale import UPSCALE_ENGINES, UPSCALE_SCALES, upscale


def main():
    parser = argparse.ArgumentParser(description="Real-ESRGAN으로 이미지를 AI 업스케일")
    parser.add_argument("input", help="입력 이미지 경로 (jpg/png/tiff 등 cv2가 읽는 포맷)")
    parser.add_argument("output", help="출력 이미지 경로")
    parser.add_argument("--scale", type=int, default=4, choices=UPSCALE_SCALES,
                         help="업스케일 배율 (기본 4)")
    parser.add_argument("--engine", default="onnx", choices=UPSCALE_ENGINES,
                         help="실행 엔진 - onnx(가벼움, 최초 1회 torch로 변환/캐시) 또는 "
                              "pytorch (기본 onnx)")
    parser.add_argument("--tile-size", type=int, default=512,
                         help="타일 크기(픽셀, 기본 512) - 크면 빠르지만 메모리 더 씀. "
                              "100MP급 원본은 반드시 통짜로 넣지 말고 타일 처리할 것")
    parser.add_argument("--tile-pad", type=int, default=10,
                         help="타일 겹침 패딩(픽셀, 기본 10) - 타일 경계 아티팩트 완화")
    args = parser.parse_args()

    img = cv2.imread(args.input, cv2.IMREAD_COLOR)
    if img is None:
        print(f"이미지를 읽을 수 없음: {args.input}")
        sys.exit(1)

    print(f"업스케일 중... (scale={args.scale}, engine={args.engine}, "
          f"입력 {img.shape[1]}x{img.shape[0]})")
    out = upscale(img, scale=args.scale, engine=args.engine,
                  tile_size=args.tile_size, tile_pad=args.tile_pad)
    cv2.imwrite(args.output, out)
    print(f"저장: {args.output} ({out.shape[1]}x{out.shape[0]})")


if __name__ == "__main__":
    main()
