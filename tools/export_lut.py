"""포토샵/DaVinci Resolve/Premiere용 .cube 3D LUT 내보내기 CLI.

brands/*.py의 apply_* 함수(hybrid_engine.core.preset_inverse.TARGET_FUNCS
레지스트리)를 core.lut_export로 구워서 표준 Adobe .cube 파일로 저장한다.
자세한 배경/한계는 core/lut_export.py의 모듈 docstring 참고.

사용법:
    python3 -m tools.export_lut --list
    python3 -m tools.export_lut hasselblad out.cube [--size 33]
"""
import argparse
import sys

from core.lut_export import bake_lut_from_function, write_cube_file
from hybrid_engine.core.preset_inverse import TARGET_FUNCS


def main():
    parser = argparse.ArgumentParser(description="brands/*.py apply_* 함수를 .cube 3D LUT으로 내보내기")
    parser.add_argument("preset", nargs="?", help="TARGET_FUNCS 키 (--list로 확인)")
    parser.add_argument("output", nargs="?", help="출력 .cube 파일 경로")
    parser.add_argument("--size", type=int, default=33, help="LUT 격자 한 변 크기 (기본 33, Adobe 표준)")
    parser.add_argument("--list", action="store_true", help="사용 가능한 preset 이름 목록 출력")
    args = parser.parse_args()

    if args.list or not args.preset:
        for name in sorted(TARGET_FUNCS):
            print(name)
        if not args.list:
            sys.exit("preset과 output 경로가 필요합니다 (--list로 사용 가능한 preset 확인)")
        return

    if args.preset not in TARGET_FUNCS:
        sys.exit(f"알 수 없는 preset: {args.preset} (--list로 확인)")
    if not args.output:
        sys.exit("output 경로가 필요합니다")

    lut = bake_lut_from_function(TARGET_FUNCS[args.preset], size=args.size)
    write_cube_file(lut, args.output, title=args.preset)
    print(f"저장됨: {args.output} (LUT_3D_SIZE {args.size}, preset={args.preset})")


if __name__ == "__main__":
    main()
