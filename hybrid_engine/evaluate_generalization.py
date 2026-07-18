"""
[Protocol 2: Cross-camera generalization] 여러 소스 카메라를 hybrid_engine으로
같은 타깃 브랜드로 변환했을 때 결과가 수렴하는지 측정. 설계 근거는 이
대화의 평가 파이프라인 설계 문서 참고.

**정답이 없는 문제다** - "Sony로 찍었으면 Hasselblad가 어떻게 나왔을까"의
실측 정답 자체가 존재하지 않는다(같은 피사체를 여러 카메라로 동시
촬영한 데이터가 없는 한). 그래서 정확도가 아니라 두 개의 간접 지표로
설계했다:

  1. **수렴성(convergence)**: 서로 다른 소스를 같은 타깃으로 변환한
     결과들의 population 통계(b2/w995/sat, core.stats.image_stats)가
     서로 얼마나 가까운지(소스 간 표준편차) - 작을수록 "소스가 뭐든
     타깃 정체성으로 잘 수렴한다"는 신호
  2. **지문 소거(fingerprint erasure)**: 변환 전/후로 소스 간 노이즈
     시그니처(tools.iso_noise.estimate_noise_sigma) 분산이 줄어드는지 -
     안 줄면 톤/색만 바뀌고 카메라 고유 렌더링 특성은 안 지워진 것

**데이터 제약(정직하게 명시)**: 이 환경엔 실제 RAW가 Fuji(raw_calib_cache_fuji/)
뿐이라 그 경로는 hybrid_engine의 RAW 입력 경로(HybridCameraEngine, 브랜드
역산 불필요 - 카메라 무관)로 진짜 raw 기반 테스트를 한다. Sony/Nikon/Canon은
raw+jpeg 페어를 이 프로젝트가 여러 번 찾아봤지만 못 구해서(brands/canon.py,
nikon.py docstring), 각 브랜드의 apply_*_look()을 공통 테스트 사진에
합성 적용한 근사 소스로 대체한다(JPEG 입력 경로, preset_inverse 역산
필요) - **진짜 카메라 데이터가 아니라는 caveat이 리포트에 항상 같이
찍힌다.**

**알려진 방법론적 함정(2026-07 첫 실행에서 발견) - 합성 소스 간
수렴이 부풀려져 보일 수 있다.** sony/nikon/canon 합성 소스는 전부
"같은 하나의" base-image에 서로 다른 apply_*_look()을 적용해서 만든다.
`convert_between_brands()`의 역산 단계(`remove_camera_signature`)가 그
브랜드 커브의 거의 정확한 역함수라서, 셋 다 원래의 그 base-image L채널로
거의 되돌아간 뒤 같은 타깃 커브를 맞으니 "소스가 달라도 수렴한다"가
아니라 "애초에 같은 사진이었으니 당연히 수렴한다"에 가깝다 - 순환
논증 위험. 실제로 첫 실행에서 sony/nikon/canon의 변환 후 b2가 셋 다
정확히 10.0으로 나왔는데(의심스러울 만큼 완벽) 진짜 raw인 fuji는
58.0으로 확 벌어졌다 - **합성 소스 셋의 "수렴"은 신뢰하지 말고, raw
기반 소스(fuji)와의 차이가 더 정직한 신호.** 서로 다른 base-image를
브랜드마다 쓰도록 바꾸면 이 함정을 줄일 수 있으나 아직 미구현 - 지금
버전의 알려진 한계로만 기록.

  python3 -m hybrid_engine.evaluate_generalization --target hasselblad --base-image photo.jpg
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import rawpy

from hybrid_engine.core.preset_inverse import BRAND_FUNCS, convert_between_brands
from hybrid_engine.pipeline.engine import HybridCameraEngine
from hybrid_engine.utils.io import decode_raw
from core.stats import image_stats
from tools.iso_noise import estimate_noise_sigma

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FUJI_RAW_GLOB = os.path.join(_REPO_ROOT, "raw_calib_cache_fuji", "*", "raw", "*.RAF")
_SYNTHETIC_SOURCES = ("sony", "nikon", "canon")  # 이 환경에 real RAW가 없는 브랜드


def _resize_max_dim(img, max_dim):
    h, w = img.shape[:2]
    scale = max_dim / max(h, w)
    if scale >= 1:
        return img
    return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def _rawpy_default_render(raw_path, max_dim=1200):
    """rawpy 기본 sRGB 렌더링 - '이 카메라가 실제로 찍었을 법한' 근사
    소스(진짜 인카메라 엔진은 아니지만 raw_direct 경로에서는 굳이
    브랜드 커브가 필요 없어서 참고용일 뿐, 실제 평가는 raw에서 바로 함)."""
    with rawpy.imread(raw_path) as raw:
        rgb8 = raw.postprocess(use_camera_wb=True, no_auto_bright=True, output_bps=8)
    return _resize_max_dim(cv2.cvtColor(rgb8, cv2.COLOR_RGB2BGR), max_dim)


def _noise_sigma(img_bgr):
    return estimate_noise_sigma(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY).astype(np.float64))


def run_generalization(target_brand, base_image_path, target_profile=None):
    if target_brand not in BRAND_FUNCS:
        raise ValueError(f"알 수 없는 타깃 브랜드: {target_brand}")

    base_img = cv2.imread(base_image_path)
    if base_img is None:
        raise FileNotFoundError(base_image_path)
    base_img = _resize_max_dim(base_img, 1200)

    results = {}

    # 실제 RAW 경로 (Fuji) - HybridCameraEngine으로 브랜드 역산 없이 직접
    raw_files = sorted(glob.glob(_FUJI_RAW_GLOB))
    if raw_files:
        raw_path = raw_files[0]
        linear = _resize_max_dim(decode_raw(raw_path), 1200)
        engine = HybridCameraEngine(profile=target_profile)
        converted = engine.process(linear)
        # process()는 linear float RGB를 반환 - stats/noise 계산은 8bit BGR
        # 기준이라 sRGB 감마 인코딩 후 변환(save_tiff16과 동일한 인코딩)
        clipped = np.clip(converted, 0.0, 1.0)
        import colour
        srgb_encoded = colour.cctf_encoding(clipped, function="sRGB")
        converted_u8 = (np.clip(srgb_encoded, 0, 1) * 255).astype(np.uint8)[:, :, ::-1]  # RGB->BGR

        source_render = _rawpy_default_render(raw_path)
        results["fuji"] = {
            "path": "raw_direct (HybridCameraEngine, no brand inversion needed)",
            "is_real_raw": True,
            "pre_stats": image_stats(source_render),
            "post_stats": image_stats(converted_u8),
            "pre_noise_sigma": _noise_sigma(source_render),
            "post_noise_sigma": _noise_sigma(converted_u8),
        }
    else:
        print("  fuji: RAW 없음(raw_calib_cache_fuji/), 스킵")

    # 합성 소스 경로 (Sony/Nikon/Canon) - real RAW 없어서 apply_*_look()으로 근사
    for brand in _SYNTHETIC_SOURCES:
        source_img = BRAND_FUNCS[brand](base_img)
        converted = convert_between_brands(source_img, brand, target_brand)
        results[brand] = {
            "path": "synthetic (apply_*_look on common test image, NOT real camera data)",
            "is_real_raw": False,
            "pre_stats": image_stats(source_img),
            "post_stats": image_stats(converted),
            "pre_noise_sigma": _noise_sigma(source_img),
            "post_noise_sigma": _noise_sigma(converted),
        }

    return results


def _to_jsonable(obj):
    """core.stats.image_stats()가 반환하는 numpy 스칼라(float32 등)는
    json.dump가 그대로 직렬화 못 함 - 재귀적으로 파이썬 기본 타입으로
    변환."""
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, np.generic):
        return obj.item()
    return obj


def _convergence_summary(results):
    post_b2 = [r["post_stats"]["b2"] for r in results.values()]
    post_w995 = [r["post_stats"]["w995"] for r in results.values()]
    post_sat = [r["post_stats"]["sat"] for r in results.values()]
    pre_noise = [r["pre_noise_sigma"] for r in results.values()]
    post_noise = [r["post_noise_sigma"] for r in results.values()]
    return {
        "n_sources": len(results),
        "post_b2_std_across_sources": float(np.std(post_b2)),
        "post_w995_std_across_sources": float(np.std(post_w995)),
        "post_sat_std_across_sources": float(np.std(post_sat)),
        "noise_sigma_std_pre": float(np.std(pre_noise)),
        "noise_sigma_std_post": float(np.std(post_noise)),
        "fingerprint_erasure_ratio": (
            float(np.std(post_noise) / np.std(pre_noise)) if np.std(pre_noise) > 1e-9 else None
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Protocol 2: 소스 카메라 간 hybrid_engine 변환 결과 수렴성 평가")
    parser.add_argument("--target", required=True, help="타깃 브랜드 (예: hasselblad)")
    parser.add_argument("--base-image", required=True,
                         help="합성 소스(Sony/Nikon/Canon)를 만들 공통 테스트 사진 경로")
    parser.add_argument("--out", default=None, help="JSON 리포트 저장 경로")
    args = parser.parse_args()

    print(f"Cross-camera generalization 평가 중... (target={args.target})")
    print("주의: fuji만 실제 RAW, sony/nikon/canon은 apply_*_look 합성 소스(진짜 카메라 데이터 아님)\n")

    results = run_generalization(args.target, args.base_image)
    for src, r in results.items():
        tag = "REAL RAW" if r["is_real_raw"] else "synthetic"
        print(f"  {src:8s} [{tag:9s}] pre b2={r['pre_stats']['b2']:6.1f} -> "
              f"post b2={r['post_stats']['b2']:6.1f}  "
              f"pre_noise={r['pre_noise_sigma']:.3f} -> post_noise={r['post_noise_sigma']:.3f}")

    summary = _convergence_summary(results)
    print(f"\n=== 수렴성 요약 (n={summary['n_sources']}) ===")
    print(f"변환 후 소스 간 b2 표준편차: {summary['post_b2_std_across_sources']:.2f} "
          f"(작을수록 잘 수렴)")
    print(f"변환 후 소스 간 w995 표준편차: {summary['post_w995_std_across_sources']:.2f}")
    print(f"변환 후 소스 간 채도 표준편차: {summary['post_sat_std_across_sources']:.2f}")
    print(f"노이즈 시그니처 소스간 분산 - 변환 전: {summary['noise_sigma_std_pre']:.3f} "
          f"-> 변환 후: {summary['noise_sigma_std_post']:.3f}")
    if summary["fingerprint_erasure_ratio"] is not None:
        print(f"지문 소거 비율(post/pre, 1보다 작을수록 소거 성공): "
              f"{summary['fingerprint_erasure_ratio']:.2f}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(_to_jsonable({"per_source": results, "summary": summary}), f, indent=2)
        print(f"\n저장: {args.out}")


if __name__ == "__main__":
    main()
