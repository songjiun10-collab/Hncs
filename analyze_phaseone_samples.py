"""
imaging-resource.com의 Phase One 카메라 리뷰 갤러리에서 population 통계를
뽑는다.

라이카/후지와 개념적으로 다른 지점: Phase One 디지털백은 스튜디오/테더링
중심이라 컨슈머 카메라 같은 인카메라 JPEG 엔진이 사실상 의미가 없다.
실제로 받아본 샘플의 EXIF Software는 전부 "Capture One"(Phase One 자체
제작 RAW 컨버터)이었다 - 이건 라이카/후지 때 걸러냈던 "리뷰어가 Photoshop/
Lightroom으로 편집한 제3자 편집본"과 달리 Phase One의 공식 렌더링 소프트웨어
자체이므로 오히려 이게 맞는 타깃이다. 그래서 이 프로젝트의 목표는
"Phase One 카메라 JPEG"가 아니라 "Capture One 기본 렌더링"이 된다.

이 사이트는 라이카 때 쓴 것과 같은 CMS 템플릿이지만 일부 갤러리는 이미지가
지연로딩(data-lazy-src)돼 있어서 정규식을 그에 맞게 조정했고, 리뷰어의
후보정 버전은 파일명 접미사가 "-EDIT"가 아니라 "-MOD"인 경우가 많아서
필터 키워드를 넓혔다. 상세페이지의 진짜 원본(href) 링크가 종종 404라
scaled 버전으로 폴백한다.

Phase One XT 갤러리 URL은 추측했지만 존재하지 않는 슬러그라 사이트가
엉뚱한 catch-all 페이지로 리다이렉트시켜서 제외 - 검증된 URL을 못 찾음.
"""
import csv
import os
import re
import subprocess
import time
import urllib.request

import cv2
import numpy as np

CACHE_DIR = "downloaded_samples_phaseone"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

GALLERIES = [
    ("Phase One XF 100MP", "https://www.imaging-resource.com/PRODS/phase-one-xf-100mp/phase-one-xf-100mpGALLERY.HTM"),
]

MAX_PER_CAMERA = 20

DETAIL_LINK_RE = re.compile(
    r'href="(/cameras/[^"]+/image/\d+\?section=gallery)"[^>]*>\s*<img([^>]*)>'
)
# src가 class보다 앞에 오는 경우가 있어서(Leica 때 겪은 버그) class 뒤에
# src를 기대하는 정규식은 안 됨 - img 태그 속성 전체를 캡처해서 src를 따로 뽑음
FULL_IMG_RE = re.compile(r'<a href="([^"]+)" target="_blank"><img([^>]*)class="attachment-full size-full"')

EDIT_KEYWORDS = ("edit", "-mod", "unsharpmask", "nosharp", "stack")


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _img_url(img_attrs):
    m = re.search(r'data-lazy-src="([^"]+)"', img_attrs)
    if m:
        return m.group(1)
    m = re.search(r'src="([^"]+)"', img_attrs)
    return m.group(1) if m else ""


def list_gallery_images(gallery_url):
    html = fetch(gallery_url)
    seen = set()
    results = []
    for detail_path, img_attrs in DETAIL_LINK_RE.findall(html):
        if detail_path in seen:
            continue
        seen.add(detail_path)
        thumb_url = _img_url(img_attrs)
        if any(k in thumb_url.lower() for k in EDIT_KEYWORDS):
            continue
        results.append(detail_path)
    return results


def resolve_full_image(detail_path):
    detail_url = "https://www.imaging-resource.com" + detail_path
    html = fetch(detail_url)
    m = FULL_IMG_RE.search(html)
    if not m:
        return None
    original_url = m.group(1)
    scaled_url = _img_url(m.group(2))
    return original_url, scaled_url


def download(url, path):
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


def exif_check(path):
    out = subprocess.run(["exiftool", "-Software", path], capture_output=True, timeout=30)
    text = out.stdout.decode("utf-8", errors="ignore").lower()
    capture_one = "capture one" in text
    third_party_edit = any(s in text for s in ["photoshop", "lightroom"])
    return capture_one, third_party_edit


def stats(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    s = hsv[:, :, 1].astype(np.float32)
    p = np.percentile
    dark = (gray < 40).sum() / gray.size * 100
    return dict(b2=p(gray, 2), w995=p(gray, 99.5), med=np.median(gray),
                sat=s[s > 20].mean() if (s > 20).any() else 0, dark_pct=dark)


def main():
    os.makedirs(CACHE_DIR, exist_ok=True)
    results = []

    for camera, gallery_url in GALLERIES:
        print(f"\n=== {camera} ===")
        try:
            detail_paths = list_gallery_images(gallery_url)
        except Exception as e:
            print(f"  갤러리 목록 실패: {e}")
            continue
        print(f"  후보 {len(detail_paths)}장 (MOD/EDIT 제외)")

        n_ok = 0
        for detail_path in detail_paths:
            if n_ok >= MAX_PER_CAMERA:
                break
            try:
                resolved = resolve_full_image(detail_path)
            except Exception:
                continue
            if not resolved:
                continue
            original_url, scaled_url = resolved

            fname = f"{camera.replace(' ', '_')}_{os.path.basename(original_url)}"
            path = os.path.join(CACHE_DIR, fname)
            if not download(original_url, path):
                # 원본(href)이 404인 경우가 종종 있어서 scaled로 폴백
                fname = f"{camera.replace(' ', '_')}_{os.path.basename(scaled_url)}"
                path = os.path.join(CACHE_DIR, fname)
                if not download(scaled_url, path):
                    continue

            capture_one, third_party_edit = exif_check(path)
            if not capture_one or third_party_edit:
                print(f"  스킵 ({'Capture One 아님' if not capture_one else '제3자 편집됨'}): {fname}")
                os.remove(path)
                continue

            img = cv2.imread(path)
            if img is None:
                continue
            st = stats(img)
            results.append(dict(camera=camera, filename=fname, url=original_url, **st))
            n_ok += 1
            print(f"  [{n_ok}/{MAX_PER_CAMERA}] {fname}  b2={st['b2']:.0f} w995={st['w995']:.0f} sat={st['sat']:.0f}")
            time.sleep(0.3)

    if not results:
        print("\n결과 없음")
        return

    with open("phaseone_stats_result.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    print(f"\n=== 전체 population 통계 (n={len(results)}) ===")
    shadow_valid = [r for r in results if r["dark_pct"] > 5]
    print(f"그림자유효: {len(shadow_valid)}장")
    if shadow_valid:
        print(f"블랙p2 타깃: {np.mean([r['b2'] for r in shadow_valid]):.1f}")
    print(f"화이트p99.5 타깃: {np.mean([r['w995'] for r in results]):.1f}")
    print(f"채도 평균: {np.mean([r['sat'] for r in results]):.1f}")

    print("\n저장: phaseone_stats_result.csv")


if __name__ == "__main__":
    main()
