"""
apply_hncs_x2dii()가 실제 이미지에서 어떻게 보이는지 눈으로 확인하기
위한 렌더 스크립트 - 지금까지의 검증은 전부 ΔE00/RMSE 숫자였지, 실제
출력 JPG를 본 적은 없었다. X2D II raw 몇 장을 골라 원본 카메라 JPG /
apply_hncs(main) / apply_hncs_x2dii 세 개를 나란히 렌더링해서 저장한다.

  python3 -m tools.render_x2dii_comparison
"""
import csv
import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brands.hasselblad import apply_hncs
from brands.hasselblad_x2dii import apply_hncs_x2dii
from tools.calibrate import load_neutral_render

RAW_DIR = "/Users/songjiun/Documents/raw pair"
MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "datasets", "hasselblad", "dpreview_raw_jpeg_pairs_clean.csv")
OUT_DIR = "/private/tmp/claude-501/-Users-songjiun/2723c108-07c0-42ac-b509-d2a51043de16/scratchpad/x2dii_compare"

SAMPLE_RAW_FILES = [
    "0174976521.3fr",
    "0512413224.3fr",
    "1188410135.3fr",
    "5648738585.3fr",
    "9860222596.3fr",
]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rows = {r['raw_file']: r for r in csv.DictReader(open(MANIFEST))}

    for raw_file in SAMPLE_RAW_FILES:
        r = rows[raw_file]
        raw_path = os.path.join(RAW_DIR, raw_file)
        jpg_path = os.path.join(RAW_DIR, r['jpeg_file'])
        stem = os.path.splitext(raw_file)[0]

        neutral = load_neutral_render(raw_path, max_dim=1600)
        main_out = apply_hncs(neutral)
        x2dii_out = apply_hncs_x2dii(neutral)
        target = cv2.imread(jpg_path)
        h, w = neutral.shape[:2]
        if target is not None:
            target = cv2.resize(target, (w, h), interpolation=cv2.INTER_AREA)

        cv2.imwrite(os.path.join(OUT_DIR, f"{stem}_1_camera_jpg.jpg"), target)
        cv2.imwrite(os.path.join(OUT_DIR, f"{stem}_2_apply_hncs_main.jpg"), main_out)
        cv2.imwrite(os.path.join(OUT_DIR, f"{stem}_3_apply_hncs_x2dii.jpg"), x2dii_out)
        print(f"{raw_file}: 저장 완료", flush=True)

    print(f"\n출력 위치: {OUT_DIR}")


if __name__ == "__main__":
    main()
