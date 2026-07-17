"""
JPEG 입력 전용 CLI - EXIF로 소스 카메라를 자동인식해서 그 브랜드
시그니처를 역산하고, 타깃 브랜드로 재렌더링한다. RAW 입력은
main.py(HybridCameraEngine, Phase 0~1 정규화 기반)를 쓴다 - 이 스크립트는
core/preset_inverse.py(EXIF 기반 프리셋 역산) 전용.

  python3 -m hybrid_engine.convert input.jpg output.jpg --target hasselblad
  python3 -m hybrid_engine.convert input.jpg output.jpg --source canon --target sony
"""
import argparse
import os
import subprocess
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2

from hybrid_engine.core.preset_inverse import (
    BRAND_FUNCS, TARGET_FUNCS, convert_between_brands, detect_brand_from_exif,
)


def _read_exif_make_model(path):
    out = subprocess.run(["exiftool", "-json", "-Make", "-Model", path],
                          capture_output=True, text=True, timeout=30)
    data = json.loads(out.stdout) if out.stdout.strip() else [{}]
    d = data[0] if data else {}
    return d.get("Make"), d.get("Model")


def main():
    parser = argparse.ArgumentParser(
        description="EXIF 기반 카메라 프리셋 역산 + 타깃 브랜드 재적용")
    parser.add_argument("input", help="입력 JPEG 경로")
    parser.add_argument("output", help="출력 JPEG 경로")
    parser.add_argument("--target", required=True, choices=sorted(TARGET_FUNCS),
                         help="재렌더링할 타깃 브랜드/프리셋 (fuji_*는 타깃 전용 - 역산 소스 불가)")
    parser.add_argument("--source", default=None, choices=sorted(BRAND_FUNCS),
                         help="소스 브랜드를 직접 지정 (생략 시 EXIF Make/Model로 자동인식)")
    args = parser.parse_args()

    source = args.source
    if source is None:
        make, model = _read_exif_make_model(args.input)
        source = detect_brand_from_exif(make, model)
        if source is None:
            print(f"EXIF로 소스 브랜드를 못 알아봄 (Make={make!r}, Model={model!r}) - "
                  f"--source로 직접 지정하거나, 근거 데이터 없는 카메라는 지원 불가")
            sys.exit(1)
        print(f"EXIF 인식: Make={make!r} Model={model!r} -> source={source}")

    img = cv2.imread(args.input)
    if img is None:
        print(f"이미지를 못 읽음: {args.input}")
        sys.exit(1)

    print(f"{source} 시그니처 역산 -> {args.target} 재적용 중...")
    out = convert_between_brands(img, source, args.target)
    cv2.imwrite(args.output, out, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print(f"저장: {args.output}")


if __name__ == "__main__":
    main()
