"""
fuji_sample_pages.csv에 있는 Google Drive 링크에서 RAW(RAF)+SOOC JPEG를
받아서 raw_calib_cache_fuji/<camera>/raw, .../jpeg 에 저장하고,
같은 카메라 안에서 EXIF DateTimeOriginal이 일치하는 RAF<->JPEG 페어를 찾아
fuji_pairs_manifest.csv로 남긴다 (파일명이 서로 안 맞는 경우가 많아서
촬영시각으로 매칭 - calibrate_from_raw.py의 raw_url/jpeg_url 페어와 달리
여기는 사이트가 페어를 직접 지정해주지 않기 때문).

각 JPEG의 실제 Film Mode(필름 시뮬레이션) 태그는 exiftool로 읽어서 매니페스트에
같이 기록한다 - 후지 공식 사이트 샘플은 EXIF가 스트립돼 있어 이게 불가능했지만,
이 리뷰 사이트 JPEG는 카메라가 만든 원본 그대로라 MakerNote가 살아있다.
"""
import csv
import json
import os
import re
import subprocess

import gdown
import requests

CACHE_DIR = "raw_calib_cache_fuji"
CSV_PATH = "fuji_sample_pages.csv"
MANIFEST_PATH = "fuji_pairs_manifest.csv"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def extract_id(url):
    m = re.search(r"/folders/([a-zA-Z0-9_-]+)", url)
    if m:
        return "folder", m.group(1)
    m = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
    if m:
        return "file", m.group(1)
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    if m:
        return "unknown", m.group(1)
    raise ValueError(f"드라이브 URL에서 id를 못 찾음: {url}")


def resolve_kind(url, drive_id):
    # "open?id=" 링크는 파일/폴더 어느 쪽인지 URL만으로 알 수 없어서
    # 실제로 리다이렉트를 따라가서 최종 경로를 확인한다.
    resp = requests.get(f"https://drive.google.com/open?id={drive_id}",
                         headers=HEADERS, allow_redirects=True, timeout=30)
    if "/folders/" in resp.url:
        return "folder"
    return "file"


def fetch(url, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    if len(os.listdir(dest_dir)) > 0:
        print(f"  캐시됨: {dest_dir}")
        return
    kind, drive_id = extract_id(url)
    if kind == "unknown":
        kind = resolve_kind(url, drive_id)

    if kind == "folder":
        gdown.download_folder(id=drive_id, output=dest_dir, quiet=False, use_cookies=False)
    else:
        # 단일 파일 - 확장자를 모르니 gdown이 헤더에서 알아낸 원래 파일명을 그대로 씀
        gdown.download(id=drive_id, output=dest_dir + os.sep, quiet=False)


def exif_datetime_and_filmmode(path):
    out = subprocess.run(
        ["exiftool", "-json", "-DateTimeOriginal", "-FilmMode", path],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0 or not out.stdout.strip():
        return None, None
    data = json.loads(out.stdout)[0]
    return data.get("DateTimeOriginal"), data.get("FilmMode")


def collect_files(dest_dir, exts):
    files = []
    for root, _, names in os.walk(dest_dir):
        for n in names:
            if os.path.splitext(n)[1].lower() in exts:
                files.append(os.path.join(root, n))
    return files


def main():
    rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8-sig")))
    manifest = []

    for r in rows:
        camera = r["camera"]
        print(f"\n=== {camera} ===")
        cam_dir = os.path.join(CACHE_DIR, camera.replace(" ", "_"))
        raw_dir = os.path.join(cam_dir, "raw")
        jpeg_dir = os.path.join(cam_dir, "jpeg")

        try:
            print(" raw...")
            fetch(r["raw_drive_url"], raw_dir)
            print(" jpeg...")
            fetch(r["jpeg_drive_url"], jpeg_dir)
        except Exception as e:
            print(f"  다운로드 실패: {e}")
            continue

        raw_files = collect_files(raw_dir, {".raf"})
        jpeg_files = collect_files(jpeg_dir, {".jpg", ".jpeg"})
        print(f"  raw {len(raw_files)}장, jpeg {len(jpeg_files)}장")

        raw_by_time = {}
        for f in raw_files:
            dt, _ = exif_datetime_and_filmmode(f)
            if dt:
                raw_by_time.setdefault(dt, []).append(f)

        for jf in jpeg_files:
            dt, film_mode = exif_datetime_and_filmmode(jf)
            if not dt or dt not in raw_by_time:
                continue
            for rf in raw_by_time[dt]:
                manifest.append(dict(camera=camera, datetime=dt, film_mode=film_mode or "",
                                      raw_path=rf, jpeg_path=jf))

        print(f"  매칭된 페어: {sum(1 for m in manifest if m['camera'] == camera)}")

    with open(MANIFEST_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["camera", "datetime", "film_mode", "raw_path", "jpeg_path"])
        writer.writeheader()
        writer.writerows(manifest)
    print(f"\n총 {len(manifest)}쌍 -> {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
