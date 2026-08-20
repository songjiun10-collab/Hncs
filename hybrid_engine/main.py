"""
Hybrid 9D Parametric Engine V0.1 CLI 엔트리 포인트 - RAW 파일을 받아서
카메라 고유 매트릭스/화이트밸런스 정제부터 톤/색 보정까지 전체 파이프
라인을 한 번에 돌리는 완성형 보정 프로그램.

출력 확장자로 형식을 정한다 - .jpg/.jpeg는 바로 보는 완성본(8비트 sRGB),
.tif/.tiff는 후속 편집/재파이프라인용 16비트. --profile을 생략하면
EXIF Make/Model로 카메라를 자동인식해서 맞는 프로필을 고른다 - 근거
데이터(assets/profiles/*.json)가 있는 카메라만 지원하고, 없으면 임의로
아무 프로필이나 갖다 쓰지 않고 에러로 알린다.

  python3 -m hybrid_engine.main input.3FR output.jpg
  python3 -m hybrid_engine.main input.RAF output.tiff --profile hasselblad
  python3 -m hybrid_engine.main input.3FR output.jpg --evaluate target.jpg
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2

from hybrid_engine.pipeline.engine import HybridCameraEngine
from hybrid_engine.core.color_matrix import extract_camera_metadata
from hybrid_engine.core.preset_inverse import detect_brand_from_exif
from hybrid_engine.utils.exif import read_make_model
from hybrid_engine.utils.io import decode_raw, save_tiff16, save_jpeg8
from hybrid_engine.utils.evaluate import mean_delta_e, load_image_linear_for_evaluate

_PROFILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "profiles")


def _available_profiles():
    return sorted(
        os.path.splitext(name)[0]
        for name in os.listdir(_PROFILES_DIR)
        if name.endswith(".json")
    )


def _load_profile(name):
    path = os.path.join(_PROFILES_DIR, f"{name}.json")
    with open(path, encoding="utf-8") as f:
        profile = json.load(f)
    profile.pop("_comment", None)
    return profile


def resolve_profile_name(raw_path, requested):
    """--profile이 명시되면 그대로 쓰고, 생략되면 EXIF Make/Model로
    카메라를 인식해서 근거 데이터가 있는 프로필을 자동으로 고른다.
    인식이 안 되거나 해당 카메라용 프로필이 없으면 None + 이유 문자열을
    반환한다 - 호출부가 에러로 처리해야 한다(임의 추측 금지)."""
    available = _available_profiles()
    if requested is not None:
        if requested not in available:
            return None, f"'{requested}' 프로필 없음 (사용 가능: {', '.join(available)})"
        return requested, None

    make, model = read_make_model(raw_path)
    brand = detect_brand_from_exif(make, model)
    if brand is None:
        return None, f"EXIF로 카메라를 못 알아봄 (Make={make!r}, Model={model!r})"
    if brand not in available:
        return None, (f"{brand} 카메라를 인식했지만 아직 보정 프로필이 없음 "
                       f"(사용 가능: {', '.join(available)})")
    print(f"EXIF 인식: Make={make!r} Model={model!r} -> profile={brand}")
    return brand, None


_EVALUATE_MAX_MEGAPIXELS = 20.0  # ΔE는 픽셀별 평균이라 해상도를 더 낮춰도
# 평균값 자체는 거의 안 바뀐다(analyze_pixel_errors.py 등 다른 진단
# 도구에서도 이미 쓰는 전제) - --max-megapixels로 저장용 출력 해상도를
# 낮추지 않은 경우에도 ΔE 계산 단계만 따로 더 가볍게 만든다.


def maybe_downsample(linear_rgb, max_megapixels):
    """엔진 파이프라인은 Linear RGB를 float64로 여러 벌 들고 있는 구간이
    있어서(실측: 60MP 처리 한 번에 peak RSS 13.9GB, 105MP 원본은 16GB로
    OOM kill됨), 최신 100MP대 센서(X2D II 등, 53MP대 X1D 기준으로 만들어진
    파이프라인이 검증된 적 없는 해상도)는 이 환경에서 안전하지 않다.
    max_megapixels(기본 50.0, X1D 53MP가 이 세션 내내 무사히 돌아간
    실측 상한에 여유를 둔 안전값)를 넘으면 비율을 유지하며 다운샘플한다
    - 0이면 무제한(고해상도는 자기 책임)."""
    if max_megapixels <= 0:
        return linear_rgb
    h, w = linear_rgb.shape[:2]
    megapixels = (h * w) / 1e6
    if megapixels <= max_megapixels:
        return linear_rgb
    scale = (max_megapixels / megapixels) ** 0.5
    new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
    print(f"{megapixels:.1f}MP -> {new_w}x{new_h}({new_w * new_h / 1e6:.1f}MP)로 다운샘플 "
          f"(파이프라인 메모리 한도 안전값 - 무제한으로 하려면 --max-megapixels 0)")
    return cv2.resize(linear_rgb, (new_w, new_h), interpolation=cv2.INTER_AREA)


def main():
    parser = argparse.ArgumentParser(description="Hybrid 9D Parametric Engine V0.1")
    parser.add_argument("input", help="입력 RAW 파일 경로")
    parser.add_argument("output", help="출력 이미지 경로 (.jpg/.jpeg 또는 .tif/.tiff)")
    parser.add_argument("--profile", default=None,
                         help="assets/profiles/<name>.json 프로필 이름 "
                              "(생략 시 EXIF로 자동인식)")
    parser.add_argument("--jpeg-quality", type=int, default=95,
                         help="JPEG 출력 품질 (기본 95, .jpg/.jpeg 출력에만 적용)")
    parser.add_argument("--max-megapixels", type=float, default=50.0,
                         help="이 값을 넘는 해상도는 자동 다운샘플 (기본 50.0 - "
                              "파이프라인 메모리 한도 안전값, 0이면 무제한)")
    parser.add_argument("--evaluate", default=None, metavar="TARGET_IMAGE",
                         help="이 이미지와 엔진 출력 사이 평균 ΔE(CIEDE2000)를 계산해서 출력")
    parser.add_argument("--no-srgb-encoding", action="store_true",
                         help="TIFF를 감마 인코딩 없이 순수 linear로 저장 (.tif/.tiff 출력에만 적용)")
    args = parser.parse_args()

    ext = os.path.splitext(args.output)[1].lower()
    if ext not in (".jpg", ".jpeg", ".tif", ".tiff"):
        print(f"지원하지 않는 출력 확장자: {ext!r} (.jpg/.jpeg 또는 .tif/.tiff만 지원)")
        sys.exit(1)

    profile_name, error = resolve_profile_name(args.input, args.profile)
    if error is not None:
        print(error)
        sys.exit(1)

    engine = HybridCameraEngine(profile=_load_profile(profile_name))

    print(f"RAW 디코드 중... ({args.input})")
    linear = decode_raw(args.input)
    linear = maybe_downsample(linear, args.max_megapixels)
    camera_wb = extract_camera_metadata(args.input)["camera_whitebalance"]

    print(f"파라메트릭 코어 처리 중... (profile={profile_name}, Phase 0 색정제 포함)")
    result = engine.process(linear, camera_whitebalance=camera_wb)

    if ext in (".jpg", ".jpeg"):
        save_jpeg8(result, args.output, quality=args.jpeg_quality)
    else:
        save_tiff16(result, args.output, apply_srgb_encoding=not args.no_srgb_encoding)
    print(f"저장: {args.output}")

    if args.evaluate:
        eval_result = maybe_downsample(result, _EVALUATE_MAX_MEGAPIXELS)
        target = load_image_linear_for_evaluate(args.evaluate, eval_result.shape)
        delta_e = mean_delta_e(eval_result, target)
        verdict = "합격 (< 2.0)" if delta_e < 2.0 else "불합격 (>= 2.0)"
        print(f"평균 ΔE (CIEDE2000): {delta_e:.3f} - {verdict}")


if __name__ == "__main__":
    main()
