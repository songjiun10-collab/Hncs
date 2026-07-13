"""
다운로드 엔진 모음:
1. imaging-resource.com 카메라 리뷰 갤러리 공용 스크레이퍼 - 라이카/
   Phase One/Pentax/Ricoh GR 네 브랜드의 analyze 스크립트에 원래 거의
   동일하게 중복돼 있던 로직(list_gallery_images/resolve_full_image/
   download_file)을 여기로 합쳤다. tools/analyze.py가 브랜드별
   GALLERIES/필터만 다르게 넘겨서 호출한다.
2. 후지 mirrorlesscomparison.com RAW+JPEG 페어 다운로더 (Google Drive
   기반, gdown 사용) - 원래 fetch_fuji_sample_links.py + download_fuji_pairs.py
   두 파일이었던 걸 합쳤다.

사용법: `python3 -m tools.download fuji-links` / `python3 -m tools.download fuji-pairs`
(imaging-resource 엔진은 tools/analyze.py에서 라이브러리로만 쓰고 CLI는 없음)
"""
import csv
import json
import os
import re
import subprocess
import sys
import urllib.request

import gdown
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.validation import is_image_usable

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


# ============================================================
# imaging-resource.com 공용 엔진
# ============================================================
DETAIL_LINK_RE = re.compile(
    r'href="(/cameras/[^"]+/image/\d+\?section=gallery)"[^>]*>\s*<img([^>]*)>'
)
# 상세페이지의 <a href="FULL.jpg" target="_blank"><img ... class=
# "attachment-full size-full" ...></a> - href가 scaled 버전보다 큰 진짜
# 원본. img 태그 안에서 src가 class보다 앞에 오는 경우가 있어서 class
# 뒤에 src를 기대하는 정규식은 안 되고, 속성 전체를 캡처해서 따로 뽑는다.
FULL_IMG_RE = re.compile(r'<a href="([^"]+)" target="_blank"><img([^>]*)class="attachment-full size-full"')


def ir_fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def ir_img_url(img_attrs):
    """일부 갤러리는 이미지가 지연로딩(data-lazy-src)돼 있고, src는 자리
    표시용 placeholder라 data-lazy-src를 우선한다."""
    m = re.search(r'data-lazy-src="([^"]+)"', img_attrs)
    if m:
        return m.group(1)
    m = re.search(r'src="([^"]+)"', img_attrs)
    return m.group(1) if m else ""


def list_gallery_images(gallery_url, skip_keywords=(), skip_patterns=()):
    """갤러리 페이지에서 상세페이지 경로 목록을 뽑는다. skip_keywords는
    단순 부분문자열(예: "-mod", "-iso-"), skip_patterns는 컴파일된 정규식
    (예: re.compile(r"-f\\d"))으로 리뷰어 후보정본/기술 테스트샷(ISO 노이즈
    차트, 조리개 브라케팅 등)을 걸러낸다."""
    html = ir_fetch(gallery_url)
    seen = set()
    results = []
    for detail_path, img_attrs in DETAIL_LINK_RE.findall(html):
        if detail_path in seen:
            continue
        seen.add(detail_path)
        thumb_url = ir_img_url(img_attrs).lower()
        if any(k in thumb_url for k in skip_keywords):
            continue
        if any(p.search(thumb_url) for p in skip_patterns):
            continue
        results.append(detail_path)
    return results


def resolve_full_image(detail_path, base_url="https://www.imaging-resource.com"):
    detail_url = base_url + detail_path
    html = ir_fetch(detail_url)
    m = FULL_IMG_RE.search(html)
    if not m:
        return None
    original_url = m.group(1)
    scaled_url = ir_img_url(m.group(2))
    return original_url, scaled_url


def download_file(url, path):
    if os.path.exists(path):
        return True
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        with open(path, "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        print(f"    실패: {url} -> {e}")
        return False


# ============================================================
# 후지: mirrorlesscomparison.com 갤러리 링크 수집
# ============================================================
FUJI_GALLERY_URLS = [
    "https://mirrorlesscomparison.com/galleries/fuji-xt3-sample-images/",
    "https://mirrorlesscomparison.com/galleries/fuji-xt2-sample-images/",
    "https://mirrorlesscomparison.com/galleries/fuji-xt30-sample-images/",
    "https://mirrorlesscomparison.com/galleries/fujifilm-xt1-sample-images/",
    "https://mirrorlesscomparison.com/galleries/fujifilm-x30-sample-photos/",
    "https://mirrorlesscomparison.com/galleries/fuji-xa2-sample-images/",
    "https://mirrorlesscomparison.com/galleries/fuji-xh1-sample-images/",
    "https://mirrorlesscomparison.com/galleries/fuji-x100t-sample-photos-2/",
    "https://mirrorlesscomparison.com/galleries/fujifilm-x100s-sample-pics/",
    "https://mirrorlesscomparison.com/galleries/fuji-x-pro1-sample-photos/",
]

FUJI_LINKS_CSV = "datasets/fuji/fuji_sample_pages.csv"
FUJI_RAW_CACHE_DIR = "raw_calib_cache_fuji"
FUJI_MANIFEST_PATH = "fuji_pairs_manifest.csv"

DRIVE_RE = re.compile(
    r'<li><a href="(https://drive\.google\.com/[^"]+)"[^>]*>\s*<strong>([^<]+)</strong>'
)


def find_fuji_drive_links(html):
    section_start = html.find("SOOC JPG and RAW Samples to Download")
    if section_start == -1:
        section_start = html.find("RAW Samples to Download")
    if section_start == -1:
        return []
    section_end = html.find("<hr", section_start + 40)
    chunk = html[section_start:section_end if section_end != -1 else section_start + 3000]
    return DRIVE_RE.findall(chunk)


def fetch_fuji_links():
    """mirrorlesscomparison.com 갤러리들에서 RAW/JPEG Google Drive 링크를
    긁어 FUJI_LINKS_CSV로 저장 (원래 fetch_fuji_sample_links.py)."""
    rows = []
    for url in FUJI_GALLERY_URLS:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        links = find_fuji_drive_links(resp.text)
        title_match = re.search(r"<title>(.*?)</title>", resp.text)
        title = title_match.group(1) if title_match else url
        camera = title.split("Gallery of ")[-1].split(" Sample")[0]

        raw_url = jpeg_url = ""
        for link, label in links:
            if "raw" in label.lower():
                raw_url = link
            elif "jpg" in label.lower() or "jpeg" in label.lower():
                jpeg_url = link

        print(f"{camera}: raw={bool(raw_url)} jpeg={bool(jpeg_url)}")
        rows.append(dict(camera=camera, gallery_url=url, raw_drive_url=raw_url,
                          jpeg_drive_url=jpeg_url))

    os.makedirs(os.path.dirname(FUJI_LINKS_CSV), exist_ok=True)
    with open(FUJI_LINKS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["camera", "gallery_url", "raw_drive_url", "jpeg_drive_url"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"저장: {FUJI_LINKS_CSV}")


# ============================================================
# 후지: Google Drive RAW+JPEG 페어 다운로드 (원래 download_fuji_pairs.py)
# ============================================================
def _gdrive_extract_id(url):
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


def _gdrive_resolve_kind(drive_id):
    # "open?id=" 링크는 파일/폴더 어느 쪽인지 URL만으로 알 수 없어서
    # 실제로 리다이렉트를 따라가서 최종 경로를 확인한다.
    resp = requests.get(f"https://drive.google.com/open?id={drive_id}",
                         headers=HEADERS, allow_redirects=True, timeout=30)
    return "folder" if "/folders/" in resp.url else "file"


def _gdrive_fetch(url, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    if len(os.listdir(dest_dir)) > 0:
        print(f"  캐시됨: {dest_dir}")
        return
    kind, drive_id = _gdrive_extract_id(url)
    if kind == "unknown":
        kind = _gdrive_resolve_kind(drive_id)

    if kind == "folder":
        gdown.download_folder(id=drive_id, output=dest_dir, quiet=False, use_cookies=False)
    else:
        # 단일 파일 - 확장자를 모르니 gdown이 헤더에서 알아낸 원래 파일명을 그대로 씀
        gdown.download(id=drive_id, output=dest_dir + os.sep, quiet=False)


def _exif_datetime_and_filmmode(path):
    out = subprocess.run(
        ["exiftool", "-json", "-DateTimeOriginal", "-FilmMode", path],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0 or not out.stdout.strip():
        return None, None
    data = json.loads(out.stdout)[0]
    return data.get("DateTimeOriginal"), data.get("FilmMode")


def _collect_files(dest_dir, exts):
    files = []
    for root, _, names in os.walk(dest_dir):
        for n in names:
            if os.path.splitext(n)[1].lower() in exts:
                files.append(os.path.join(root, n))
    return files


def download_fuji_pairs():
    """datasets/fuji/fuji_sample_pages.csv의 Drive 링크에서 RAW(RAF)+SOOC
    JPEG를 받고, 같은 카메라 안에서 EXIF DateTimeOriginal이 일치하는
    RAF<->JPEG 페어를 찾아 FUJI_MANIFEST_PATH로 남긴다 (파일명이 서로 안
    맞는 경우가 많아서 촬영시각으로 매칭 - 이 사이트는 raw_url/jpeg_url을
    직접 짝지어 주지 않기 때문). 각 JPEG의 Film Mode 태그도 exiftool로
    같이 기록한다."""
    rows = list(csv.DictReader(open(FUJI_LINKS_CSV, encoding="utf-8-sig")))
    manifest = []

    for r in rows:
        camera = r["camera"]
        print(f"\n=== {camera} ===")
        cam_dir = os.path.join(FUJI_RAW_CACHE_DIR, camera.replace(" ", "_"))
        raw_dir = os.path.join(cam_dir, "raw")
        jpeg_dir = os.path.join(cam_dir, "jpeg")

        try:
            print(" raw...")
            _gdrive_fetch(r["raw_drive_url"], raw_dir)
            print(" jpeg...")
            _gdrive_fetch(r["jpeg_drive_url"], jpeg_dir)
        except Exception as e:
            print(f"  다운로드 실패: {e}")
            continue

        raw_files = _collect_files(raw_dir, {".raf"})
        jpeg_files = _collect_files(jpeg_dir, {".jpg", ".jpeg"})
        n_before = len(jpeg_files)
        jpeg_files = [f for f in jpeg_files if is_image_usable(f)]
        if len(jpeg_files) < n_before:
            print(f"  손상 JPEG 제외: {n_before - len(jpeg_files)}장")
        print(f"  raw {len(raw_files)}장, jpeg {len(jpeg_files)}장 (무결성 검증 통과분)")

        raw_by_time = {}
        for f in raw_files:
            dt, _ = _exif_datetime_and_filmmode(f)
            if dt:
                raw_by_time.setdefault(dt, []).append(f)

        for jf in jpeg_files:
            dt, film_mode = _exif_datetime_and_filmmode(jf)
            if not dt or dt not in raw_by_time:
                continue
            for rf in raw_by_time[dt]:
                manifest.append(dict(camera=camera, datetime=dt, film_mode=film_mode or "",
                                      raw_path=rf, jpeg_path=jf))

        print(f"  매칭된 페어: {sum(1 for m in manifest if m['camera'] == camera)}")

    with open(FUJI_MANIFEST_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["camera", "datetime", "film_mode", "raw_path", "jpeg_path"])
        writer.writeheader()
        writer.writerows(manifest)
    print(f"\n총 {len(manifest)}쌍 -> {FUJI_MANIFEST_PATH}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "fuji-links":
        fetch_fuji_links()
    elif mode == "fuji-pairs":
        download_fuji_pairs()
    else:
        print("usage: python3 -m tools.download [fuji-links|fuji-pairs]")
