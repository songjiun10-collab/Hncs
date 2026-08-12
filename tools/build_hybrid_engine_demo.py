"""README `docs/images/hybrid_engine_demo.jpg` 생성 CLI - RAW 파일 하나를
`hybrid_engine`의 RAW 파이프라인(HybridCameraEngine, Phase 0 색정제 +
Gray World + 톤/색 커브)으로 지정한 프로필(기본 hasselblad)로 렌더링해서
카메라 원본 JPEG과 나란히 놓는다.

`hybrid_engine.main`을 서브프로세스로 그대로 부르지 않는 이유: 그
모듈이 최상단에서 import하는 `hybrid_engine.utils.evaluate`가 이
환경의 colour-science 버전과 안 맞아서(기존에 알려진 24개 베이스라인
에러 중 하나, `--evaluate` 플래그를 안 써도 CLI 자체가 죽는다) 필요한
조각(`HybridCameraEngine`/`decode_raw`/`extract_camera_metadata`)만
직접 가져다 쓴다 - `hybrid_engine/main.py`의 `main()` 핵심 로직과
동일하고 `--evaluate` 관련 부분만 없다.

  python3 -m tools.build_hybrid_engine_demo photo.RAF original.jpg docs/images/hybrid_engine_demo.jpg
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hybrid_engine.core.color_matrix import extract_camera_metadata
from hybrid_engine.pipeline.engine import HybridCameraEngine
from hybrid_engine.utils.io import decode_raw

_PROFILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                              "hybrid_engine", "assets", "profiles")
BAR_H = 36
BG = (34, 34, 34)
FG = (230, 230, 230)
MAX_DIM = 900


def _load_profile(name):
    with open(os.path.join(_PROFILES_DIR, f"{name}.json"), encoding="utf-8") as f:
        profile = json.load(f)
    profile.pop("_comment", None)
    return profile


def render_with_profile(raw_path, profile_name="hasselblad"):
    linear = decode_raw(raw_path)
    camera_wb = extract_camera_metadata(raw_path)["camera_whitebalance"]
    engine = HybridCameraEngine(profile=_load_profile(profile_name))
    result_linear = engine.process(linear, camera_whitebalance=camera_wb)
    srgb_u8 = np.clip(result_linear, 0.0, 1.0)
    import colour
    srgb_u8 = colour.cctf_encoding(srgb_u8, function="sRGB")
    bgr_u8 = cv2.cvtColor((np.clip(srgb_u8, 0, 1) * 255).astype(np.uint8), cv2.COLOR_RGB2BGR)
    return bgr_u8


def _resize_max_dim(bgr, max_dim=MAX_DIM):
    h, w = bgr.shape[:2]
    scale = max_dim / max(h, w)
    if scale < 1:
        bgr = cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return bgr


def _load_bgr_exif_corrected(path, max_dim=MAX_DIM):
    pil_img = ImageOps.exif_transpose(Image.open(path))
    bgr = cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)
    return _resize_max_dim(bgr, max_dim)


def build_before_after(original_bgr, rendered_bgr, right_label):
    h = min(original_bgr.shape[0], rendered_bgr.shape[0])
    w = min(original_bgr.shape[1], rendered_bgr.shape[1])
    original_bgr = cv2.resize(original_bgr, (w, h), interpolation=cv2.INTER_AREA)
    rendered_bgr = cv2.resize(rendered_bgr, (w, h), interpolation=cv2.INTER_AREA)

    canvas = Image.new("RGB", (2 * w, h + BAR_H), BG)
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22)
    except OSError:
        font = ImageFont.load_default()

    canvas.paste(Image.fromarray(cv2.cvtColor(original_bgr, cv2.COLOR_BGR2RGB)), (0, BAR_H))
    canvas.paste(Image.fromarray(cv2.cvtColor(rendered_bgr, cv2.COLOR_BGR2RGB)), (w, BAR_H))
    draw.text((10, 6), "Original", fill=FG, font=font)
    draw.text((w + 10, 6), right_label, fill=FG, font=font)
    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw_path")
    ap.add_argument("original_jpeg")
    ap.add_argument("output_path")
    ap.add_argument("--profile", default="hasselblad")
    ap.add_argument("--label", default="hybrid_engine.main --profile hasselblad")
    args = ap.parse_args()

    print(f"{args.raw_path} 디코드 + {args.profile} 프로필 렌더링 중...", flush=True)
    rendered_bgr = _resize_max_dim(render_with_profile(args.raw_path, args.profile))
    original_bgr = _load_bgr_exif_corrected(args.original_jpeg)

    canvas = build_before_after(original_bgr, rendered_bgr, args.label)
    canvas.save(args.output_path, quality=92)
    print(f"저장: {args.output_path} ({canvas.size[0]}x{canvas.size[1]})")


if __name__ == "__main__":
    main()
