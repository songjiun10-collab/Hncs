"""docs/images/preset_demo.jpg 상단 타이틀 바를 현재 apply_* 개수로
다시 그린다. 타일(사진 그리드) 부분은 그대로 두고 y<TITLE_H만 교체 -
새 브랜드가 추가될 때마다 소스 사진을 다시 렌더링/재타일링할 필요 없이
숫자만 맞추는 용도.

python3 -m tools.regen_preset_demo_title
"""
import ast
import glob
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_PATH = os.path.join(ROOT, "docs", "images", "preset_demo.jpg")
TITLE_H = 54
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
BG = (24, 24, 24)


def count_photo_mode_looks():
    """brands/*.py의 사진용 apply_* 함수 개수 (video_frame 변형 제외).
    .claude/skills/run-hncs/driver.py의 shipped_looks()와 같은 기준."""
    n = 0
    for f in sorted(glob.glob(os.path.join(ROOT, "brands", "*.py"))):
        if f.endswith("__init__.py"):
            continue
        for node in ast.parse(open(f, encoding="utf-8").read()).body:
            if (isinstance(node, ast.FunctionDef) and node.name.startswith("apply_")
                    and "video_frame" not in node.name):
                n += 1
    return n


def regen():
    n_looks = count_photo_mode_looks()
    img = Image.open(IMAGE_PATH)
    w, h = img.size
    tiles = img.crop((0, TITLE_H, w, h))

    title = Image.new("RGB", (w, TITLE_H), BG)
    draw = ImageDraw.Draw(title)
    font = ImageFont.truetype(FONT_PATH, 20)
    text = f"HNCS preset demo - {n_looks} apply_* looks + original, one source photo (Nikon D5300)"
    bbox = draw.textbbox((0, 0), text, font=font)
    y = (TITLE_H - (bbox[3] - bbox[1])) // 2 - bbox[1]
    draw.text((8, y), text, font=font, fill=(255, 255, 255))

    out = Image.new("RGB", (w, h))
    out.paste(title, (0, 0))
    out.paste(tiles, (0, TITLE_H))
    out.save(IMAGE_PATH, quality=92)
    print(f"{IMAGE_PATH}: title updated, {n_looks} looks")


if __name__ == "__main__":
    regen()
