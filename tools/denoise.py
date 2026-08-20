"""
노이즈 제거 CLI.

  python3 -m tools.denoise input.jpg output.jpg
  python3 -m tools.denoise input.jpg output.jpg --strength 15
  python3 -m tools.denoise input.jpg output.jpg --method bilateral
"""
import argparse
import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.denoise import denoise


def main():
    parser = argparse.ArgumentParser(description="이미지 노이즈 제거")
    parser.add_argument("input", help="입력 이미지 경로")
    parser.add_argument("output", help="출력 이미지 경로")
    parser.add_argument("--strength", type=float, default=10,
                         help="노이즈 제거 강도 (기본 10, 높을수록 강함 - 디테일도 같이 흐려질 수 있음)")
    parser.add_argument("--method", choices=["nlm", "bilateral"], default="nlm",
                         help="nlm(기본, 고품질/느림) 또는 bilateral(빠름/약함)")
    args = parser.parse_args()

    img = cv2.imread(args.input)
    if img is None:
        print(f"이미지를 못 읽음: {args.input}")
        return

    print(f"denoise 중... (method={args.method}, strength={args.strength})")
    out = denoise(img, strength=args.strength, method=args.method)
    cv2.imwrite(args.output, out)
    print(f"저장: {args.output}")


if __name__ == "__main__":
    main()
