"""
imaging-resource.com의 라이카 카메라 리뷰 갤러리에서 실측 population 통계를
뽑는다. 라이카는 후지처럼 카메라 내장 "필름모드" 프리셋이 여러 개 있는 게
아니라(단일 색과학), 핫셀블라드 v9 때와 같은 급의 population 통계 방식으로
접근한다.

시도해본 다른 소스들(dpreview/kenrockwell/photographyblog - Cloudflare 차단,
stevehuffphoto - Photoshop/Lightroom으로 편집된 사진이라 SOOC 아님,
leicarumors의 Dropbox DNG 링크 - JS 렌더링이라 폴더 목록 못 긁음)은 전부
막혀서, RAW 페어 없이 JPEG population 통계만으로 시작한다.

imaging-resource.com 갤러리 구조:
  갤러리 페이지 -> 썸네일 + 상세페이지 링크(/cameras/{slug}/image/{id}?section=gallery)
  상세페이지 -> <a href="FULL.jpg" target="_blank"><img class="attachment-full
                size-full" src="SCALED.jpg"></a>  (scaled 버전이 이미 충분히 큼)
파일명에 "-EDIT"가 붙은 건 리뷰어가 후보정한 버전이라 제외하고, EXIF Software가
Photoshop/Lightroom/Camera Raw를 언급하면 추가로 걸러서 진짜 SOOC만 쓴다.
"""
import csv
import os
import re
import subprocess
import time
import urllib.request

import cv2
import numpy as np

CACHE_DIR = "downloaded_samples_leica"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

GALLERIES = [
    ("Leica M9", "https://www.imaging-resource.com/PRODS/M9/M9GALLERY.HTM"),
    ("Leica X Vario", "https://www.imaging-resource.com/PRODS/leica-x-vario/leica-x-varioGALLERY.HTM"),
    ("Leica SL2", "https://www.imaging-resource.com/PRODS/leica-sl2/leica-sl2GALLERY.HTM"),
    ("Leica T (Typ 701)", "https://www.imaging-resource.com/cameras/leica-t-typ-701-review/gallery/"),
]

MAX_PER_CAMERA = 15  # 카메라당 최대 다운로드 수 (대역폭/시간 절약)

DETAIL_LINK_RE = re.compile(r'href="(/cameras/[^"]+/image/\d+\?section=gallery)"[^>]*>\s*<img[^>]*src="([^"]+)"')
FULL_IMG_RE = re.compile(r'class="attachment-full size-full"[^>]*src="([^"]+)"')


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def list_gallery_images(gallery_url):
    html = fetch(gallery_url)
    seen = set()
    results = []
    for detail_path, thumb_url in DETAIL_LINK_RE.findall(html):
        if detail_path in seen:
            continue
        seen.add(detail_path)
        if "edit" in thumb_url.lower():
            continue
        results.append(detail_path)
    return results


def resolve_full_image(detail_path):
    detail_url = "https://www.imaging-resource.com" + detail_path
    html = fetch(detail_url)
    m = FULL_IMG_RE.search(html)
    return m.group(1) if m else None


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
    out = subprocess.run(["exiftool", "-Make", "-Software"], input=open(path, "rb").read(),
                          capture_output=True, timeout=30)
    text = out.stdout.decode("utf-8", errors="ignore")
    make_ok = "leica" in text.lower()
    edited = any(s in text.lower() for s in ["photoshop", "lightroom", "camera raw", "capture one"])
    return make_ok, edited


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
        print(f"  후보 {len(detail_paths)}장 (EDIT 제외)")

        n_ok = 0
        for detail_path in detail_paths:
            if n_ok >= MAX_PER_CAMERA:
                break
            try:
                full_url = resolve_full_image(detail_path)
            except Exception as e:
                continue
            if not full_url:
                continue

            fname = f"{camera.replace(' ', '_')}_{os.path.basename(full_url)}"
            path = os.path.join(CACHE_DIR, fname)
            if not download(full_url, path):
                continue

            make_ok, edited = exif_check(path)
            if not make_ok or edited:
                print(f"  스킵 ({'라이카 아님' if not make_ok else '편집된 파일'}): {fname}")
                os.remove(path)
                continue

            img = cv2.imread(path)
            if img is None:
                continue
            st = stats(img)
            results.append(dict(camera=camera, filename=fname, url=full_url, **st))
            n_ok += 1
            print(f"  [{n_ok}/{MAX_PER_CAMERA}] {fname}  b2={st['b2']:.0f} w995={st['w995']:.0f} sat={st['sat']:.0f}")
            time.sleep(0.3)

    if not results:
        print("\n결과 없음")
        return

    with open("leica_stats_result.csv", "w", newline="", encoding="utf-8") as f:
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

    print(f"\n=== 카메라별 ===")
    from collections import defaultdict
    groups = defaultdict(list)
    for r in results:
        groups[r["camera"]].append(r)
    for cam, rows in groups.items():
        sv = [r for r in rows if r["dark_pct"] > 5]
        b2 = np.mean([r["b2"] for r in sv]) if sv else float("nan")
        w995 = np.mean([r["w995"] for r in rows])
        sat = np.mean([r["sat"] for r in rows])
        print(f"{cam:20s} n={len(rows):2d}  b2={b2:5.1f}  w995={w995:5.1f}  sat={sat:5.1f}")

    print("\n저장: leica_stats_result.csv")


if __name__ == "__main__":
    main()
