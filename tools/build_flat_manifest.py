"""
build_local_manifest.py와 같은 EXIF DateTimeOriginal 페어링(find_pairs)을
쓰되, datasets/<브랜드>/contributed/<세트>/로 파일을 복사하지 않고 원본
경로 그대로 둔 채 raw_file/jpeg_file/model 3컬럼 CSV만 만든다 - 이번
배치(로컬 raw pair 폴더 53GB)는 build_local_manifest의 복사 방식을 쓰면
디스크가 남는 74GB를 넘길 위험이 있어서, 기존 세션에서 써온
dpreview_raw_jpeg_pairs_clean.csv류 포맷(파일은 제자리, CSV만 참조)으로
대신한다.

  python3 -m tools.build_flat_manifest "/Users/songjiun/local-work/raw pair" \
      --make Canon --ext .cr3 --out datasets/canon/canon_r6iii_pairs.csv

--make은 EXIF Make 대조(편집 오염과 무관 - jpeg Software 검사로 별도 처리),
--ext은 이 브랜드가 쓰는 raw 확장자만 골라 매칭 대상을 좁힌다(안 주면
find_pairs가 지원하는 모든 확장자를 다 뒤짐 - 브랜드 섞인 폴더에서
느리고 위험).
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.analyze import _check_genuine_bytes
from tools.build_local_manifest import find_pairs, RAW_EXT as ALL_RAW_EXT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("src_dir")
    parser.add_argument("--out", required=True)
    parser.add_argument("--make", required=True, help="EXIF Make 대조용 제조사명")
    parser.add_argument("--ext", action="append", required=True,
                         help="이 브랜드 raw 확장자(.cr3 등) - 여러 개면 --ext 반복")
    args = parser.parse_args()
    src_dir = os.path.expanduser(args.src_dir)

    import tools.build_local_manifest as blm
    blm.RAW_EXT = set(args.ext) & ALL_RAW_EXT

    pairs = find_pairs(src_dir, already_raw=set(), already_jpeg=set())
    print(f"{len(pairs)}개 raw/jpeg 시각 매칭")

    rows = []
    dropped_make = dropped_edit = 0
    for r, j, delta, oh in pairs:
        raw_path = os.path.join(src_dir, r["filename"])
        jpeg_path = os.path.join(src_dir, j["filename"])
        if args.make.lower() not in _make_of(raw_path):
            dropped_make += 1
            continue
        with open(jpeg_path, "rb") as f:
            if not _check_genuine_bytes(f.read()):
                dropped_edit += 1
                continue
        rows.append(dict(raw_file=r["filename"], jpeg_file=j["filename"],
                          model=r["model"].strip()))

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["raw_file", "jpeg_file", "model"])
        w.writeheader()
        w.writerows(rows)

    print(f"제조사 불일치 제외 {dropped_make}, 편집 오염 제외 {dropped_edit}, "
          f"최종 {len(rows)}쌍 -> {args.out}")
    from collections import Counter
    for model, cnt in Counter(r["model"] for r in rows).most_common():
        print(f"  {model}: {cnt}")


def _make_of(path):
    import subprocess
    out = subprocess.run(["exiftool", "-T", "-Make", path], capture_output=True, text=True, timeout=30)
    return (out.stdout or "").strip().lower()


if __name__ == "__main__":
    main()
