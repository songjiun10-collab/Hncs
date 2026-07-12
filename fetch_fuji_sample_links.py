"""
mirrorlesscomparison.com의 후지필름 카메라 리뷰 갤러리 페이지들에서
"SOOC JPG and RAW Samples to Download" 섹션의 Google Drive 링크를 긁어와
fuji_sample_pages.csv로 저장한다.

핫셀블라드 공식 킷과 달리 후지 공식 사이트는 RAW/필름시뮬레이션 라벨을
전혀 제공하지 않아서(hasselblad_sample_images.csv 참고), 대신 이 리뷰
사이트가 명시적으로 "가공 안 한 순정 SOOC JPG + RAW"를 다운로드용으로
제공하는 걸 이용한다. exiftool로 각 JPEG의 실제 Film Mode 태그를 읽으면
후지 공식 사이트에서는 불가능했던 프리셋별 라벨링이 가능하다.
"""
import csv
import re

import requests

GALLERY_URLS = [
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

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

DRIVE_RE = re.compile(
    r'<li><a href="(https://drive\.google\.com/[^"]+)"[^>]*>\s*<strong>([^<]+)</strong>'
)


def find_drive_links(html):
    section_start = html.find("SOOC JPG and RAW Samples to Download")
    if section_start == -1:
        section_start = html.find("RAW Samples to Download")
    if section_start == -1:
        return []
    section_end = html.find("<hr", section_start + 40)
    chunk = html[section_start:section_end if section_end != -1 else section_start + 3000]
    return DRIVE_RE.findall(chunk)


def main():
    rows = []
    for url in GALLERY_URLS:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        links = find_drive_links(resp.text)
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

    with open("fuji_sample_pages.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["camera", "gallery_url", "raw_drive_url", "jpeg_drive_url"])
        writer.writeheader()
        writer.writerows(rows)
    print("저장: fuji_sample_pages.csv")


if __name__ == "__main__":
    main()
