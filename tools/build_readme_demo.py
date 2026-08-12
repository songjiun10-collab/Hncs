"""README/docs 데모 이미지(`docs/images/preset_demo.jpg`) 생성 CLI - 사진
한 장에 `brands/*.py`의 사진용 `apply_*` 룩을 전부 적용해서 라벨 붙은
그리드 이미지 하나로 합친다. 원-샷이 아니라 재사용 가능한 도구로
만든 이유: 새 브랜드/프리셋이 생길 때마다(이번 세션만도 v2/v3 여럿
추가됨) 데모를 다시 만들어야 하는 게 반복 작업이기 때문
(CLAUDE.md: "그 작업은 다음 세션에도 재발할 가능성이 높다").

`gui.tabs.brand_preview.list_shipped_looks()`를 그대로 재사용해서
목록을 별도로 안 든다 - 대입식(`apply_x = make_population_fit_look(...)`)
까지 스캔하도록 2026-08에 고친 바로 그 함수.

  python3 -m tools.build_readme_demo /path/to/photo.jpg docs/images/preset_demo.jpg
"""
import argparse
import importlib
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.tabs.brand_preview import list_shipped_looks

CELL_W, CELL_H = 220, 165
LABEL_H = 28
PAD = 4


def _load_bgr_exif_corrected(path):
    pil_img = Image.open(path)
    pil_img = ImageOps.exif_transpose(pil_img)
    rgb = np.array(pil_img.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _short_label(module, fn_name):
    if module == "(original)":
        return "(original)"
    brand = module.split(".", 1)[1]
    return f"{brand}\n{fn_name.replace('apply_', '')}"


def build_grid(source_bgr, cols=9):
    looks = [("(original)", "original")] + list_shipped_looks()
    rows = (len(looks) + cols - 1) // cols

    grid = Image.new("RGB", (cols * CELL_W, rows * (CELL_H + LABEL_H)), "white")
    draw = ImageDraw.Draw(grid)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 11)
    except OSError:
        font = ImageFont.load_default()

    thumb_src = cv2.resize(source_bgr, (CELL_W - 2 * PAD, CELL_H - 2 * PAD),
                            interpolation=cv2.INTER_AREA)

    for i, (module, fn_name) in enumerate(looks):
        print(f"  [{i + 1}/{len(looks)}] {module}.{fn_name}", flush=True)
        if module == "(original)":
            out = thumb_src
        else:
            fn = getattr(importlib.import_module(module), fn_name)
            out = fn(thumb_src)
            if out.ndim == 2:
                out = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
        out_rgb = cv2.cvtColor(out, cv2.COLOR_BGR2RGB)
        thumb = Image.fromarray(out_rgb)

        col, row = i % cols, i // cols
        x0 = col * CELL_W + PAD
        y0 = row * (CELL_H + LABEL_H) + PAD
        grid.paste(thumb, (x0, y0))
        draw.text((x0, y0 + CELL_H - 2 * PAD), _short_label(module, fn_name),
                  fill="black", font=font)

    return grid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source_image")
    ap.add_argument("output_path")
    ap.add_argument("--cols", type=int, default=9)
    args = ap.parse_args()

    source_bgr = _load_bgr_exif_corrected(args.source_image)
    grid = build_grid(source_bgr, cols=args.cols)
    grid.save(args.output_path, quality=90)
    print(f"저장: {args.output_path} ({grid.size[0]}x{grid.size[1]})")


if __name__ == "__main__":
    main()
