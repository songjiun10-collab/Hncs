"""dpreview 위젯 DB에서 받은 브랜드 raw/ 폴더를 `manifest.csv`(image_id,
camera, product_id, raw_file_url, notes)로 박제하고 raw/ 를 지운다 -
raw는 git-ignore 대상이라 어차피 커밋 안 되는데, manifest 없이 그냥
지우면 재현 불가능해진다. `tools/match_dpreview_downloads_by_hash.py`로
받은 raw/를 검증(`validate_dpreview_chart_brand.py`)까지 끝낸 뒤
디스크 확보용으로 호출한다(2026-09-04, 사용자 지시 - 디스크 용량
부족 사태).

    python3 -m tools.write_dpreview_manifest
      (payload는 stdin으로 JSON: {"rel_dir":..., "camera":..., "product_id":...,
       "images":[{"id":..., "url":...}, ...]})

또는 `write_manifest_and_clean(rel_dir, camera, product_id, images)`를
직접 import해서 호출.
"""
import csv
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIDGET_NOTE = ("dpreview 스튜디오씬 비교위젯 API (widget id 541497, product_id로 필터) - "
               "EVALUATION.md '공용 챠트 데이터베이스' 절 참고")


def write_manifest_and_clean(rel_dir, camera, product_id, images):
    full_dir = os.path.join(REPO_ROOT, rel_dir)
    with open(os.path.join(full_dir, "manifest.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["image_id", "camera", "product_id", "raw_file_url", "notes"])
        for img in images:
            w.writerow([img["id"], camera, product_id, img["url"], WIDGET_NOTE])
    raw_dir = os.path.join(full_dir, "raw")
    n = 0
    if os.path.isdir(raw_dir):
        for fn in os.listdir(raw_dir):
            fp = os.path.join(raw_dir, fn)
            if os.path.isfile(fp):
                os.remove(fp)
                n += 1
        os.rmdir(raw_dir)
    print(f"{rel_dir}: manifest written ({len(images)} rows), deleted {n} raw files")


if __name__ == "__main__":
    payload = json.load(sys.stdin)
    write_manifest_and_clean(payload["rel_dir"], payload["camera"], payload["product_id"], payload["images"])
