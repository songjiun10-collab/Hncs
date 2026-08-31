"""
렌즈 왜곡 보정 CLI - EXIF(Make/Model/LensModel/FocalLength/FNumber)를 읽어
core/lens_correction.py로 lensfun DB 매치 + 지오메트릭 왜곡 보정을 적용한다.
RAW/일반 이미지 파일 둘 다 입력으로 받는다.

  python3 -m tools.lens_correction input.RAF output.jpg
  python3 -m tools.lens_correction input.jpg output.jpg --lens "XF10-24mmF4 R OIS" --focal-length 10 --aperture 8
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2

from core.lens_correction import correct_from_exif

_RAW_EXTS = {".cr2", ".cr3", ".nef", ".arw", ".raf", ".rw2", ".orf", ".3fr", ".fff", ".dng"}

_EXIF_TAGS = ["Make", "Model", "LensModel", "LensID", "LensInfo",
              "FocalLength", "FNumber", "ApertureValue"]


def _read_exif(path):
    out = subprocess.run(["exiftool", "-json"] + [f"-{t}" for t in _EXIF_TAGS] + [path],
                          capture_output=True, text=True, timeout=60)
    if out.returncode != 0 or not out.stdout.strip():
        raise RuntimeError(f"exiftool 실패 (returncode={out.returncode}): {path}")
    return json.loads(out.stdout)[0]


def _parse_focal_length(value):
    """exiftool의 '10.0 mm' 같은 문자열/숫자 둘 다에서 mm 단위 float 추출."""
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value).split()[0])


def _parse_aperture(value):
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value))


def resolve_lens_params(path, *, make=None, model=None, lens=None,
                        focal_length=None, aperture=None):
    """EXIF와 명시적 override를 합쳐 lensfun 보정에 필요한 값을 반환.

    두 CLI(`tools.lens_correction`, `tools.raw_pipeline`)가 같은 규칙으로
    EXIF를 읽도록 공통화했다. 호출자는 ``--make`` 같은 명시적 인자를
    넘겨 EXIF가 비어 있거나 부정확한 RAW도 처리할 수 있다.

    정보가 모자라면 ``ValueError``를 낸다. 보정하지 않은 이미지를 성공한
    것처럼 반환하지 않기 위해서이며, CLI가 이를 사용자 친화적인 오류로
    표시한다.
    """
    exif = _read_exif(path)
    resolved_make = make or exif.get("Make")
    resolved_model = model or exif.get("Model")
    resolved_lens = (lens or exif.get("LensModel") or exif.get("LensID")
                     or exif.get("LensInfo"))

    resolved_focal_length = focal_length
    if resolved_focal_length is None:
        if "FocalLength" not in exif:
            raise ValueError("--focal-length가 없고 EXIF에 FocalLength도 없음")
        resolved_focal_length = _parse_focal_length(exif["FocalLength"])

    resolved_aperture = aperture
    if resolved_aperture is None:
        aperture_src = exif.get("FNumber", exif.get("ApertureValue"))
        if aperture_src is None:
            raise ValueError("--aperture가 없고 EXIF에 FNumber/ApertureValue도 없음")
        resolved_aperture = _parse_aperture(aperture_src)

    if not resolved_make or not resolved_model or not resolved_lens:
        raise ValueError(
            "카메라/렌즈 정보 부족 "
            f"(make={resolved_make}, model={resolved_model}, lens={resolved_lens})"
        )

    return {
        "make": resolved_make,
        "model": resolved_model,
        "lens_model": resolved_lens,
        "focal_length": float(resolved_focal_length),
        "aperture": float(resolved_aperture),
    }


def _load_image(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in _RAW_EXTS:
        import rawpy
        with rawpy.imread(path) as raw:
            return raw.postprocess(use_camera_wb=True, no_auto_bright=True, output_bps=8)[:, :, ::-1]
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(path)
    return img


def main():
    parser = argparse.ArgumentParser(description="EXIF 기반 렌즈 왜곡 보정 (lensfun DB)")
    parser.add_argument("input", help="입력 이미지 경로 (RAW 또는 JPEG/TIFF/PNG)")
    parser.add_argument("output", help="출력 이미지 경로")
    parser.add_argument("--make", default=None, help="카메라 제조사 (생략 시 EXIF에서 읽음)")
    parser.add_argument("--model", default=None, help="카메라 모델 (생략 시 EXIF에서 읽음)")
    parser.add_argument("--lens", default=None, help="렌즈 모델 (생략 시 EXIF LensModel/LensID/LensInfo 순으로 시도)")
    parser.add_argument("--focal-length", type=float, default=None, help="초점거리 mm (생략 시 EXIF에서 읽음)")
    parser.add_argument("--aperture", type=float, default=None, help="조리개값 (생략 시 EXIF에서 읽음)")
    parser.add_argument("--distance", type=float, default=1000.0, help="촬영 거리 근사치(m), 기본 1000(무한대에 가깝게)")
    args = parser.parse_args()

    try:
        params = resolve_lens_params(
            args.input, make=args.make, model=args.model, lens=args.lens,
            focal_length=args.focal_length, aperture=args.aperture,
        )
    except ValueError as exc:
        print(f"에러: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"카메라: {params['make']} {params['model']}  렌즈: {params['lens_model']}  "
          f"초점거리: {params['focal_length']}mm  조리개: f/{params['aperture']}")

    img = _load_image(args.input)
    corrected, info = correct_from_exif(img, distance=args.distance, **params)
    if not info["ok"]:
        print(f"보정 실패: {info['reason']} ({info})", file=sys.stderr)
        sys.exit(1)

    cv2.imwrite(args.output, corrected)
    print(f"매치된 DB 프로파일: 카메라={info['camera']}  렌즈={info['lens']}")
    print(f"저장: {args.output}")


if __name__ == "__main__":
    main()
