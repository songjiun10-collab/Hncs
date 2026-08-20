"""README `docs/images/hybrid_engine_demo_more.jpg` 생성 CLI -
`tools/build_hybrid_engine_demo.py`와 같은 RAW 파이프라인 렌더링을
여러 장에 대해 반복해서 세로로 이어붙인 다중 before/after 그리드를
만든다.

  python3 -m tools.build_hybrid_engine_demo_more \\
      photo1.RAF photo1.jpg photo2.RAF photo2.jpg ... \\
      docs/images/hybrid_engine_demo_more.jpg
"""
import argparse
import os
import sys

import cv2
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.build_hybrid_engine_demo import (
    BAR_H,
    BG,
    FG,
    _load_bgr_exif_corrected,
    _resize_max_dim,
    render_with_profile,
)

ROW_MAX_DIM = 900
ROW_PAD = 6
HALF_WIDTH = 430


def _resize_to_width(bgr, width):
    h, w = bgr.shape[:2]
    scale = width / w
    return cv2.resize(bgr, (width, max(1, int(round(h * scale)))), interpolation=cv2.INTER_AREA)


def build_row(original_bgr, rendered_bgr, right_label, half_width=HALF_WIDTH):
    original_bgr = _resize_to_width(original_bgr, half_width)
    rendered_bgr = _resize_to_width(rendered_bgr, half_width)
    h = min(original_bgr.shape[0], rendered_bgr.shape[0])
    w = half_width
    original_bgr = original_bgr[:h]
    rendered_bgr = rendered_bgr[:h]

    row = Image.new("RGB", (2 * w, h + BAR_H), BG)
    draw = ImageDraw.Draw(row)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18)
    except OSError:
        font = ImageFont.load_default()

    row.paste(Image.fromarray(cv2.cvtColor(original_bgr, cv2.COLOR_BGR2RGB)), (0, BAR_H))
    row.paste(Image.fromarray(cv2.cvtColor(rendered_bgr, cv2.COLOR_BGR2RGB)), (w, BAR_H))
    draw.text((10, 6), "Original", fill=FG, font=font)
    draw.text((w + 10, 6), right_label, fill=FG, font=font)
    return row


def build_grid(pairs, profile="hasselblad", label="hybrid_engine.main --profile hasselblad"):
    rows = []
    for raw_path, jpeg_path in pairs:
        print(f"{raw_path} 디코드 + {profile} 프로필 렌더링 중...", flush=True)
        rendered_bgr = _resize_max_dim(render_with_profile(raw_path, profile), max_dim=ROW_MAX_DIM)
        original_bgr = _load_bgr_exif_corrected(jpeg_path, max_dim=ROW_MAX_DIM)
        rows.append(build_row(original_bgr, rendered_bgr, label))

    width = max(row.width for row in rows)
    height = sum(row.height for row in rows) + ROW_PAD * (len(rows) - 1)
    grid = Image.new("RGB", (width, height), BG)
    y = 0
    for row in rows:
        grid.paste(row, (0, y))
        y += row.height + ROW_PAD
    return grid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pairs_and_output", nargs="+",
                     help="raw1 jpeg1 raw2 jpeg2 ... output_path")
    ap.add_argument("--profile", default="hasselblad")
    ap.add_argument("--label", default="hybrid_engine.main --profile hasselblad")
    args = ap.parse_args()

    *pair_args, output_path = args.pairs_and_output
    if len(pair_args) % 2 != 0 or len(pair_args) == 0:
        ap.error("raw/jpeg 경로는 짝수 개, 최소 한 쌍 필요합니다")
    pairs = list(zip(pair_args[0::2], pair_args[1::2]))

    grid = build_grid(pairs, profile=args.profile, label=args.label)
    grid.save(output_path, quality=92)
    print(f"저장: {output_path} ({grid.size[0]}x{grid.size[1]})")


if __name__ == "__main__":
    main()
