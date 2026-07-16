"""
Hybrid 9D Parametric Engine V0.1 CLI 엔트리 포인트.

  python3 -m hybrid_engine.main input.RAF output.tiff
  python3 -m hybrid_engine.main input.RAF output.tiff --profile hasselblad
  python3 -m hybrid_engine.main input.RAF output.tiff --profile hasselblad --evaluate target.jpg
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hybrid_engine.pipeline.engine import HybridCameraEngine
from hybrid_engine.core.color_matrix import extract_camera_metadata
from hybrid_engine.utils.io import decode_raw, save_tiff16
from hybrid_engine.utils.evaluate import mean_delta_e, load_image_linear_for_evaluate

_PROFILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "profiles")


def _load_profile(name):
    if name is None:
        return None
    path = os.path.join(_PROFILES_DIR, f"{name}.json")
    with open(path, encoding="utf-8") as f:
        profile = json.load(f)
    profile.pop("_comment", None)
    return profile


def main():
    parser = argparse.ArgumentParser(description="Hybrid 9D Parametric Engine V0.1")
    parser.add_argument("input", help="입력 RAW 파일 경로")
    parser.add_argument("output", help="출력 16비트 TIFF 경로")
    parser.add_argument("--profile", default=None,
                         help="assets/profiles/<name>.json 프로필 이름 (생략 시 기본값)")
    parser.add_argument("--evaluate", default=None, metavar="TARGET_IMAGE",
                         help="이 이미지와 엔진 출력 사이 평균 ΔE(CIEDE2000)를 계산해서 출력")
    parser.add_argument("--no-srgb-encoding", action="store_true",
                         help="TIFF를 감마 인코딩 없이 순수 linear로 저장")
    args = parser.parse_args()

    profile = _load_profile(args.profile)
    engine = HybridCameraEngine(profile=profile)

    print(f"RAW 디코드 중... ({args.input})")
    linear = decode_raw(args.input)
    camera_wb = extract_camera_metadata(args.input)["camera_whitebalance"]

    print(f"파라메트릭 코어 처리 중... (profile={args.profile or 'default'}, Phase 0 색정제 포함)")
    result = engine.process(linear, camera_whitebalance=camera_wb)

    save_tiff16(result, args.output, apply_srgb_encoding=not args.no_srgb_encoding)
    print(f"저장: {args.output}")

    if args.evaluate:
        target = load_image_linear_for_evaluate(args.evaluate, result.shape)
        delta_e = mean_delta_e(result, target)
        verdict = "합격 (< 2.0)" if delta_e < 2.0 else "불합격 (>= 2.0)"
        print(f"평균 ΔE (CIEDE2000): {delta_e:.3f} - {verdict}")


if __name__ == "__main__":
    main()
