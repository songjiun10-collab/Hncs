"""README `docs/images/before_after_hncs.jpg` 생성 CLI - 사진 한 장에
`apply_hncs()`를 적용하기 전/후를 좌우로 나란히 놓고 위에 라벨 바를
붙인다. 재사용 가능한 CLI로 저장(CLAUDE.md: 데모 이미지 재생성은
반복될 작업).

  python3 -m tools.build_before_after_demo photo.jpg docs/images/before_after_hncs.jpg
"""
import argparse
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brands.hasselblad import apply_hncs

BAR_H = 36
BG = (34, 34, 34)
FG = (230, 230, 230)


def _load_bgr_exif_corrected(path, max_dim=900):
    pil_img = ImageOps.exif_transpose(Image.open(path))
    bgr = cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)
    h, w = bgr.shape[:2]
    scale = max_dim / max(h, w)
    if scale < 1:
        bgr = cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return bgr


def build_before_after(source_bgr, right_label="apply_hncs (Hasselblad)"):
    after_bgr = apply_hncs(source_bgr)
    h, w = source_bgr.shape[:2]

    canvas = Image.new("RGB", (2 * w, h + BAR_H), BG)
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22)
    except OSError:
        font = ImageFont.load_default()

    before_rgb = Image.fromarray(cv2.cvtColor(source_bgr, cv2.COLOR_BGR2RGB))
    after_rgb = Image.fromarray(cv2.cvtColor(after_bgr, cv2.COLOR_BGR2RGB))
    canvas.paste(before_rgb, (0, BAR_H))
    canvas.paste(after_rgb, (w, BAR_H))
    draw.text((10, 6), "Original", fill=FG, font=font)
    draw.text((w + 10, 6), right_label, fill=FG, font=font)
    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source_image")
    ap.add_argument("output_path")
    ap.add_argument("--label", default="apply_hncs (Hasselblad)")
    args = ap.parse_args()

    source_bgr = _load_bgr_exif_corrected(args.source_image)
    canvas = build_before_after(source_bgr, right_label=args.label)
    canvas.save(args.output_path, quality=92)
    print(f"저장: {args.output_path} ({canvas.size[0]}x{canvas.size[1]})")


if __name__ == "__main__":
    main()
